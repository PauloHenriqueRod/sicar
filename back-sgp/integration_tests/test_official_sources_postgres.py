"""Componentes de função: Numeric e exclusão concorrente em PostgreSQL real."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from queue import Queue

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.salary_reference_migration import migrate_salary_references
from app.models.fontes_oficiais import (
    EstruturaFuncao,
    EstruturaIQ,
    ReferenciaFuncao,
    ReferenciaIQ,
    migrate_official_sources,
)


@pytest.mark.parametrize("kind", ["FUNCAO", "IQ"])
def test_reference_numeric_and_concurrent_exclusion(postgres_engine, kind):
    reference_model = ReferenciaIQ if kind == "IQ" else ReferenciaFuncao
    structure_model = EstruturaIQ if kind == "IQ" else EstruturaFuncao
    amount = (
        Decimal("12.123456789012") if kind == "IQ" else Decimal("1234.123456789012")
    )
    migrate_salary_references(postgres_engine)
    migrate_official_sources(postgres_engine)
    migrate_official_sources(postgres_engine)
    with postgres_engine.begin() as connection:
        structure = connection.execute(
            structure_model.__table__.insert()
            .values(
                **(
                    {"chave": "synthetic-iq", "titulacao": "Doutorado sintético"}
                    if kind == "IQ"
                    else {
                        "chave": "synthetic-fg-1",
                        "tipo_funcao": "FG",
                        "codigo_funcao": "1",
                        "modalidade": "PADRAO_CONFERIDO",
                        "componente": "FUNCAO",
                    }
                )
            )
            .returning(structure_model.id)
        ).scalar_one()
    values = {
        "estrutura_id": structure,
        "inicio_vigencia": date(2019, 1, 1),
        "fim_vigencia": date(2026, 3, 31),
        "valor": amount,
        "fonte": "Sintética",
        "conferido_por": 1,
        "conferido_em": datetime(2026, 10, 26, 12),
    }
    queue = Queue()

    def competing_insert():
        with postgres_engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            queue.put(connection.execute(text("SELECT pg_backend_pid()")).scalar_one())
            try:
                connection.execute(
                    reference_model.__table__.insert().values(
                        {**values, "inicio_vigencia": date(2020, 1, 1)}
                    )
                )
            except IntegrityError as exc:
                transaction.rollback()
                return exc.orig.pgcode, exc.orig.diag.constraint_name
            finally:
                if transaction.is_active:
                    transaction.rollback()
        raise AssertionError("Sobreposição concorrente foi aceita.")

    with (
        postgres_engine.connect() as first,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        transaction = first.begin()
        try:
            first.execute(reference_model.__table__.insert().values(**values))
            competing = executor.submit(competing_insert)
            pid = queue.get(timeout=5)
            deadline = time.monotonic() + 5
            waiting = False
            with postgres_engine.connect() as observer:
                while time.monotonic() < deadline:
                    waiting = observer.execute(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=:pid AND NOT granted)"
                        ),
                        {"pid": pid},
                    ).scalar_one()
                    if waiting or competing.done():
                        break
                    time.sleep(0.02)
            assert waiting
            transaction.commit()
            assert competing.result(timeout=5) == (
                "23P01",
                "ex_iq_vigencia" if kind == "IQ" else "ex_funcao_vigencia",
            )
        finally:
            if transaction.is_active:
                transaction.rollback()
    with postgres_engine.begin() as connection:
        assert connection.execute(select(reference_model.valor)).scalar_one() == amount
        connection.execute(
            reference_model.__table__.insert().values(
                {**values, "inicio_vigencia": date(2026, 4, 1), "fim_vigencia": None}
            )
        )
