import html
import re
import os
import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.utils.limiter import limiter
from app.utils.password_policy import is_strong_password
from app.models.user import AuditLog, TokenBlacklist, User, UserSession
from app.services.auth_service import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_user_session,
    decode_session_token,
    revoke_user_sessions,
    DUMMY_PASSWORD_HASH,
    get_current_user,
    get_password_hash,
    require_admin,
    require_dev,
    token_digest,
    verify_password,
)


def log_audit(db: Session, action: str, target: str | None = None, user_id: int | None = None, ip_address: str | None = None):
    """Confirma as alterações pendentes e sua auditoria na mesma transação."""
    try:
        log = AuditLog(action=action, target=target, user_id=user_id, ip_address=ip_address)
        db.add(log)
        db.commit()
    except Exception as exc:
        db.rollback()
        logging.getLogger(__name__).error("Falha ao registrar operação auditada: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Não foi possível registrar a operação. Tente novamente.")

router = APIRouter(prefix="/api/auth", tags=["Autenticação"])


@router.get("/me")
def minha_identidade(current_user: User = Depends(get_current_user)):
    """Reconcilia a identidade do cookie com o estado das abas do navegador."""
    return {"username": current_user.username, "role": current_user.role,
            "auth_subject": current_user.auth_subject}


class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    role: Literal["user", "admin", "dev"] = "user"

class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}

class PasswordReset(BaseModel):
    new_password: str

def set_session_cookie(response: Response, token: str):
    response.set_cookie(
        key="access_token", value=f"Bearer {token}", httponly=True,
        secure=os.getenv("ENVIRONMENT") == "production", samesite="strict",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, response: Response, payload: LoginRequest, db: Session = Depends(get_db)):
    # Serializa a contagem por conta também em instalações com vários workers.
    user = db.query(User).filter(User.username == payload.username).with_for_update().first()
    valid_password = verify_password(payload.password, user.hashed_password if user else DUMMY_PASSWORD_HASH)
    now = datetime.now(UTC).replace(tzinfo=None)
    lockout = user.lockout_until if user else None
    if lockout is not None and lockout.tzinfo is not None:
        lockout = lockout.astimezone(UTC).replace(tzinfo=None)
    locked = bool(lockout and lockout > now)
    ip = request.client.host if request.client else None
    if not user or not user.is_active or locked or not valid_password:
        action = "LOGIN_FAILED"
        if user and user.is_active and not locked:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.lockout_until = now + timedelta(minutes=15)
                action = "ACCOUNT_LOCKED"
        log_audit(db, action, user.username if user else None, user.id if user else None, ip)
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos",
                            headers={"WWW-Authenticate": "Bearer"})
    user.failed_login_attempts = 0
    user.lockout_until = None
    token = create_user_session(db, user)
    log_audit(db, "LOGIN_SUCCESS", user.username, user.id, ip)
    set_session_cookie(response, token)
    return {"message": "Login realizado com sucesso", "role": user.role, "username": user.username}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token", "").removeprefix("Bearer ")
    try:
        claims = decode_session_token(token, verify_exp=False)
    except (jwt.InvalidTokenError, ValueError, TypeError):
        claims = None
    if claims:
        session = db.query(UserSession).filter(UserSession.id == claims["sid"]).first()
        if session:
            session.revoked_at = datetime.now(UTC).replace(tzinfo=None)
            digest = token_digest(token)
            if not db.query(TokenBlacklist).filter(TokenBlacklist.token == digest).first():
                db.add(TokenBlacklist(token=digest))
            log_audit(db, "LOGOUT", user_id=session.user_id,
                      ip_address=request.client.host if request.client else None)
    response.delete_cookie(key="access_token", httponly=True,
                           secure=os.getenv("ENVIRONMENT") == "production", samesite="strict")
    return {"message": "Logout realizado com sucesso"}

@router.get("/usuarios", response_model=list[UserResponse])
def listar_usuarios(db: Session = Depends(get_db), current_admin: User = Depends(require_admin)):
    return db.query(User).all()

@router.post("/usuarios", response_model=UserResponse)
def criar_usuario(request: UserCreate, db: Session = Depends(get_db), current_admin: User = Depends(require_admin)):
    if request.role in ("admin", "dev") and current_admin.role != "dev":
        raise HTTPException(status_code=403, detail="Apenas desenvolvedores podem criar usuários privilegiados.")
    
    # Sanitização de Input: valida que o username só contém caracteres seguros
    sanitized_username = html.escape(request.username.strip())
    if not re.match(r'^[a-zA-Z0-9_]{3,50}$', sanitized_username):
        raise HTTPException(status_code=400, detail="O nome de usuário deve conter apenas letras, números e underscore (3 a 50 caracteres).")
    
    if db.query(User).filter(User.username == sanitized_username).first():
        raise HTTPException(status_code=400, detail="Usuário já existe")
    
    if not is_strong_password(request.password):
        raise HTTPException(status_code=400, detail="A senha deve ter no mínimo 8 caracteres, uma letra maiúscula, um número e um caractere especial (@$!%*?&)")
    
    hashed = get_password_hash(request.password)
    novo_user = User(username=sanitized_username, hashed_password=hashed, role=request.role)
    db.add(novo_user)
    log_audit(db, "USER_CREATED", novo_user.username, current_admin.id)
    db.refresh(novo_user)
    return novo_user

@router.put("/usuarios/{user_id}/reset-password")
def resetar_senha(user_id: int, request: PasswordReset, db: Session = Depends(get_db), current_admin: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    if user.role == "dev" and current_admin.role != "dev":
        raise HTTPException(status_code=403, detail="Apenas desenvolvedores podem alterar contas de desenvolvedores.")

    if not is_strong_password(request.new_password):
        raise HTTPException(status_code=400, detail="A senha deve ter no mínimo 8 caracteres, uma letra maiúscula, um número e um caractere especial (@$!%*?&)")
    
    user.hashed_password = get_password_hash(request.new_password)
    user.token_version += 1
    revoke_user_sessions(db, user.id)
    log_audit(db, "PASSWORD_RESET", user.username, current_admin.id)
    return {"message": "Senha redefinida com sucesso"}

@router.delete("/usuarios/{user_id}")
def excluir_usuario(user_id: int, db: Session = Depends(get_db), current_admin: User = Depends(require_admin)):
    if current_admin.id == user_id:
        raise HTTPException(status_code=400, detail="Você não pode excluir a si mesmo")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if user.role == "dev" and current_admin.role != "dev":
        raise HTTPException(status_code=403, detail="Apenas desenvolvedores podem excluir contas de desenvolvedores.")
    revoke_user_sessions(db, user.id)
    # Preserve historical calculations without retaining a deleted account reference.
    from app.models.tabelas_salariais import HistoricoCalculo
    db.query(HistoricoCalculo).filter(HistoricoCalculo.user_id == user.id).update({"user_id": None})
    db.delete(user)
    log_audit(db, "USER_DELETED", user.username, current_admin.id)
    return {"message": "Usuário excluído com sucesso"}

class AuditLogResponse(BaseModel):
    id: int
    user_id: int | None
    action: str
    target: str | None
    timestamp: datetime
    ip_address: str | None

    model_config = {"from_attributes": True}

@router.get("/audit-logs", response_model=list[AuditLogResponse])
def listar_audit_logs(db: Session = Depends(get_db), current_dev: User = Depends(require_dev)):
    return db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(200).all()


class ChangeMyPassword(BaseModel):
    current_password: str
    new_password: str


@router.put("/me/alterar-senha")
@limiter.limit("5/minute")
def alterar_minha_senha(
    payload: ChangeMyPassword,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")

    if not is_strong_password(payload.new_password):
        raise HTTPException(
            status_code=400,
            detail="A nova senha deve ter no mínimo 8 caracteres, uma letra maiúscula, um número e um caractere especial (@$!%*?&)"
        )

    current_user.hashed_password = get_password_hash(payload.new_password)
    current_user.token_version += 1
    revoke_user_sessions(db, current_user.id)
    token = create_user_session(db, current_user)
    log_audit(db, "PASSWORD_CHANGED_SELF", current_user.username, current_user.id, request.client.host if request.client else None)
    set_session_cookie(response, token)
    return {"message": "Senha alterada com sucesso"}
