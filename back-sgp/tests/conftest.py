"""
conftest.py — Configuração compartilhada para todos os testes.

Cria um banco SQLite em memória por sessão de teste, substituindo
o banco de produção via override de dependência do FastAPI.
"""
import os

# Deve ser setado ANTES de qualquer import do app para desabilitar o rate limiter
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-only-secret-key-at-least-32-characters"
os.environ["ADMIN_INITIAL_PASSWORD"] = "TestOnly@1234"
os.environ["ENVIRONMENT"] = "testing"
os.environ["ENCRYPTION_KEY"] = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.user import User
from app.services.auth_service import get_password_hash


# ─────────────────────────────────────────────────────────────
# Gerador de PDFs mockados automático para testes
# ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def gerador_pdfs_teste(tmp_path_factory):
    """Gera documentos somente em uma pasta temporária de teste."""
    from scripts import gerar_pdfs_mockados
    base_dir = tmp_path_factory.mktemp("pdfs")
    for nome, gerar in {
        "pdf_substituicao.pdf": gerar_pdfs_mockados.gerar_substituicao,
        "pdf_abono_permanencia.pdf": gerar_pdfs_mockados.gerar_abono,
        "progressao_teste_01.pdf": gerar_pdfs_mockados.gerar_progressao,
    }.items():
        gerar().output(str(base_dir / nome))
    return base_dir

# ─────────────────────────────────────────────────────────────
# Banco SQLite em memória — isolado por sessão de teste
# ─────────────────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite:///:memory:"

engine_test = create_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Cria todas as tabelas no banco em memória antes dos testes."""
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture()
def db_session(monkeypatch):
    """Sessão de banco limpa para cada teste (rollback ao final)."""
    connection = engine_test.connect()
    transaction = connection.begin()
    # SQLite adia BEGIN; materializá-lo impede que RELEASE SAVEPOINT
    # confirme os dados fora da transação que isola cada teste.
    connection.exec_driver_sql("BEGIN")
    monkeypatch.setattr("app.database.SessionLocal", sessionmaker(bind=connection))
    session = TestingSessionLocal(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session, monkeypatch):
    """TestClient do FastAPI com banco de dados sobrescrito."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def test_lifespan(app):
        yield

    monkeypatch.setattr(app.router, "lifespan_context", test_lifespan)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_user(db_session) -> User:
    """Cria e retorna um usuário admin no banco de teste."""
    user = User(
        username="test_admin",
        hashed_password=get_password_hash("Admin@123"),
        role="admin",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def regular_user(db_session) -> User:
    """Cria e retorna um usuário comum no banco de teste."""
    user = User(
        username="test_user",
        hashed_password=get_password_hash("User@123"),
        role="user",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def dev_user(db_session) -> User:
    """Cria e retorna um usuário dev no banco de teste."""
    user = User(
        username="test_dev",
        hashed_password=get_password_hash("Dev@123"),
        role="dev",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest.fixture()
def auth_client_admin(client, admin_user):
    """TestClient já autenticado como admin (cookie de sessão setado)."""
    response = client.post(
        "/api/auth/login",
        json={"username": "test_admin", "password": "Admin@123"},
    )
    assert response.status_code == 200, f"Login admin falhou: {response.json()}"
    return client


@pytest.fixture()
def auth_client_user(client, regular_user):
    """TestClient já autenticado como usuário comum."""
    response = client.post(
        "/api/auth/login",
        json={"username": "test_user", "password": "User@123"},
    )
    assert response.status_code == 200, f"Login user falhou: {response.json()}"
    return client


@pytest.fixture()
def auth_client_dev(client, dev_user):
    """TestClient já autenticado como dev."""
    response = client.post(
        "/api/auth/login",
        json={"username": "test_dev", "password": "Dev@123"},
    )
    assert response.status_code == 200, f"Login dev falhou: {response.json()}"
    return client


@pytest.fixture
def salary_reference(db_session):
    """Referências exclusivamente sintéticas, com datas e dimensões explícitas."""
    from app.schemas.referencias_salariais import ReferenciaEntrada, ConsultaSalarial
    from app.services.salary_references import salvar_referencia

    def create(**overrides):
        values = dict(carreira="MAGISTERIO_SUPERIOR", vinculo="EFETIVO", jornada="40H",
                      versao_carreira="ESTRUTURA SINTÉTICA", classe_docente="Adjunto", nivel_docente=1,
                      inicio_vigencia="2026-01-15", fim_vigencia=None, vencimento_basico="3000",
                      fonte="Fonte sintética conferida", estado="CONFIRMADA", retribuicoes=[])
        values.update(overrides)
        item = salvar_referencia(db_session, ReferenciaEntrada.model_validate(values), 1)
        db_session.flush()
        consulta = ConsultaSalarial.model_validate({**{k: v for k, v in values.items() if k in ConsultaSalarial.model_fields},
                                                   "data_referencia": values["inicio_vigencia"]})
        return item, consulta
    return create
