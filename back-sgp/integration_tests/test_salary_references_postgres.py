"""Numeric e exclusão de vigências reais; banco explícito e schema descartável."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from queue import Queue

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db.salary_reference_migration import migrate_salary_references
from app.models.referencias_salariais import EstruturaRemuneratoria, ReferenciaSalarial


def test_pg_lookup_keeps_vb_and_rt_in_same_snapshot(postgres_engine):
    from sqlalchemy import event, update
    from sqlalchemy.orm import Session

    from app.models.referencias_salariais import RetribuicaoReferencia
    from app.schemas.referencias_salariais import ConsultaSalarial
    from app.services.salary_references import resolve_salary

    migrate_salary_references(postgres_engine)
    query = ConsultaSalarial(
        carreira="MAGISTERIO_SUPERIOR", vinculo="EFETIVO", jornada="40H",
        versao_carreira="SINTETICA", classe_docente="Associado", nivel_docente=3,
        data_referencia=date(2026, 4, 1),
    )
    with postgres_engine.begin() as conn:
        structure = conn.execute(EstruturaRemuneratoria.__table__.insert().values(
            chave=query.chave_estrutura(), **query.model_dump(exclude={"data_referencia"}),
        ).returning(EstruturaRemuneratoria.id)).scalar_one()
        reference = conn.execute(ReferenciaSalarial.__table__.insert().values(
            estrutura_id=structure, inicio_vigencia=date(2026, 4, 1),
            vencimento_basico=Decimal(3000), estado="CONFIRMADA", fonte="Sintética",
        ).returning(ReferenciaSalarial.id)).scalar_one()
        conn.execute(RetribuicaoReferencia.__table__.insert().values(
            referencia_id=reference, titulacao="Mestrado", titulacao_chave="mestrado", valor=Decimal(1000),
        ))
    changed = False

    def concurrent_edit(conn, cursor, statement, parameters, context, executemany):
        nonlocal changed
        if changed or not statement.lstrip().upper().startswith("SELECT") or "FROM referencia_salarial" not in statement:
            return
        changed = True
        with postgres_engine.begin() as writer:
            writer.execute(update(ReferenciaSalarial).values(vencimento_basico=Decimal(5000)))
            writer.execute(update(RetribuicaoReferencia).values(valor=Decimal(2000)))

    event.listen(postgres_engine, "after_cursor_execute", concurrent_edit)
    try:
        with Session(postgres_engine) as reader:
            assert resolve_salary(reader, query, "Mestrado")[0] == Decimal(4000)
            assert changed
            assert resolve_salary(reader, query, "Mestrado")[0] == Decimal(7000)
    finally:
        event.remove(postgres_engine, "after_cursor_execute", concurrent_edit)


def test_pg_migration_numeric_dryrun_and_legacy_preservation(postgres_engine):
    with postgres_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE tabela_vencimento_basico (id INTEGER PRIMARY KEY, classe TEXT, nivel INTEGER, ano INTEGER, valor DOUBLE PRECISION)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO tabela_vencimento_basico VALUES (1, 'D', 1, 2020, 3000.25)"
            )
        )
    simulated = migrate_salary_references(postgres_engine, dry_run=True)
    assert simulated["registros"][0]["estado"] == "PENDENTE"
    assert not inspect(postgres_engine).has_table("referencia_salarial")
    migrate_salary_references(postgres_engine)
    assert migrate_salary_references(postgres_engine)["inalterados"] == 1
    with postgres_engine.begin() as conn:
        assert conn.execute(
            text("SELECT classe, nivel, ano, valor FROM tabela_vencimento_basico")
        ).one() == ("D", 1, 2020, 3000.25)
        assert (
            conn.execute(text("SELECT COUNT(*) FROM referencia_salarial")).scalar_one()
            == 0
        )
        structure = conn.execute(
            EstruturaRemuneratoria.__table__.insert()
            .values(
                chave="sintetica",
                carreira="TAE",
                vinculo="EFETIVO",
                jornada="40H",
                versao_carreira="sintética",
                classificacao_tae="D",
                padrao_tae=1,
            )
            .returning(EstruturaRemuneratoria.id)
        ).scalar_one()
        conn.execute(
            ReferenciaSalarial.__table__.insert().values(
                estrutura_id=structure,
                inicio_vigencia=date(2026, 4, 1),
                vencimento_basico=Decimal("9876543210.123456789012"),
                estado="CONFIRMADA",
                fonte="sintética",
            )
        )
        assert conn.execute(
            select(ReferenciaSalarial.vencimento_basico)
        ).scalar_one() == Decimal("9876543210.123456789012")
        column = next(
            c
            for c in inspect(conn).get_columns("referencia_salarial")
            if c["name"] == "vencimento_basico"
        )
        assert column["type"].precision == 30 and column["type"].scale == 12


def test_pg_exclusion_rejects_concurrent_overlap_and_keeps_adjacent_intervals(
    postgres_engine,
):
    migrate_salary_references(postgres_engine)
    with postgres_engine.begin() as conn:
        structure = conn.execute(
            EstruturaRemuneratoria.__table__.insert()
            .values(
                chave="sintetica",
                carreira="MAGISTERIO_SUPERIOR",
                vinculo="EFETIVO",
                jornada="DE",
                versao_carreira="sintética",
                classe_docente="Adjunto",
                nivel_docente=1,
            )
            .returning(EstruturaRemuneratoria.id)
        ).scalar_one()
    values = {
        "estrutura_id": structure,
        "inicio_vigencia": date(2026, 4, 1),
        "fim_vigencia": date(2026, 4, 30),
        "vencimento_basico": Decimal("3000.25"),
        "estado": "CONFIRMADA",
        "fonte": "sintética",
    }
    pid_queue = Queue()

    def competing_transaction():
        with postgres_engine.connect() as conn:
            transaction = conn.begin()
            pid_queue.put(conn.execute(text("SELECT pg_backend_pid()")).scalar_one())
            try:
                conn.execute(
                    ReferenciaSalarial.__table__.insert().values(
                        {**values, "inicio_vigencia": date(2026, 4, 15)}
                    )
                )
            except IntegrityError as exc:
                transaction.rollback()
                return exc.orig.pgcode, exc.orig.diag.constraint_name
            finally:
                if transaction.is_active:
                    transaction.rollback()
        pytest.fail("Sobreposição concorrente foi aceita.")

    with (
        postgres_engine.connect() as first,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        transaction = first.begin()
        try:
            first.execute(ReferenciaSalarial.__table__.insert().values(**values))
            competing = executor.submit(competing_transaction)
            pid = pid_queue.get(timeout=5)
            waiting = False
            deadline = time.monotonic() + 5
            with postgres_engine.connect() as observer:
                while time.monotonic() < deadline:
                    waiting = observer.execute(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=:pid AND NOT granted)"
                        ),
                        {"pid": pid},
                    ).scalar_one()
                    if waiting:
                        break
                    if competing.done():
                        competing.result()
                        pytest.fail(
                            "A concorrente terminou sem aguardar a transação aberta."
                        )
                    time.sleep(0.02)
            assert waiting
            transaction.commit()
            assert competing.result(timeout=5) == ("23P01", "ex_referencia_vigencia")
        finally:
            if transaction.is_active:
                transaction.rollback()
    with postgres_engine.begin() as conn:
        assert (
            conn.execute(text("SELECT COUNT(*) FROM referencia_salarial")).scalar_one()
            == 1
        )
        conn.execute(
            ReferenciaSalarial.__table__.insert().values(
                {**values, "inicio_vigencia": date(2026, 5, 1), "fim_vigencia": None}
            )
        )
    with pytest.raises(IntegrityError), postgres_engine.begin() as conn:
        conn.execute(
            ReferenciaSalarial.__table__.update()
            .where(ReferenciaSalarial.inicio_vigencia == date(2026, 5, 1))
            .values(inicio_vigencia=date(2026, 4, 30))
        )
