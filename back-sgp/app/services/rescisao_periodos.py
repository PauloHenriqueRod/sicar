"""Rescisão com calendário e lançamentos rastreáveis, sem homologar direito."""

import calendar
from collections import defaultdict
from datetime import date, timedelta
from fractions import Fraction

from app.schemas.rescisao_periodos import PlanoRescisao
from app.services.apuracao_periodos import (
    SaldoCompetencia,
    conciliar_recebimentos,
    consolidar_saldos,
    exato,
    moeda,
    validar_tamanho_resultado,
)
from app.services.pendencias import PendenciaApuracao
from app.services.periodos import dividir_intervalo
from app.services.salary_references import resolve_salary


def pendencia(code, message):
    raise PendenciaApuracao(code, message)


def aniversario(inicio, meses):
    index = inicio.year * 12 + inicio.month - 1 + meses
    year, month = divmod(index, 12)
    return date(
        year, month + 1, min(inicio.day, calendar.monthrange(year, month + 1)[1])
    )


def previa_rescisao(plan: PlanoRescisao):
    if plan.sentido_termino == "A_PARTIR_DE" and plan.data_termino == date.min:
        pendencia(
            "periodo_contratual_vazio", "Não há dia considerado anterior ao término."
        )
    suggested_end = (
        plan.data_termino - timedelta(days=1)
        if plan.sentido_termino == "A_PARTIR_DE"
        else plan.data_termino
    )
    end = plan.ultimo_dia_considerado or suggested_end
    if end < plan.inicio_exercicio:
        pendencia(
            "periodo_contratual_vazio", "Não há dia considerado dentro do contrato."
        )
    if end != suggested_end and not plan.justificativa_ultimo_dia:
        pendencia(
            "ultimo_dia_sem_justificativa",
            "Justifique a alteração do último dia considerado.",
        )
    if plan.sentido_termino == "A_PARTIR_DE" and end >= plan.data_termino:
        pendencia(
            "ultimo_dia_incompativel",
            "Rescisão a partir de exclui a própria data do término.",
        )
    if plan.ultimo_dia_trabalhado and plan.ultimo_dia_trabalhado > end:
        pendencia(
            "ultimo_dia_trabalhado_incompativel",
            "Último dia trabalhado posterior ao último dia considerado.",
        )
    if plan.inicio_exercicio.day >= 29 and plan.regra.aniversario_meses_curtos is None:
        pendencia(
            "aniversario_sem_regra",
            "Confirme a política de aniversário contratual em meses curtos.",
        )
    months = (
        (end.year - plan.inicio_exercicio.year) * 12
        + end.month
        - plan.inicio_exercicio.month
    )
    if aniversario(plan.inicio_exercicio, months) > end:
        months -= 1
    anchor = aniversario(plan.inicio_exercicio, months)
    fraction_days = (end - anchor).days + 1
    acquired = months + int(fraction_days >= 15)
    if acquired > 1200:
        pendencia(
            "limite_tecnico_rescisao",
            "Contrato excede o limite técnico de 1200 avos; confira ou delimite o caso.",
        )
    start_month = max(plan.inicio_exercicio, date(end.year, end.month, 1))
    salary_days = (end - start_month).days + 1
    thirteenth = 0
    for month in range(1, end.month + 1):
        first = max(date(end.year, month, 1), plan.inicio_exercicio)
        last = min(date(end.year, month, calendar.monthrange(end.year, month)[1]), end)
        thirteenth += int((last - first).days + 1 >= 15)
    suggestions = {
        "dias_salariais": salary_days,
        "avos_ferias": acquired,
        "avos_13": thirteenth,
    }
    adopted = {
        key: plan.correcoes[key].valor if key in plan.correcoes else value
        for key, value in suggestions.items()
    }
    if adopted["dias_salariais"] > salary_days or adopted["avos_13"] > 12:
        pendencia(
            "quantidade_incompativel",
            "Dias corrigidos não podem exceder a janela salarial; 13º está limitado a 12 avos.",
        )
    if adopted["dias_salariais"] != salary_days and len(plan.salarios) > 1:
        pendencia(
            "dias_com_multiplas_bases",
            "Para corrigir dias com mudanças salariais, delimite as faixas efetivas; não rateie dias entre bases distintas automaticamente.",
        )
    return {
        "ultimo_dia_sugerido": suggested_end.isoformat(),
        "ultimo_dia_considerado": end.isoformat(),
        "competencia_salarial": f"{end.year:04}-{end.month:02}",
        "meses_completos": months,
        "inicio_fracao_final": anchor.isoformat(),
        "dias_fracao_final": fraction_days,
        "sugestoes": suggestions,
        "adotados": adopted,
        "correcoes": {
            key: value.model_dump(mode="json") for key, value in plan.correcoes.items()
        },
    }


def resolver_base(base, db):
    if base is None:
        pendencia(
            "base_rescisao_pendente", "Informe e confira a base da parcela dependente."
        )
    if base.valor_manual:
        return Fraction(base.valor_manual.valor), base.valor_manual.model_dump(
            mode="json"
        )
    amount, source = resolve_salary(db, base.referencia_salarial, base.titulacao)
    return Fraction(amount), source


def ferias_pagas(plan):
    identities = {}
    for payment in plan.pagamentos_ferias:
        metadata = (
            payment.periodo_aquisitivo,
            payment.avos,
            payment.base_terco.valor if payment.base_terco else None,
            payment.pagamento_original_id,
            payment.data_pagamento,
            payment.ordem_devolucao,
        )
        if payment.id in identities and identities[payment.id] != metadata:
            pendencia(
                "ferias_pagamento_conflitante",
                "Mesmo identificador com período, avos ou base divergentes.",
            )
        identities[payment.id] = metadata
    accepted, duplicates = conciliar_recebimentos(plan.pagamentos_ferias)
    # A identidade documental também precisa concordar quanto ao período/base/avos.
    by_id = {p.id: p for p in plan.pagamentos_ferias}
    for copy in duplicates:
        left, right = by_id[copy["id"]], by_id[copy["original_id"]]
        for key in (
            "periodo_aquisitivo",
            "avos",
            "pagamento_original_id",
            "data_pagamento",
            "ordem_devolucao",
        ):
            if getattr(left, key) != getattr(right, key):
                pendencia(
                    "ferias_pagamento_conflitante",
                    "Cópias de pagamento divergem em período, avos ou base do terço.",
                )
        if (left.base_terco.valor if left.base_terco else None) != (
            right.base_terco.valor if right.base_terco else None
        ):
            pendencia(
                "ferias_pagamento_conflitante",
                "Cópias de pagamento divergem na base do terço.",
            )
    originals = {p.id: p for p in accepted if p.operacao == "PAGAMENTO"}
    postings = {p.id: p for p in accepted}
    aliases = {copy["id"]: copy["original_id"] for copy in duplicates}
    net = {p.id: p.avos for p in originals.values()}
    net_amounts = {p.id: Fraction(p.valor) for p in originals.values()}
    periods = set()
    for payment in originals.values():
        period = payment.periodo_aquisitivo
        if (
            payment.avos == 0
            or period.inicio < plan.inicio_exercicio
            or period.inicio > plan.ultimo_dia_considerado
        ):
            pendencia(
                "ferias_periodo_incompativel",
                "Confira avos e período aquisitivo do pagamento de férias.",
            )
    for payment in accepted:
        first_competence = (
            f"{plan.inicio_exercicio.year:04}-{plan.inicio_exercicio.month:02}"
        )
        last_day = plan.ultimo_dia_considerado
        last_competence = f"{last_day.year:04}-{last_day.month:02}"
        if not first_competence <= payment.competencia <= last_competence:
            pendencia(
                "ferias_pagamento_fora_contrato",
                "Pagamento de férias fora das competências do contrato; confira a associação.",
            )
        if payment.natureza_rubrica != "R":
            pendencia(
                "ferias_natureza_pendente",
                "Classifique o estorno explicitamente, preservando a natureza do pagamento original.",
            )
        if payment.operacao == "PAGAMENTO":
            continue
        target_id = (
            payment.estorna_id
            if payment.operacao == "ESTORNO"
            else payment.pagamento_original_id
        )
        target_id = aliases.get(target_id, target_id)
        reversed_posting = postings.get(target_id)
        if (
            payment.operacao == "ESTORNO"
            and reversed_posting is not None
            and reversed_posting.operacao == "COMPLEMENTO"
        ):
            if payment.avos != 0:
                pendencia(
                    "estorno_complemento_com_avos",
                    "Estorno de complemento não reverte avos; o complemento não quitou novos avos.",
                )
            original_id = reversed_posting.pagamento_original_id
            target_id = aliases.get(original_id, original_id)
        target = originals.get(target_id)
        if not target or payment.periodo_aquisitivo != target.periodo_aquisitivo:
            pendencia(
                "ferias_sem_vinculo",
                "Associe complemento/estorno ao pagamento e ao mesmo período aquisitivo.",
            )
        if payment.base_terco is not None and (
            target.base_terco is None
            or payment.base_terco.valor != target.base_terco.valor
        ):
            pendencia(
                "base_terco_conflitante",
                "Base divergente no acerto: confira e atualize a base pertinente no pagamento original, preservando sua fonte.",
            )
        if payment.operacao == "COMPLEMENTO" and payment.avos != 0:
            pendencia(
                "complemento_com_avos",
                "Complemento não representa nova quitação de avos.",
            )
        if payment.operacao == "ESTORNO":
            net[target_id] -= payment.avos
            if net[target_id] < 0:
                pendencia(
                    "estorno_avos_excedente",
                    "Avos revertidos excedem os avos do pagamento original.",
                )
        net_amounts[target_id] += Fraction(payment.valor) * (
            -1 if payment.operacao == "ESTORNO" else 1
        )
    for payment in originals.values():
        if not net[payment.id]:
            continue
        period = payment.periodo_aquisitivo
        if any(
            period.inicio <= old_end and old_start <= period.ultimo_dia_considerado
            for old_start, old_end in periods
        ):
            pendencia(
                "ferias_periodo_duplicado",
                "Pagamentos originais ativos cobrem períodos sobrepostos; identifique complementos e estornos.",
            )
        periods.add((period.inicio, period.ultimo_dia_considerado))
    return originals, net, net_amounts, duplicates, accepted


def calcular_rescisao_periodos(plan: PlanoRescisao, db):
    preview = previa_rescisao(plan)
    end = date.fromisoformat(preview["ultimo_dia_considerado"])
    if not plan.conferido_pelo_rh or not plan.regra.confirmada:
        pendencia(
            "rescisao_sem_conferencia",
            "Confirme os dados e a regra da rescisão pelo RH.",
        )
    if (
        plan.modalidade != "PROFESSOR_SUBSTITUTO"
        or plan.motivo_termino not in plan.regra.motivos_suportados
    ):
        pendencia(
            "motivo_termino_nao_suportado",
            "Modalidade ou motivo sem regra de cálculo suportada.",
        )
    if plan.ultimo_dia_trabalhado is None or plan.ultimo_dia_considerado is None:
        pendencia(
            "ultimos_dias_pendentes",
            "Confirme último dia trabalhado e último dia considerado; a prévia é apenas sugestão.",
        )
    if not plan.regra.cobre(plan.inicio_exercicio) or not plan.regra.cobre(end):
        pendencia(
            "regra_rescisao_sem_vigencia",
            "A regra deve cobrir o período contratual considerado.",
        )
    if any(
        not doc.vinculo_confirmado or doc.contrato_identificado != plan.contrato_id
        for doc in plan.documentos
    ):
        pendencia(
            "documento_contrato_pendente",
            "Confira a associação de cada documento à pessoa e ao contrato.",
        )
    quantities = preview["adotados"]
    acquired = quantities["avos_ferias"]
    if (
        not plan.regra.ferias_sem_teto_confirmada
        and plan.regra.limite_avos_ferias is None
    ):
        pendencia(
            "limite_ferias_sem_regra",
            "Confirme ausência de teto ou informe o limite aplicável; não há corte automático em 24 avos.",
        )
    if (
        plan.regra.limite_avos_ferias is not None
        and acquired > plan.regra.limite_avos_ferias
    ):
        pendencia(
            "limite_ferias_excedido",
            "Avos excedem o limite confirmado; confira o enquadramento, sem truncamento automático.",
        )
    originals, net, net_amounts, duplicates, holiday_payments = ferias_pagas(plan)
    balance = acquired - sum(net.values())
    principal = third = Fraction(0)
    sources = {}
    refunds = []
    if balance > 0:
        base, sources["ferias"] = resolver_base(plan.base_ferias, db)
        principal = base * balance / 12
        third = principal / 3
    elif balance < 0:
        remaining = -balance
        active = [payment for payment in originals.values() if net[payment.id]]
        order: list[str]
        if any(payment.ordem_devolucao is not None for payment in active):
            if any(payment.ordem_devolucao is None for payment in active):
                pendencia(
                    "ordem_tercos_pendente",
                    "Informe a ordem cronológica conferida de todos os pagamentos originais ativos.",
                )
            order = [f"{payment.ordem_devolucao:04}" for payment in active]
        elif any(payment.data_pagamento is not None for payment in active):
            if any(payment.data_pagamento is None for payment in active):
                pendencia(
                    "ordem_tercos_pendente",
                    "Informe as datas dos pagamentos originais ativos para identificar o último terço.",
                )
            order = [
                payment.data_pagamento.isoformat() if payment.data_pagamento else ""
                for payment in active
            ]
        else:
            order = [payment.competencia for payment in active]
        if len(set(order)) != len(order):
            pendencia(
                "ordem_tercos_pendente",
                "Há pagamentos ativos sem ordem cronológica inequívoca; informe datas distintas ou a ordem de devolução conferida pelo RH.",
            )
        ordered = [
            payment
            for _, payment in sorted(
                zip(order, active, strict=True), key=lambda item: item[0], reverse=True
            )
        ]
        for payment in ordered:
            avos = min(remaining, net[payment.id])
            if not avos:
                continue
            if payment.base_terco is None:
                pendencia(
                    "base_ultimo_terco_pendente",
                    "Informe a base pertinente do terço excedente; não se presume o salário atual.",
                )
            amount = Fraction(payment.base_terco.valor) * avos / 36
            if amount > net_amounts[payment.id]:
                pendencia(
                    "devolucao_superior_ao_pago",
                    "Devolução excede o terço efetivamente pago após complementos/estornos; confira base, avos e lançamentos.",
                )
            third -= amount
            refunds.append(
                {
                    "pagamento_id": payment.id,
                    "avos": avos,
                    "base": payment.base_terco.model_dump(mode="json"),
                    "devolucao": moeda(amount),
                    "devolucao_exata": exato(amount),
                }
            )
            remaining -= avos
            if not remaining:
                break
    salary = Fraction(0)
    days_changed = (
        quantities["dias_salariais"] != preview["sugestoes"]["dias_salariais"]
    )
    segments = []
    month_start = max(plan.inicio_exercicio, date(end.year, end.month, 1))
    limits = {
        value
        for faixa in plan.salarios
        for value in (
            faixa.inicio.toordinal(),
            faixa.ultimo_dia_considerado.toordinal() + 1,
        )
    }
    for first, last, days, month_days in dividir_intervalo(month_start, end, limits):
        matches = [
            faixa
            for faixa in plan.salarios
            if faixa.inicio <= first and faixa.ultimo_dia_considerado >= last
        ]
        if len(matches) != 1:
            pendencia(
                "salario_final_sem_cobertura",
                "Informe uma única base salarial para cada dia da competência final, sem lacunas ou sobreposições.",
            )
        base = matches[0].base
        current = first
        while current <= last:
            chosen = base
            if base.referencia_salarial:
                chosen = base.model_copy(
                    update={
                        "referencia_salarial": base.referencia_salarial.model_copy(
                            update={"data_referencia": current}
                        )
                    }
                )
            monthly, source = resolver_base(chosen, db)
            ref_end = source.get("referencia", {}).get("fim_vigencia")
            segment_end = min(last, date.fromisoformat(ref_end)) if ref_end else last
            segment_days = (segment_end - current).days + 1
            counted = quantities["dias_salariais"] if days_changed else segment_days
            if days_changed and (current != first or segment_end != end):
                pendencia(
                    "dias_com_multiplas_bases",
                    "Não é possível distribuir automaticamente dias corrigidos entre referências salariais distintas.",
                )
            amount = monthly * counted / month_days
            salary += amount
            segments.append(
                {
                    "inicio": current.isoformat(),
                    "ultimo_dia_considerado": segment_end.isoformat(),
                    "dias_computados": counted,
                    "dias_reais_mes": month_days,
                    "base": source,
                    "regra": plan.regra.model_dump(mode="json"),
                    "devido": moeda(amount),
                    "devido_exato": exato(amount),
                }
            )
            if segment_end == last:
                break
            current = segment_end + timedelta(days=1)
    thirteenth = Fraction(0)
    if quantities["avos_13"]:
        base, sources["decimo_terceiro"] = resolver_base(plan.base_13, db)
        thirteenth = base * quantities["avos_13"] / 12
    received, payment_duplicates = conciliar_recebimentos(plan.recebidos)
    due = {"00742": salary, "00772": principal, "82696": third, "82407": thirteenth}
    rows = []
    total_received = Fraction(0)
    for payment in received:
        competence_matches = payment.competencia == preview["competencia_salarial"]
        if payment.rubrica == "82407":
            first_competence = max(
                f"{end.year:04}-01",
                f"{plan.inicio_exercicio.year:04}-{plan.inicio_exercicio.month:02}",
            )
            competence_matches = (
                first_competence
                <= payment.competencia
                <= preview["competencia_salarial"]
            )
        if (
            payment.rubrica not in due
            or payment.natureza_rubrica != "R"
            or not competence_matches
        ):
            pendencia(
                "recebimento_rescisao_incompativel",
                "Confira rubrica e competência: salário/férias finais na competência final; 13º no ano considerado. A rubrica 750 pertence ao histórico de férias.",
            )
        value = Fraction(payment.valor) * (-1 if payment.operacao == "ESTORNO" else 1)
        total_received += value
        rows.append(
            {**payment.model_dump(mode="json"), "valor_conciliado": moeda(value)}
        )
    detail = {}
    ledger: dict[tuple[str, str, str, str], SaldoCompetencia] = defaultdict(
        SaldoCompetencia
    )
    for code, amount in due.items():
        ledger[
            (preview["competencia_salarial"], code, plan.natureza_folha_devida, "R")
        ].devido += amount
    for payment in received:
        key = (
            payment.competencia,
            payment.rubrica,
            payment.natureza_folha,
            payment.natureza_rubrica,
        )
        ledger[key].recebido += Fraction(payment.valor) * (
            -1 if payment.operacao == "ESTORNO" else 1
        )
        ledger[key].lancamentos.append(payment.id)
    by_competence, _, _ = consolidar_saldos(ledger)
    for code, value in due.items():
        paid = sum(
            (
                Fraction(p.valor) * (-1 if p.operacao == "ESTORNO" else 1)
                for p in received
                if p.rubrica == code
            ),
            Fraction(0),
        )
        detail[code] = {
            "competencia": preview["competencia_salarial"],
            "devido": moeda(value),
            "recebido": moeda(paid),
            "saldo": moeda(value - paid),
            "saldo_exato": exato(value - paid),
        }
    total = sum(due.values(), Fraction(0)) - total_received
    result = {
        "tipo_rescisao": "periodos_v1",
        "previa": preview,
        "avos_ferias_adquiridos": acquired,
        "avos_ferias_quitados": sum(net.values()),
        "avos_ferias_devidos": balance,
        "segmentos_salariais": segments,
        "bases": sources,
        "devolucoes_terco": refunds,
        "pagamentos_ferias": [p.model_dump(mode="json") for p in holiday_payments],
        "recebimentos_considerados": rows,
        "duplicidades": duplicates + payment_duplicates,
        "detalhamento_rubricas": detail,
        "por_competencia": by_competence,
        "saldo_parcelas_calculadas": moeda(total),
        "total_liquido_a_receber": moeda(total),
        "saldo_exato": exato(total),
        "nota_escopo": "Saldo das parcelas calculadas: salário final, férias, terço e 13º. Não representa líquido completo. Direito, períodos, bases, motivos e pagamentos conferidos manualmente pelo RH.",
    }
    validar_tamanho_resultado(result)
    return result
