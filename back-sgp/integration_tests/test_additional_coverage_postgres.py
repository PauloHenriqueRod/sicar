"""Reserva concorrente real, opt-in e isolada no schema temporário do CI."""

import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from types import SimpleNamespace

from sqlalchemy import select, text
from sqlalchemy.orm import Session


def test_additional_cross_flow_claim_waits_and_rejects_overlap(
    postgres_engine, history_table
):
    from app.models.cobertura_adicionais import (
        CoberturaAdicional,
        EscopoAdicional,
        RevisaoCalculo,
    )
    from app.models.tabelas_salariais import HistoricoCalculo
    from app.services.cobertura_adicionais import registrar_cobertura
    from app.services.pendencias import PendenciaApuracao

    for model in (EscopoAdicional, CoberturaAdicional, RevisaoCalculo):
        model.__table__.create(postgres_engine)
    user = SimpleNamespace(id=1, role="user")
    data = SimpleNamespace(matricula="000999", substitui_historico_id=None)
    result = {
        "segmentos": [
            {
                "inicio": "2024-02-01",
                "ultimo_dia_considerado": "2024-02-29",
                "dias_computados": 29,
                "estado": {
                    "adicional": {
                        "identificador": "ATO-SINTETICO",
                        "inicio_vigencia": "2020-01-01",
                    }
                },
                "parcelas": [
                    {"formula": "ADICIONAL_CONFIRMADO", "incluido_principal": True}
                ],
            }
        ]
    }
    queue = Queue()

    def competing():
        with Session(postgres_engine) as session:
            queue.put(session.scalar(text("SELECT pg_backend_pid()")))
            record = HistoricoCalculo(
                user_id=1,
                tipo_calculo="progressao",
                matricula="999",
                resultado_json="synthetic",
            )
            session.add(record)
            session.flush()
            try:
                registrar_cobertura(session, data, result, record, user)
            except PendenciaApuracao as exc:
                session.rollback()
                return exc.codigo
            session.rollback()
            raise AssertionError("A reserva concorrente sobreposta foi aceita.")

    with (
        Session(postgres_engine) as first,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        record = HistoricoCalculo(
            user_id=1,
            tipo_calculo="insalubridade",
            matricula="999",
            resultado_json="synthetic",
        )
        first.add(record)
        first.flush()
        registrar_cobertura(first, data, result, record, user)
        future = executor.submit(competing)
        try:
            pid = queue.get(timeout=5)
            waiting = False
            deadline = time.monotonic() + 5
            with postgres_engine.connect() as observer:
                while time.monotonic() < deadline:
                    waiting = observer.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=:pid AND NOT granted)"
                        ),
                        {"pid": pid},
                    )
                    if waiting:
                        break
                    if future.done():
                        future.result()
                    time.sleep(0.02)
            assert waiting, "A concorrente deveria aguardar a reserva não confirmada."
            first.commit()
        finally:
            first.rollback()
        assert future.result(timeout=10) == "adicional_ja_apurado"
    with Session(postgres_engine) as session:
        assert len(session.scalars(select(CoberturaAdicional)).all()) == 1
        assert len(session.scalars(select(HistoricoCalculo)).all()) == 1
