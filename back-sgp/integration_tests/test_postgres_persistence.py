"""Migração e concorrência reais; esta suíte não usa tests/conftest.py."""
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from uuid import uuid4

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db.calculation_migration import migrate_calculation_schema


def test_migracao_aditiva_postgresql_preserva_dados_e_pode_repetir(postgres_engine):
    with postgres_engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE historico_calculo (id INTEGER PRIMARY KEY, user_id INTEGER, resultado_json TEXT)"
        ))
        connection.execute(text(
            "INSERT INTO historico_calculo VALUES (1, 7, 'sintetico-legado-1'), (2, 7, 'sintetico-legado-2')"
        ))
    migrate_calculation_schema(postgres_engine)
    migrate_calculation_schema(postgres_engine)

    with postgres_engine.connect() as connection:
        columns = inspect(connection).get_columns("historico_calculo")
        indexes = inspect(connection).get_indexes("historico_calculo")
        assert [column["name"] for column in columns].count("idempotency_key") == 1
        assert connection.execute(text(
            "SELECT id, user_id, resultado_json, idempotency_key FROM historico_calculo ORDER BY id"
        )).all() == [(1, 7, "sintetico-legado-1", None), (2, 7, "sintetico-legado-2", None)]
        index = next(index for index in indexes if index["name"] == "uq_historico_requisicao")
        assert index["unique"]
        assert index["column_names"] == ["user_id", "idempotency_key"]

    key = str(uuid4())
    with postgres_engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO historico_calculo (id, user_id, idempotency_key) VALUES (3, 7, :key)"
        ), {"key": key})
    with pytest.raises(IntegrityError) as conflict:
        with postgres_engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO historico_calculo (id, user_id, idempotency_key) VALUES (4, 7, :key)"
            ), {"key": key})
    assert conflict.value.orig.pgcode == "23505"
    assert conflict.value.orig.diag.constraint_name == "uq_historico_requisicao"


def test_migracao_sem_tabela_legada_nao_cria_estruturas(postgres_engine):
    migrate_calculation_schema(postgres_engine)
    with postgres_engine.connect() as connection:
        assert inspect(connection).get_table_names() == []


def test_requisicoes_concorrentes_conflitam_e_rollback_preserva_um_historico(postgres_engine, history_table):
    key, rolled_back_key = str(uuid4()), str(uuid4())
    contender_pid = Queue()

    def competing_transaction():
        with postgres_engine.connect() as connection:
            transaction = connection.begin()
            try:
                contender_pid.put(connection.execute(text("SELECT pg_backend_pid()")).scalar_one())
                # Esta primeira escrita deve desaparecer junto com a transação
                # que falhar ao tentar salvar a mesma requisição concorrente.
                connection.execute(history_table.insert().values(user_id=1, idempotency_key=rolled_back_key))
                connection.execute(history_table.insert().values(user_id=1, idempotency_key=key))
            except IntegrityError as error:
                transaction.rollback()
                assert connection.execute(text("SELECT 1")).scalar_one() == 1
                return error.orig.pgcode, error.orig.diag.constraint_name
            finally:
                if transaction.is_active:
                    transaction.rollback()
        pytest.fail("A segunda conexão salvou uma requisição já reservada pela primeira.")

    with postgres_engine.connect() as first, ThreadPoolExecutor(max_workers=1) as executor:
        transaction = first.begin()
        try:
            first_pid = first.execute(text("SELECT pg_backend_pid()")).scalar_one()
            first.execute(history_table.insert().values(user_id=1, idempotency_key=key))
            competing = executor.submit(competing_transaction)
            second_pid = contender_pid.get(timeout=5)
            assert first_pid != second_pid
            # Observa o bloqueio real do segundo backend antes de confirmar o
            # primeiro. Não depende de uma pausa arbitrária para simular corrida.
            deadline = time.monotonic() + 5
            waiting = False
            with postgres_engine.connect() as observer:
                while time.monotonic() < deadline:
                    waiting = observer.execute(text(
                        "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid = :pid AND NOT granted)"
                    ), {"pid": second_pid}).scalar_one()
                    if waiting:
                        break
                    if competing.done():
                        competing.result()
                        pytest.fail("A segunda conexão terminou antes de aguardar o bloqueio.")
                    time.sleep(0.02)
            assert waiting, "Não foi observado bloqueio concorrente no PostgreSQL."
            transaction.commit()
            assert competing.result(timeout=5) == ("23505", "uq_historico_requisicao")
        finally:
            if transaction.is_active:
                transaction.rollback()

    with postgres_engine.begin() as connection:
        assert connection.execute(select(history_table.c.user_id, history_table.c.idempotency_key)).all() == [(1, key)]
        # A chave pertence a cada usuário; registros legados sem chave continuam válidos.
        connection.execute(history_table.insert(), [
            {"user_id": 2, "idempotency_key": key},
            {"user_id": 1, "idempotency_key": None},
            {"user_id": 1, "idempotency_key": None},
        ])
        assert connection.execute(text("SELECT COUNT(*) FROM historico_calculo")).scalar_one() == 4
