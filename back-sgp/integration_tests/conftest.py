"""PostgreSQL opt-in: banco de teste explícito e schema descartável por caso."""
import os
import re
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture
def postgres_engine():
    raw_url = os.getenv("TEST_POSTGRES_URL")
    if raw_url is None:
        pytest.skip("Integração PostgreSQL não executada: configure TEST_POSTGRES_URL para um banco exclusivo de teste.")
    try:
        url = make_url(raw_url)
    except Exception:
        pytest.fail("TEST_POSTGRES_URL inválida; nenhuma conexão foi aberta.", pytrace=False)
    if (
        url.drivername not in {"postgresql", "postgresql+psycopg2"}
        or not re.fullmatch(r"(?:test_[a-z0-9_]+|[a-z0-9_]+_test(?:_[a-z0-9_]+)?)", url.database or "")
        or url.query
    ):
        pytest.fail(
            "TEST_POSTGRES_URL deve indicar PostgreSQL, banco test_* ou *_test[_*], sem parâmetros adicionais.",
            pytrace=False,
        )

    schema = f"sgp_test_{uuid4().hex}"
    admin_engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 5})
    isolated_engine = None
    created = False
    try:
        # A identidade é conferida antes da primeira operação de escrita.
        # URL presente com erro de conexão causa falha, nunca skip ou fallback SQLite.
        with admin_engine.begin() as connection:
            assert connection.execute(text("SELECT current_database()")).scalar_one() == url.database
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        isolated_engine = create_engine(
            url, hide_parameters=True, pool_size=3, max_overflow=0,
            connect_args={
                "connect_timeout": 5,
                "options": f"-c search_path={schema} -c statement_timeout=10000 -c lock_timeout=8000",
            },
        )
        with isolated_engine.connect() as connection:
            assert connection.dialect.name == "postgresql"
            assert connection.execute(text("SELECT current_schema()")).scalar_one() == schema
        yield isolated_engine
    finally:
        if isolated_engine is not None:
            isolated_engine.dispose()
        try:
            if created:
                # Nome criado nesta fixture, nunca recebido pela URL ou por configuração.
                assert re.fullmatch(r"sgp_test_[0-9a-f]{32}", schema)
                with admin_engine.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            admin_engine.dispose()


@pytest.fixture
def history_table(postgres_engine, monkeypatch):
    # Importa somente o mapeamento; não inicia FastAPI nem lê .env do usuário.
    # A engine global criada no import não é utilizada: toda operação usa a
    # engine PostgreSQL acima, cujo search_path é exclusivo deste teste.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DATABASE_URL", postgres_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    from app.models.user import User
    from app.models.tabelas_salariais import HistoricoCalculo

    User.__table__.create(postgres_engine)
    HistoricoCalculo.__table__.create(postgres_engine)
    with postgres_engine.begin() as connection:
        connection.execute(User.__table__.insert(), [
            {"id": 1, "username": "synthetic_one", "hashed_password": "synthetic-not-a-login"},
            {"id": 2, "username": "synthetic_two", "hashed_password": "synthetic-not-a-login"},
        ])
    return HistoricoCalculo.__table__
