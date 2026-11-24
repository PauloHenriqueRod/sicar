"""Configuração segura sem conexão com infraestrutura de produção."""
import pytest

from app.models.user import User
from app.security import configured_database_url, validate_production_config
from app.services.auth_service import create_initial_admin, verify_password


@pytest.mark.parametrize("url", [None, "", "   ", "sqlite:///sgp.db", "mysql://user:secret@localhost/sgp", "inválida", "postgresql://localhost"])
def test_producao_recusa_banco_ausente_ou_nao_postgresql(url, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    if url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(RuntimeError, match="DATABASE_URL") as error:
        configured_database_url()
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("driver", ["postgresql", "postgresql+psycopg2", "postgresql+psycopg"])
def test_producao_aceita_url_explicita_sem_abrir_conexao(driver, monkeypatch):
    url = f"{driver}://synthetic:synthetic@localhost/sgp_test"
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setenv("SECRET_KEY", "synthetic-production-test-key-32-bytes")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://rh.example.edu")
    assert configured_database_url() == url
    validate_production_config()


@pytest.mark.parametrize("environment", ["testing", "development"])
def test_ambientes_locais_continuam_aceitando_sqlite(environment, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    assert configured_database_url() == "sqlite://"
    monkeypatch.delenv("DATABASE_URL")
    assert configured_database_url() == "sqlite:///./sgp_dados.db"


def test_ambiente_desconhecido_nao_desativa_as_protecoes(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prodution")
    with pytest.raises(RuntimeError, match="ENVIRONMENT"):
        validate_production_config()


@pytest.mark.parametrize("password", [None, "", "Admin1!", "admin@123", "Admin@@@", "Admin123", "Á" * 35 + "A1@"])
def test_bootstrap_recusa_senha_fora_da_politica(password, db_session, monkeypatch):
    if password is None:
        monkeypatch.delenv("ADMIN_INITIAL_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", password)
    with pytest.raises(RuntimeError, match="ADMIN_INITIAL_PASSWORD"):
        create_initial_admin(db_session)
    assert db_session.query(User).filter_by(username="admin").first() is None


def test_bootstrap_cria_admin_com_senha_valida_e_preserva_conta_existente(db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "Synthetic@123")
    create_initial_admin(db_session)
    administrator = db_session.query(User).filter_by(username="admin").one()
    original = administrator.hashed_password
    assert administrator.role == "admin"
    assert verify_password("Synthetic@123", original)
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "fraca")
    create_initial_admin(db_session)
    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD")
    create_initial_admin(db_session)
    db_session.refresh(administrator)
    assert administrator.hashed_password == original
    assert db_session.query(User).filter_by(username="admin").count() == 1


def test_identidade_da_sessao_exige_autenticacao(client):
    assert client.get("/api/auth/me").status_code == 401


def test_identidade_da_sessao_retorna_somente_identificadores_publicos(auth_client_user, regular_user):
    response = auth_client_user.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == {"username": regular_user.username, "role": "user", "auth_subject": regular_user.auth_subject}


def test_identidade_da_sessao_recusa_sessao_revogada(auth_client_user, regular_user, db_session):
    from app.services.auth_service import revoke_user_sessions
    revoke_user_sessions(db_session, regular_user.id)
    db_session.commit()
    assert auth_client_user.get("/api/auth/me").status_code == 401
