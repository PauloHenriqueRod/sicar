import json
from datetime import timedelta
from unittest.mock import patch

import bcrypt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.db.security_migration import migrate_security_schema
from app.frontend import mount_frontend
from app.main import add_security_headers
from app.models.tabelas_salariais import HistoricoCalculo
from app.models.user import AuditLog, User, UserSession
from app.services import auth_service


def saved_calculation(client):
    response = client.post("/api/calcular", json={
        "tipo_calculo": "abono",
        "dados_extraidos": {"matricula": "DEMO-123", "valores_anuais": {"2026": [1000]}},
    })
    assert response.status_code == 200
    return response.json()


def test_token_nao_autentica_conta_recriada(auth_client_user, regular_user, db_session, admin_user):
    old_cookie = auth_client_user.cookies.get("access_token")
    old_subject = regular_user.auth_subject
    auth_client_user.post("/api/auth/login", json={"username": "test_admin", "password": "Admin@123"})
    assert auth_client_user.delete(f"/api/auth/usuarios/{regular_user.id}").status_code == 200
    assert auth_client_user.post("/api/auth/usuarios", json={
        "username": "test_user", "password": "Outra@1234", "role": "user",
    }).status_code == 200
    assert db_session.query(User).filter_by(username="test_user").one().auth_subject != old_subject
    auth_client_user.cookies.clear()
    auth_client_user.cookies.set("access_token", old_cookie)
    assert auth_client_user.get("/api/dashboard/stats").status_code == 401


@pytest.mark.parametrize("reason", ["idle", "absolute", "revoked", "missing"])
def test_servidor_rejeita_sessao_encerrada(auth_client_user, db_session, reason):
    session = db_session.query(UserSession).one()
    if reason == "idle":
        session.last_seen_at = auth_service.utcnow() - timedelta(minutes=auth_service.SESSION_IDLE_TIMEOUT_MINUTES)
    elif reason == "absolute":
        session.expires_at = auth_service.utcnow() - timedelta(seconds=1)
    elif reason == "revoked":
        session.revoked_at = auth_service.utcnow()
    else:
        db_session.delete(session)
    db_session.commit()
    assert auth_client_user.get("/api/dashboard/stats").status_code == 401


def test_atividade_renova_inatividade_sem_estender_prazo_absoluto(auth_client_user, db_session):
    session = db_session.query(UserSession).one()
    session.last_seen_at = auth_service.utcnow() - timedelta(minutes=10)
    before, expires = session.last_seen_at, session.expires_at
    db_session.commit()
    assert auth_client_user.get("/api/dashboard/stats").status_code == 200
    db_session.refresh(session)
    assert session.last_seen_at > before
    assert session.expires_at == expires


def test_logout_revoga_apenas_a_sessao_atual(auth_client_user, regular_user, db_session):
    other = auth_service.create_user_session(db_session, regular_user)
    db_session.commit()
    previous = auth_client_user.cookies.get("access_token")
    assert auth_client_user.post("/api/auth/logout").status_code == 200
    auth_client_user.cookies.set("access_token", previous)
    assert auth_client_user.get("/api/dashboard/stats").status_code == 401
    auth_client_user.cookies.set("access_token", f"Bearer {other}")
    assert auth_client_user.get("/api/dashboard/stats").status_code == 200


def test_login_mesma_resposta_e_verificacao_bcrypt_para_conta_inexistente_e_inativa(client, regular_user, db_session):
    regular_user.is_active = False
    db_session.commit()
    with patch("app.routers.auth_router.verify_password", wraps=auth_service.verify_password) as verify:
        missing = client.post("/api/auth/login", json={"username": "nao_existe", "password": "errada"})
        inactive = client.post("/api/auth/login", json={"username": "test_user", "password": "User@123"})
    assert verify.call_count == 2
    assert bcrypt.checkpw(b"errada", auth_service.DUMMY_PASSWORD_HASH.encode()) is False
    assert missing.status_code == inactive.status_code == 401
    assert missing.json() == inactive.json()


def test_falha_auditoria_desfaz_usuario_criado(auth_client_admin, db_session, monkeypatch):
    original = db_session.commit
    def fail_audit():
        if any(isinstance(obj, AuditLog) and obj.action == "USER_CREATED" for obj in db_session.new):
            raise RuntimeError("simulated audit storage failure")
        original()
    monkeypatch.setattr(db_session, "commit", fail_audit)
    response = auth_client_admin.post("/api/auth/usuarios", json={"username": "novo_user", "password": "Senha@123"})
    assert response.status_code == 503
    assert db_session.query(User).filter_by(username="novo_user").first() is None


def test_falha_auditoria_login_nao_emite_cookie_nem_sessao(client, regular_user, db_session, monkeypatch):
    monkeypatch.setattr(db_session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("simulated failure")))
    response = client.post("/api/auth/login", json={"username": "test_user", "password": "User@123"})
    assert response.status_code == 503
    assert "set-cookie" not in response.headers
    assert db_session.query(UserSession).count() == 0


def test_falha_auditoria_reset_preserva_senha_e_sessoes(auth_client_admin, regular_user, db_session, monkeypatch):
    token = auth_service.create_user_session(db_session, regular_user)
    db_session.commit()
    original_hash, original_version = regular_user.hashed_password, regular_user.token_version
    original_commit = db_session.commit
    def fail_audit():
        if any(isinstance(obj, AuditLog) and obj.action == "PASSWORD_RESET" for obj in db_session.new):
            raise RuntimeError("simulated failure")
        original_commit()
    monkeypatch.setattr(db_session, "commit", fail_audit)
    response = auth_client_admin.put(f"/api/auth/usuarios/{regular_user.id}/reset-password", json={"new_password": "Outra@1234"})
    assert response.status_code == 503
    db_session.refresh(regular_user)
    assert regular_user.hashed_password == original_hash
    assert regular_user.token_version == original_version
    auth_client_admin.cookies.clear()
    auth_client_admin.cookies.set("access_token", f"Bearer {token}")
    assert auth_client_admin.get("/api/dashboard/stats").status_code == 200


def test_falha_auditoria_tabela_desfaz_valor(auth_client_admin, db_session, monkeypatch):
    from app.models.tabelas_salariais import TabelaVencimentoBasico
    row = TabelaVencimentoBasico(classe="DEMO", nivel=1, ano=2026, valor=1000)
    db_session.add(row)
    db_session.commit()
    original_commit = db_session.commit
    def fail_audit():
        if any(isinstance(obj, AuditLog) and obj.action.startswith("TABELA_") for obj in db_session.new):
            raise RuntimeError("simulated failure")
        original_commit()
    monkeypatch.setattr(db_session, "commit", fail_audit)
    response = auth_client_admin.put(f"/api/tabelas/vencimentos/{row.id}", json={"valor": 2000})
    assert response.status_code == 503
    db_session.refresh(row)
    assert row.valor == 1000


def test_exportacao_rejeita_totais_do_cliente_e_usa_snapshot(auth_client_user):
    saved = saved_calculation(auth_client_user)
    assert auth_client_user.post("/api/exportar-pdf", json={
        "historico_id": saved["historico_id"], "dados_extraidos": {"resultado_calculo": {"total": 999999}},
    }).status_code == 422
    from app.services.pdf_export import generate_pdf_report
    with patch("app.routers.calculos_router.generate_pdf_report", wraps=generate_pdf_report) as generate:
        response = auth_client_user.post("/api/exportar-pdf", json={"historico_id": saved["historico_id"]})
    assert response.status_code == 200
    assert generate.call_args.kwargs["resultado_calculo"] == saved["resultado_calculo"]
    assert generate.call_args.kwargs["dados_extraidos"]["matricula"] == "DEMO-123"


def test_exportacao_isola_usuarios_e_permite_admin(auth_client_user, admin_user, db_session):
    saved = saved_calculation(auth_client_user)
    other = User(username="outra_conta", hashed_password=admin_user.hashed_password, role="user")
    db_session.add(other)
    db_session.commit()
    assert auth_client_user.post("/api/auth/login", json={"username": other.username, "password": "Admin@123"}).status_code == 200
    denied = auth_client_user.post("/api/exportar-pdf", json={"historico_id": saved["historico_id"]})
    absent = auth_client_user.post("/api/exportar-pdf", json={"historico_id": saved["historico_id"] + 10000})
    assert denied.status_code == absent.status_code == 404
    assert denied.json() == absent.json()
    auth_client_user.post("/api/auth/login", json={"username": "test_admin", "password": "Admin@123"})
    assert auth_client_user.post("/api/exportar-pdf", json={"historico_id": saved["historico_id"]}).status_code == 200


def test_historico_legado_visivel_mas_exige_recalculo_para_exportar(auth_client_user, db_session):
    saved = saved_calculation(auth_client_user)
    row = db_session.get(HistoricoCalculo, saved["historico_id"])
    from app.utils.crypto import encrypt_data
    row.resultado_json = encrypt_data(json.dumps(saved["resultado_calculo"]))
    db_session.commit()
    assert json.loads(auth_client_user.get("/api/historico").json()[0]["resultado_json"]) == saved["resultado_calculo"]
    assert auth_client_user.post("/api/exportar-pdf", json={"historico_id": row.id}).status_code == 409


@pytest.mark.parametrize("has_version", [True, False])
def test_migracao_legada_idempotente(has_version):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        if has_version:
            connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, token_version INTEGER)"))
            connection.execute(text("INSERT INTO users VALUES (1, NULL), (2, 1)"))
        else:
            connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO users VALUES (1), (2)"))
    migrate_security_schema(engine)
    with engine.connect() as connection:
        before = connection.execute(text("SELECT auth_subject, token_version FROM users ORDER BY id")).all()
    migrate_security_schema(engine)
    with engine.connect() as connection:
        after = connection.execute(text("SELECT auth_subject, token_version FROM users ORDER BY id")).all()
    assert before == after
    assert len({row[0] for row in before}) == 2
    assert all(row[1] == 1 for row in before)
    engine.dispose()


def test_html_producao_recebe_csp_e_nao_confia_forwarded_proto(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<!doctype html><html><body>SICAR</body></html>", encoding="utf-8")
    app = FastAPI()
    app.middleware("http")(add_security_headers)
    mount_frontend(app, tmp_path)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert response.headers["cache-control"] == "no-store"
        assert "max-age=" in response.headers["strict-transport-security"]
        assert client.get("/calculos").status_code == 200
        assert client.get("/api/inexistente").status_code == 404
        assert client.get("/assets/inexistente.js").status_code == 404
        response = client.get("http://testserver/", headers={"x-forwarded-proto": "https"}, follow_redirects=False)
        assert response.status_code == 301


def test_cookie_producao_seguro(client, regular_user, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    response = client.post("https://testserver/api/auth/login", json={"username": "test_user", "password": "User@123"})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie
