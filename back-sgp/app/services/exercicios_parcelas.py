"""Saldos reproduzíveis sem aplicar regras legais ou índices genéricos."""

from decimal import Decimal
from fractions import Fraction
from typing import Any, NoReturn

from app.schemas.exercicios_parcelas import PlanoExercicios
from app.services.apuracao_periodos import exato, moeda, validar_tamanho_resultado
from app.services.pendencias import PendenciaApuracao


def pending(code, message) -> NoReturn:
    raise PendenciaApuracao(code, message)


def conciliar_exercicios(records):
    aliases, ids, events, accepted, duplicates = {}, {}, {}, [], []
    payment_metadata = {}
    for row in records:
        if row.valor is None or not row.conferido:
            pending(
                "lancamento_exercicio_pendente",
                "Valor desconhecido ou lançamento sem conferência; não se presume zero.",
            )
        keys = [row.chave()]
        if getattr(row, "tipo_origem", None) == "FOLHA":
            keys.append(
                (
                    "FOLHA",
                    row.competencia_pagamento,
                    row.rubrica_pagamento,
                    row.natureza_folha,
                    row.natureza_rubrica,
                    row.identificador_folha,
                    row.sequencia,
                )
            )
        signature = row.contexto(), row.valor, row.operacao
        if row.id in ids and not any(
            key in events and events[key][1].id == ids[row.id][1].id for key in keys
        ):
            pending(
                "lancamento_exercicio_conflitante",
                "Identificador interno reutilizado para eventos diferentes.",
            )
        matches = [
            previous
            for previous in [ids.get(row.id), *(events.get(key) for key in keys)]
            if previous
        ]
        prior = matches[0] if matches else None
        if len({previous[1].id for previous in matches}) > 1:
            pending(
                "identidade_pagamento_ambigua",
                "Identificador compartilhado liga eventos previamente distintos; revise as fontes sem somá-los.",
            )
        for previous in matches:
            if previous and previous[0] != signature:
                pending(
                    "lancamento_exercicio_conflitante",
                    "Identificador/evento repetido com parcela, valor ou operação divergentes.",
                )
        if getattr(row, "tipo_origem", None):
            fields = (
                "competencia_pagamento",
                "rubrica_pagamento",
                "natureza_rubrica",
                "data_pagamento",
                "processo",
                "via_pagamento",
            )
            if row.tipo_origem == "FOLHA":
                fields += ("natureza_folha", "identificador_folha", "sequencia")
            known = {
                field: getattr(row, field)
                for field in fields
                if getattr(row, field) is not None
                and not (
                    field == "via_pagamento" and getattr(row, field) == "NAO_INFORMADA"
                )
            }
            metadata = payment_metadata.setdefault(prior[1].id if prior else row.id, {})
            if any(
                field in metadata and metadata[field] != value
                for field, value in known.items()
            ):
                pending(
                    "fonte_pagamento_exercicio_conflitante",
                    "Fontes do mesmo pagamento divergem em identidade ou dados informados; confira os documentos antes de apurar.",
                )
            # Acumula dados conhecidos de TODAS as fontes, sem alterar seus snapshots.
            metadata.update(known)
        if prior:
            aliases[row.id] = prior[1].id
            ids[row.id] = prior
            duplicates.append(
                {
                    "id": row.id,
                    "original_id": prior[1].id,
                    "fonte": row.fonte,
                    "localizador": row.localizador,
                    "dados_informados": row.model_dump(mode="json"),
                }
            )
        else:
            ids[row.id] = (signature, row)
            aliases[row.id] = row.id
            accepted.append(row)
        for key in keys:
            events[key] = ids[row.id]
    canonical = {row.id: row for row in accepted}
    for row in records:
        original = canonical[aliases[row.id]]
        for field in ("estorna_id", "complementa_id"):
            left, right = getattr(row, field), getattr(original, field)
            if aliases.get(left, left) != aliases.get(right, right):
                pending(
                    "lancamento_exercicio_conflitante",
                    "Cópias do evento apontam para origens diferentes.",
                )
    reversed_values = {}
    for row in accepted:
        if row.operacao == "LANCAMENTO":
            continue
        reference = row.estorna_id if row.operacao == "ESTORNO" else row.complementa_id
        target = canonical.get(aliases.get(reference, reference))
        if (
            target is None
            or target.operacao == "ESTORNO"
            or (row.operacao == "COMPLEMENTO" and target.operacao != "LANCAMENTO")
            or target.contexto() != row.contexto()
        ):
            pending(
                "acerto_exercicio_incompativel",
                "Acerto exige origem válida na mesma parcela; estorno pode apontar para complemento.",
            )
        if row.operacao == "ESTORNO":
            reversed_values[target.id] = reversed_values.get(
                target.id, Fraction(0)
            ) + Fraction(row.valor)
            if reversed_values[target.id] > target.valor:
                pending(
                    "estorno_exercicio_excedente",
                    "Estornos excedem o valor da origem vinculada.",
                )
    return accepted, duplicates


def _fonte_ajuste(row):
    return (
        row.parcela_id,
        row.tipo,
        row.efeito,
        row.fonte,
        row.localizador,
        row.regra.identificador,
        row.regra.versao,
    )


def conciliar_ajustes(records):
    source_events = {}
    for row in records:
        if row.valor is None or not row.conferido or not row.regra.confirmada:
            pending(
                "ajuste_exercicio_sem_regra",
                "Ajuste exige valor, memória, fonte e regra específica confirmada.",
            )
        source_events.setdefault(_fonte_ajuste(row), set()).add(
            row.identificador_evento
        )
    if any(None in group and len(group) > 2 for group in source_events.values()):
        pending(
            "ajuste_exercicio_ambiguo",
            "Fonte contém eventos distintos: identifique o evento deste ajuste antes de apurar.",
        )
    events, accepted, duplicates = {}, [], []
    sources, event_bindings = {}, {}
    for row in records:
        source_key = _fonte_ajuste(row)
        signature = row.model_dump(
            exclude={"id", "identificador_evento", "fonte", "localizador"}
        )
        event_key = row.parcela_id, row.identificador_evento
        previous = events.get(event_key) if row.identificador_evento else None
        related = sources.get(source_key, {})
        if previous is None:
            candidates = (
                list(related.values())
                if not row.identificador_evento
                else [
                    prior
                    for prior in related.values()
                    if prior[1].id not in event_bindings
                ]
            )
            if len(candidates) > 1:
                pending(
                    "ajuste_exercicio_ambiguo",
                    "Fonte contém eventos distintos: identifique o evento deste ajuste antes de apurar.",
                )
            previous = candidates[0] if candidates else None
        if previous:
            if previous[0] != signature:
                pending(
                    "ajuste_exercicio_conflitante",
                    "Fontes do mesmo ajuste divergem; confira valor, memória e regra antes de apurar.",
                )
            duplicates.append(
                {
                    "id": row.id,
                    "original_id": previous[1].id,
                    "dados_informados": row.model_dump(mode="json"),
                }
            )
        else:
            previous = signature, row
            accepted.append(row)
        sources.setdefault(source_key, {})[previous[1].id] = previous
        if row.identificador_evento:
            events[event_key] = previous
            event_bindings[previous[1].id] = row.identificador_evento
    return accepted, duplicates


def apurar_exercicios(plan: PlanoExercicios):
    if not plan.conferido_pelo_rh:
        pending(
            "exercicio_sem_conferencia",
            "Confirme os dados, o direito e a pesquisa de pagamentos pelo RH.",
        )
    origins = {row.id: row for row in plan.origens}
    parcels = {row.id: row for row in plan.parcelas}
    due, copies_due = conciliar_exercicios(plan.devidos)
    paid, copies_paid = conciliar_exercicios(plan.recebimentos)
    adjustment_entries, copies_adjustments = conciliar_ajustes(plan.ajustes)
    for records in (due, paid, plan.ajustes):
        if any(row.parcela_id not in parcels for row in records):
            pending(
                "parcela_exercicio_sem_vinculo",
                "Vincule todos os lançamentos e ajustes à parcela correspondente.",
            )
    for receipt in plan.recebimentos:
        if receipt.operacao != "ESTORNO" and receipt.natureza_rubrica == "D":
            pending(
                "natureza_recebimento_exercicio_pendente",
                "Desconto identificado não é crédito recebido; confira a operação e a fonte.",
            )
    for doc in plan.documentos:
        if not doc.vinculo_confirmado or doc.vinculo_identificado != plan.vinculo_id:
            pending(
                "documento_exercicio_pendente",
                "Confira pessoa e vínculo de cada documento.",
            )
        targets: dict[str, dict[str, Any]] = {
            "DEVIDO": {row.id: row for row in plan.devidos},
            "RECEBIMENTO": {row.id: row for row in plan.recebimentos},
            "AJUSTE": {row.id: row for row in plan.ajustes},
        }
        for candidate in doc.candidatos:
            if candidate.decisao == "DESCARTADO" and candidate.justificativa:
                continue
            target = targets.get(candidate.alvo_tipo or "", {}).get(
                candidate.alvo_id or ""
            )
            if (
                candidate.decisao != "UTILIZADO"
                or target is None
                or candidate.valor_observado is None
                or target.valor is None
            ):
                pending(
                    "candidato_exercicio_pendente",
                    "Revise cada dado extraído: vincule a um alvo ou justifique a exclusão.",
                )
            parcel = parcels.get(target.parcela_id)
            if parcel is None:
                pending(
                    "parcela_exercicio_sem_vinculo",
                    "Alvo documental sem parcela válida.",
                )
            competence = (
                target.competencia_pagamento
                if candidate.alvo_tipo == "RECEBIMENTO"
                else parcel.competencia
            )
            code = (
                target.rubrica_pagamento
                if candidate.alvo_tipo == "RECEBIMENTO"
                else parcel.rubrica
            )
            if (
                abs(Decimal(candidate.valor_observado)) != target.valor
                or (
                    candidate.competencia is not None
                    and candidate.competencia != competence
                )
                or (candidate.rubrica is not None and candidate.rubrica != code)
            ):
                pending(
                    "candidato_exercicio_divergente",
                    "Dado extraído e alvo divergem em valor, competência ou rubrica.",
                )
            if candidate.alvo_tipo == "RECEBIMENTO" and (
                (
                    candidate.natureza_rubrica is not None
                    and candidate.natureza_rubrica != target.natureza_rubrica
                )
                or (
                    candidate.sequencia is not None
                    and candidate.sequencia != target.sequencia
                )
            ):
                pending(
                    "candidato_exercicio_divergente",
                    "Natureza ou sequência da rubrica extraída diverge do recebimento.",
                )
            negative_operation = (
                target.efeito == "REDUCAO"
                if candidate.alvo_tipo == "AJUSTE"
                else target.operacao == "ESTORNO"
            )
            if (
                Decimal(candidate.valor_observado) < 0
                and not negative_operation
                and not (
                    candidate.correcao_sinal_confirmada and candidate.justificativa
                )
            ):
                pending(
                    "sinal_exercicio_pendente",
                    "Valor negativo exige operação coerente ou correção de sinal confirmada e justificada.",
                )
    rows = []
    total_due = total_received = Fraction(0)
    for parcel in plan.parcelas:
        origin = origins.get(parcel.origem_direito_id)
        if origin is None or not origin.regra.confirmada:
            pending(
                "origem_direito_exercicio_pendente",
                "Informe origem do direito e regra confirmada para cada parcela.",
            )
        interval = parcel.periodo_referencia
        if (
            not f"{plan.periodo.inicio.year:04}-{plan.periodo.inicio.month:02}"
            <= parcel.competencia
            <= f"{plan.periodo.ultimo_dia_considerado.year:04}-{plan.periodo.ultimo_dia_considerado.month:02}"
        ):
            pending(
                "competencia_exercicio_fora_escopo",
                "Competência devida fora do escopo informado; não confundir competência do direito com a do pagamento.",
            )
        if (
            parcel.estado_revisao == "PENDENTE"
            or parcel.pesquisa_pagamentos == "PENDENTE"
        ):
            pending(
                "revisao_exercicio_pendente",
                "Estado de revisão ou pesquisa de pagamentos pendente.",
            )
        if (
            not plan.periodo.inicio
            <= interval.inicio
            <= interval.ultimo_dia_considerado
            <= plan.periodo.ultimo_dia_considerado
            or not origin.periodo_efeitos.inicio
            <= interval.inicio
            <= interval.ultimo_dia_considerado
            <= origin.periodo_efeitos.ultimo_dia_considerado
            or not origin.regra.cobre(interval.inicio)
            or not origin.regra.cobre(interval.ultimo_dia_considerado)
        ):
            pending(
                "periodo_direito_exercicio_incompativel",
                "Período da parcela precisa estar coberto pelo escopo, efeitos e regra confirmados.",
            )
        if parcel.categoria in ("PRINCIPAL", "OUTRA") and any(
            f"{day.year:04}-{day.month:02}" != parcel.competencia
            for day in (interval.inicio, interval.ultimo_dia_considerado)
        ):
            pending(
                "competencia_exercicio_incompativel",
                "Parcela mensal deve identificar competência compatível com o período considerado.",
            )
        ds = [row for row in due if row.parcela_id == parcel.id]
        ps = [row for row in paid if row.parcela_id == parcel.id]
        adjustments = [row for row in adjustment_entries if row.parcela_id == parcel.id]
        if not ds:
            pending(
                "devido_exercicio_ausente",
                "Informe devido, inclusive zero confirmado com fonte e memória.",
            )
        if (parcel.pesquisa_pagamentos == "IDENTIFICADOS") != bool(ps):
            pending(
                "pesquisa_exercicio_incompativel",
                "Pesquisa de pagamentos incompatível com os recebimentos identificados.",
            )
        active_originals = []
        for original in (row for row in ds if row.operacao == "LANCAMENTO"):
            reversed_amount = sum(
                (
                    Fraction(row.valor)
                    for row in ds
                    if row.operacao == "ESTORNO"
                    and row.estorna_id
                    in {
                        original.id,
                        *(
                            copy["id"]
                            for copy in copies_due
                            if copy["original_id"] == original.id
                        ),
                    }
                ),
                Fraction(0),
            )
            if Fraction(original.valor) != reversed_amount:
                active_originals.append(original.id)
        if len(active_originals) > 1:
            pending(
                "devido_exercicio_duplicado",
                "Mais de um devido original ativo na parcela; identifique complemento ou estorno.",
            )
        principal = sum(
            (
                Fraction(row.valor) * (-1 if row.operacao == "ESTORNO" else 1)
                for row in ds
            ),
            Fraction(0),
        )
        additions = reductions = Fraction(0)
        for adjustment in adjustments:
            if (
                adjustment.valor is None
                or not adjustment.conferido
                or not adjustment.regra.confirmada
                or not adjustment.regra.cobre(interval.inicio)
                or not adjustment.regra.cobre(interval.ultimo_dia_considerado)
            ):
                pending(
                    "ajuste_exercicio_sem_regra",
                    "Ajuste exige valor, memória, fonte e regra específica confirmada cobrindo o período; nada é aplicado genericamente.",
                )
            if adjustment.efeito == "ACRESCIMO":
                additions += Fraction(adjustment.valor)
            else:
                reductions += Fraction(adjustment.valor)
        adjusted = principal + additions - reductions
        if adjusted < 0:
            pending(
                "ajuste_exercicio_excedente",
                "Reduções excedem o devido; confira a regra e os valores, sem zeramento automático.",
            )
        received = sum(
            (
                Fraction(row.valor) * (-1 if row.operacao == "ESTORNO" else 1)
                for row in ps
            ),
            Fraction(0),
        )
        row = {
            "parcela_id": parcel.id,
            "competencia": parcel.competencia,
            "rubrica": parcel.rubrica,
            "categoria": parcel.categoria,
            "natureza_folha_devida": parcel.natureza_folha_devida,
            "periodo_referencia": interval.model_dump(mode="json"),
            "origem_direito": origin.model_dump(mode="json"),
            "estado_revisao": parcel.estado_revisao,
            "nota_revisao": parcel.nota_revisao,
            "principal": moeda(principal),
            "acrescimos": moeda(additions),
            "reducoes": moeda(reductions),
            "devido": moeda(adjusted),
            "recebido": moeda(received),
            "saldo": moeda(adjusted - received),
            "devido_exato": exato(adjusted),
            "recebido_exato": exato(received),
            "saldo_exato": exato(adjusted - received),
            "devidos_ids": [row.id for row in ds],
            "recebimentos_ids": [row.id for row in ps],
            "ajustes_ids": [row.id for row in adjustments],
        }
        rows.append(row)
        total_due += adjusted
        total_received += received
    result = {
        "tipo_exercicio": "parcelas_v1",
        "periodo": plan.periodo.model_dump(mode="json"),
        "parcelas": rows,
        "devidos_considerados": [row.model_dump(mode="json") for row in due],
        "recebimentos_considerados": [row.model_dump(mode="json") for row in paid],
        "ajustes_declarados": [row.model_dump(mode="json") for row in plan.ajustes],
        "ajustes_considerados": [
            row.model_dump(mode="json") for row in adjustment_entries
        ],
        "duplicidades_ajustes": copies_adjustments,
        "duplicidades_devidos": copies_due,
        "duplicidades_recebimentos": copies_paid,
        "totais": {
            "devido": moeda(total_due),
            "recebido": moeda(total_received),
            "saldo": moeda(total_due - total_received),
            "saldo_exato": exato(total_due - total_received),
        },
        "saldo_parcelas_calculadas": moeda(total_due - total_received),
        "total_geral_a_receber": moeda(total_due - total_received),
        "nota_escopo": "Direito, revisão e pesquisa de pagamentos conferidos pelo RH. Pagamento judicial/administrativo preservado quando informado. Prescrição, juros, atualização e descontos não são calculados automaticamente; ajustes declarados exigem regra específica confirmada.",
    }
    validar_tamanho_resultado(result)
    return result
