"""Serializa a reserva de períodos entre progressão e adicionais na mesma transação."""

import hashlib
import hmac
import json
import os
from datetime import date

from sqlalchemy import select

from app.models.cobertura_adicionais import (
    CoberturaAdicional,
    EscopoAdicional,
    RevisaoCalculo,
)
from app.models.tabelas_salariais import HistoricoCalculo
from app.services.pendencias import PendenciaApuracao
from app.utils.employee_identity import employee_key as identidade


def chave(matricula, origem, tipo):
    value = json.dumps(
        [
            "cobertura_adicional_v1",
            identidade(matricula),
            origem.strip().casefold(),
            tipo,
        ],
        ensure_ascii=False,
    )
    return hmac.new(
        os.environ["ENCRYPTION_KEY"].encode(), value.encode(), hashlib.sha256
    ).hexdigest()


def origens_ativas(segment, resultado, first, last):
    # A origem também participa da diferença, inclusive se o destino cessou.
    for state in (segment.get("estado", {}), resultado.get("estado_origem", {})):
        item = state.get("adicional")
        if (
            item
            and item.get("inicio_vigencia")
            and first >= item["inicio_vigencia"]
            and (not item.get("fim_vigencia") or last <= item["fim_vigencia"])
        ):
            yield item["identificador"]


def parcelas(matricula, resultado):
    claims = []
    segments = {
        segment.get("id"): segment for segment in resultado.get("segmentos", [])
    }
    for segment in resultado.get("segmentos", []):
        if segment["dias_computados"] and any(
            p["formula"] == "ADICIONAL_CONFIRMADO" and p.get("incluido_principal", True)
            for p in segment.get("parcelas", [])
        ):
            first, last = segment["inicio"], segment["ultimo_dia_considerado"]
            # Mesma concessão nos dois papéis reserva o intervalo uma única vez.
            keys = {
                chave(matricula, origin, "PRINCIPAL")
                for origin in origens_ativas(segment, resultado, first, last)
            }
            for key in sorted(keys):
                claims.append(
                    (
                        key,
                        date.fromisoformat(first),
                        date.fromisoformat(last),
                    )
                )
    for event in resultado.get("reflexos", []):
        if "ADICIONAL_CONFIRMADO" in event["formulas_base"]:
            interval = event["periodo_referencia"]
            segment = segments.get(event.get("segmento_base"), {})
            origins = {
                event["origem"],
                *origens_ativas(
                    segment, resultado, event["data_base"], event["data_base"]
                ),
            }
            for key in sorted(
                {chave(matricula, origin, event["tipo"]) for origin in origins}
            ):
                claims.append(
                    (
                        key,
                        date.fromisoformat(interval["inicio"]),
                        date.fromisoformat(interval["ultimo_dia_considerado"]),
                    )
                )
    return claims


def registrar_cobertura(db, data, resultado, historico, user):
    claims = parcelas(data.matricula, resultado)
    if claims and not (data.matricula or "").strip():
        raise PendenciaApuracao(
            "matricula_adicional_pendente",
            "Informe a matrícula para conferir a cobertura do adicional entre os fluxos.",
        )
    previous_id = getattr(data, "substitui_historico_id", None)
    previous = None
    old_claims = []
    if previous_id:
        if previous_id == historico.id:
            raise PendenciaApuracao(
                "revisao_incompativel",
                "Uma revisão deve apontar para um histórico anterior.",
            )
        previous = db.get(HistoricoCalculo, previous_id)
        if previous is None or (
            user.role not in ("admin", "dev") and previous.user_id != user.id
        ):
            raise PendenciaApuracao(
                "revisao_indisponivel",
                "O histórico a substituir não está disponível para este usuário.",
            )
        if hasattr(data, "substituicao") and previous.tipo_calculo != "substituicao":
            raise PendenciaApuracao(
                "revisao_incompativel",
                "Uma revisão de substituição deve apontar para outro cálculo de substituição.",
            )
        if (
            historico.tipo_calculo in ("abono", "rescisao", "exercicio_anterior")
            and previous.tipo_calculo != historico.tipo_calculo
        ):
            raise PendenciaApuracao(
                "revisao_incompativel",
                "O recálculo deve manter o tipo do histórico anterior.",
            )
        if (
            not (previous.matricula or "").strip()
            or not (data.matricula or "").strip()
            or identidade(previous.matricula) != identidade(data.matricula)
        ):
            raise PendenciaApuracao(
                "revisao_incompativel", "A revisão deve pertencer ao mesmo servidor."
            )
        old_claims = db.scalars(
            select(CoberturaAdicional).where(
                CoberturaAdicional.historico_id == previous_id
            )
        ).all()
    keys = sorted({item[0] for item in claims} | {item.escopo for item in old_claims})
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise PendenciaApuracao(
            "banco_nao_suportado", "Reserva de adicionais exige PostgreSQL ou SQLite."
        )
    for key in keys:
        db.execute(insert(EscopoAdicional).values(chave=key).on_conflict_do_nothing())
        db.execute(
            select(EscopoAdicional)
            .where(EscopoAdicional.chave == key)
            .with_for_update()
        ).scalar_one()
    if previous:
        # Bloqueia também revisões de históricos que não possuíam cobertura legada.
        db.execute(
            select(HistoricoCalculo)
            .where(HistoricoCalculo.id == previous_id)
            .with_for_update()
        ).scalar_one()
        if db.get(RevisaoCalculo, previous_id):
            raise PendenciaApuracao(
                "historico_ja_substituido",
                "Este histórico já foi substituído. Revise a versão atual.",
            )
        for item in old_claims:
            db.delete(item)
        db.add(RevisaoCalculo(anterior_id=previous_id, novo_id=historico.id))
        db.flush()
    for key, first, last in claims:
        existing = db.scalar(
            select(CoberturaAdicional.id)
            .where(
                CoberturaAdicional.escopo == key,
                CoberturaAdicional.inicio <= last,
                CoberturaAdicional.fim >= first,
            )
            .limit(1)
        )
        if existing:
            raise PendenciaApuracao(
                "adicional_ja_apurado",
                "Há parcela de adicional ou reflexo já apurada para esta concessão e período. Confira o histórico e informe explicitamente a revisão, se cabível.",
            )
        db.add(
            CoberturaAdicional(
                escopo=key, inicio=first, fim=last, historico_id=historico.id
            )
        )
        db.flush()  # Detecta também sobreposição dentro desta entrega.
