import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request
from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserSession
from app.utils.clock import utcnow
from app.utils.password_policy import is_strong_password

load_dotenv()
_secret = os.getenv("SECRET_KEY")
if not _secret:
    raise RuntimeError("FATAL: SECRET_KEY não configurada. A aplicação não pode iniciar sem ela.")
SECRET_KEY: str = _secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
SESSION_IDLE_TIMEOUT_MINUTES = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "45"))
if ACCESS_TOKEN_EXPIRE_MINUTES <= 0 or SESSION_IDLE_TIMEOUT_MINUTES <= 0:
    raise RuntimeError("Os limites de duração da sessão devem ser positivos.")


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# Hash válido, com o mesmo custo das senhas cadastradas; não corresponde a uma conta.
DUMMY_PASSWORD_HASH = get_password_hash(secrets.token_urlsafe(32))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(UTC)
    return jwt.encode({**data, "iat": now, "exp": now + (expires_delta or timedelta(minutes=15))}, SECRET_KEY, algorithm=ALGORITHM)


def create_user_session(db: Session, user: User) -> str:
    now = utcnow()
    session_id = str(uuid4())
    db.add(UserSession(id=session_id, user_id=user.id, token_version=user.token_version,
                       last_seen_at=now, expires_at=now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)))
    return create_access_token({"sub": user.auth_subject, "sid": session_id, "tv": user.token_version},
                               timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))


def revoke_user_sessions(db: Session, user_id: int) -> None:
    db.query(UserSession).filter(UserSession.user_id == user_id).delete(synchronize_session=False)


def get_token_from_cookie(request: Request) -> str:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Não autenticado", headers={"WWW-Authenticate": "Bearer"})
    return token.removeprefix("Bearer ")


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_session_token(token: str, *, verify_exp: bool = True) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM],
                      options={"require": ["exp", "iat", "sub", "sid", "tv"], "verify_exp": verify_exp})


def get_current_user(token: str = Depends(get_token_from_cookie), db: Session = Depends(get_db)) -> User:
    denied = HTTPException(status_code=401, detail="Sessão inválida ou expirada",
                           headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = decode_session_token(token)
    except jwt.PyJWTError:
        raise denied
    if not isinstance(payload.get("sid"), str) or type(payload.get("tv")) is not int:
        raise denied
    user = db.query(User).filter(User.auth_subject == payload["sub"]).first()
    if user is None or not user.is_active or user.token_version != payload["tv"]:
        raise denied
    now = utcnow()
    # Atualização condicional: uma sessão expirada ou revogada não é reativada.
    touched = db.execute(update(UserSession).where(
        UserSession.id == payload["sid"], UserSession.user_id == user.id,
        UserSession.token_version == user.token_version, UserSession.revoked_at.is_(None),
        UserSession.expires_at > now,
        UserSession.last_seen_at > now - timedelta(minutes=SESSION_IDLE_TIMEOUT_MINUTES),
    ).values(last_seen_at=now))
    if cast(CursorResult, touched).rowcount != 1:
        db.rollback()
        raise denied
    db.commit()
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ["admin", "dev"]:
        raise HTTPException(status_code=403, detail="Operação permitida apenas para administradores ou desenvolvedores")
    return current_user


def require_dev(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "dev":
        raise HTTPException(status_code=403, detail="Operação permitida apenas para desenvolvedores")
    return current_user


def create_initial_admin(db: Session) -> None:
    if not db.query(User).filter(User.username == "admin").first():
        password = os.getenv("ADMIN_INITIAL_PASSWORD")
        if not password:
            raise RuntimeError("FATAL: ADMIN_INITIAL_PASSWORD não configurada.")
        if not is_strong_password(password):
            raise RuntimeError(
                "ADMIN_INITIAL_PASSWORD deve atender à política de senha: pelo menos 8 caracteres, "
                "uma maiúscula, um número, um caractere especial (@$!%*?&) e no máximo 72 bytes."
            )
        db.add(User(username="admin", hashed_password=get_password_hash(password), role="admin"))
        db.commit()
