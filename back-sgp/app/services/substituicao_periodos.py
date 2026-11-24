"""Cruzamento temporal de substituição, sem inferir documentos ou opção legal."""

import json
from collections import defaultdict
from fractions import Fraction

from sqlalchemy import or_

from app.models.fontes_oficiais import EstruturaFuncao, ReferenciaFuncao
from app.services.apuracao_periodos import (
    SaldoCompetencia,
    conciliar_recebimentos,
    consolidar_saldos,
    exato,
    moeda,
    validar_tamanho_resultado,
)
from app.services.pendencias import PendenciaApuracao
from app.services.periodos import dividir_intervalo, limites_mensais
from app.utils.function_keys import function_key


def composicoes(state):
    yield "SUBSTITUIDA", state.substituida
    if state.opcao.calculo == "DIFERENCA_FUNCOES" and state.propria.funcao is not None:
        yield "PROPRIA", state.propria.funcao


def referencias(plan, db):
    keys = {
        function_key(fn.tipo_funcao, fn.codigo_funcao, fn.modalidade, comp.componente)
        for state in [plan.estado_inicial, *(event.estado for event in plan.eventos)]
        for _, fn in composicoes(state)
        for comp in fn.componentes
        if comp.origem == "TABELA"
    }
    if not keys:
        return []
    rows = (
        db.query(ReferenciaFuncao, EstruturaFuncao.chave)
        .join(EstruturaFuncao)
        .filter(
            EstruturaFuncao.chave.in_(keys),
            ReferenciaFuncao.inicio_vigencia <= plan.periodo.ultimo_dia_considerado,
            or_(
                ReferenciaFuncao.fim_vigencia.is_(None),
                ReferenciaFuncao.fim_vigencia >= plan.periodo.inicio,
            ),
        )
        .limit(2001)
        .all()
    )
    if len(rows) > 2000:
        raise PendenciaApuracao(
            "limite_referencias_funcao",
            "Divida o período: mais de 2000 referências de função candidatas.",
        )
    return rows


def base_funcao(fn, papel, refs, first, last):
    amount, sources = Fraction(0), []
    for component in fn.componentes:
        source = {
            "papel": papel,
            "tipo_funcao": fn.tipo_funcao,
            "codigo_funcao": fn.codigo_funcao,
            "modalidade": fn.modalidade,
            "componente": component.componente,
            "percentual_utilizado": str(component.percentual_utilizado),
        }
        if component.origem == "MANUAL":
            if component.inicio_vigencia > first or (
                component.fim_vigencia is not None and component.fim_vigencia < last
            ):
                raise PendenciaApuracao(
                    "vigencia_manual_funcao",
                    "A base manual da função não cobre todos os dias do segmento.",
                )
            value = component.valor_manual.valor
            source.update(
                origem="MANUAL",
                **component.valor_manual.model_dump(mode="json"),
                inicio_vigencia=component.inicio_vigencia.isoformat(),
                fim_vigencia=component.fim_vigencia.isoformat()
                if component.fim_vigencia
                else None,
            )
        else:
            key = function_key(
                fn.tipo_funcao, fn.codigo_funcao, fn.modalidade, component.componente
            )
            matches = [
                ref
                for ref, identity in refs
                if identity == key
                and ref.inicio_vigencia <= first
                and (ref.fim_vigencia is None or ref.fim_vigencia >= last)
            ]
            if len(matches) != 1:
                raise PendenciaApuracao(
                    "referencia_funcao_pendente",
                    f"Confira a cobertura de {papel}: {fn.tipo_funcao} {fn.codigo_funcao}, modalidade {fn.modalidade}, componente {component.componente}, de {first} a {last}.",
                )
            ref = matches[0]
            value = ref.valor
            source.update(
                origem="REFERENCIA_CONFIRMADA",
                referencia_id=ref.id,
                valor=str(value),
                fonte=ref.fonte,
                inicio_vigencia=ref.inicio_vigencia.isoformat(),
                fim_vigencia=ref.fim_vigencia.isoformat() if ref.fim_vigencia else None,
            )
        part = Fraction(value) * Fraction(component.percentual_utilizado) / 100
        source["valor_utilizado_exato"] = exato(part)
        sources.append(source)
        amount += part
    return amount, sources


def calcular_substituicao_periodos(plan, db):
    refs = referencias(plan, db)
    received, duplicates = conciliar_recebimentos(plan.recebidos)
    first, last = plan.periodo.inicio, plan.periodo.ultimo_dia_considerado
    bounds = limites_mensais(first, last)
    for interval in [
        plan.designacao,
        *plan.afastamentos_titular,
        *plan.impedimentos_substituto,
    ]:
        bounds.update(
            (
                interval.inicio.toordinal(),
                interval.ultimo_dia_considerado.toordinal() + 1,
            )
        )
    events = sorted(plan.eventos, key=lambda item: item.efeitos_financeiros)
    bounds.update(item.efeitos_financeiros.toordinal() for item in events)
    for state in [plan.estado_inicial, *(event.estado for event in events)]:
        bounds.add(state.opcao.inicio_vigencia.toordinal())
        if state.opcao.fim_vigencia:
            bounds.add(state.opcao.fim_vigencia.toordinal() + 1)
        for _, fn in composicoes(state):
            for component in fn.componentes:
                if component.inicio_vigencia:
                    bounds.add(component.inicio_vigencia.toordinal())
                if component.fim_vigencia:
                    bounds.add(component.fim_vigencia.toordinal() + 1)
    for ref, _ in refs:
        bounds.add(ref.inicio_vigencia.toordinal())
        if ref.fim_vigencia:
            bounds.add(ref.fim_vigencia.toordinal() + 1)
    state, event_index = plan.estado_inicial, 0
    ledger = defaultdict(SaldoCompetencia)
    days_by_month = {}
    segments = []
    eligible_total = 0
    segment_bytes = 0
    for start, end, days, month_days in dividir_intervalo(first, last, bounds):
        while (
            event_index < len(events)
            and events[event_index].efeitos_financeiros <= start
        ):
            state = events[event_index].estado
            event_index += 1
        competence = f"{start.year:04}-{start.month:02}"
        summary = days_by_month.setdefault(
            competence,
            {
                "competencia": competence,
                "dias_considerados": 0,
                "dias_excluidos": 0,
                "dias_aplicaveis": 0,
                "dias_impedidos": 0,
                "grupos_exclusao": {},
            },
        )
        designated = (
            plan.designacao.inicio <= start <= plan.designacao.ultimo_dia_considerado
        )
        absences = [
            item
            for item in plan.afastamentos_titular
            if item.inicio <= start <= item.ultimo_dia_considerado
        ]
        eligible = designated and bool(absences)
        eligible_total += days if eligible else 0
        impediments = (
            [
                item
                for item in plan.impedimentos_substituto
                if item.inicio <= start <= item.ultimo_dia_considerado
            ]
            if eligible
            else []
        )
        considered = days if eligible and not impediments else 0
        reasons = (
            ["FORA_DESIGNACAO"]
            if not designated
            else ["TITULAR_SEM_AFASTAMENTO"]
            if not absences
            else [f"IMPEDIMENTO:{item.id}" for item in impediments]
        )
        summary["dias_considerados"] += considered
        summary["dias_excluidos"] += days - considered
        summary["dias_aplicaveis"] += days if eligible else 0
        summary["dias_impedidos"] += days if eligible and impediments else 0
        if reasons:
            group = tuple(sorted(reasons))
            summary["grupos_exclusao"][group] = (
                summary["grupos_exclusao"].get(group, 0) + days
            )
        amount, sources, monthly = Fraction(0), [], Fraction(0)
        if considered:
            if not state.opcao.cobre(start) or not state.opcao.cobre(end):
                raise PendenciaApuracao(
                    "opcao_fora_vigencia",
                    "A regra da opção remuneratória não cobre o segmento considerado.",
                )
            bases = {"PROPRIA": Fraction(0)}
            for role, fn in composicoes(state):
                bases[role], origins = base_funcao(fn, role, refs, start, end)
                sources.extend(origins)
            monthly = bases["SUBSTITUIDA"] - (
                bases["PROPRIA"] if state.opcao.calculo == "DIFERENCA_FUNCOES" else 0
            )
            if state.opcao.diferenca_negativa == "ZERAR":
                monthly = max(monthly, Fraction(0))
            amount = monthly * considered / month_days
        key = (
            competence,
            plan.rubrica.rubrica,
            plan.rubrica.natureza_folha,
            plan.rubrica.natureza_rubrica,
        )
        ledger[key].devido += amount
        segments.append(
            {
                "id": len(segments) + 1,
                "inicio": start.isoformat(),
                "ultimo_dia_considerado": end.isoformat(),
                "competencia": competence,
                "dias_calendario": days,
                "dias_reais_mes": month_days,
                "dias_computados": considered,
                "dias_excluidos": days - considered,
                "motivos_exclusao": reasons,
                "afastamentos_titular": [
                    item.model_dump(mode="json") for item in absences
                ],
                "impedimentos_substituto": [
                    item.model_dump(mode="json") for item in impediments
                ],
                "estado": state.model_dump(mode="json"),
                "evento_aplicado": events[event_index - 1].model_dump(
                    mode="json", exclude={"estado"}
                )
                if event_index
                else None,
                "referencias_funcoes": sources,
                "regra": state.opcao.model_dump(mode="json"),
                "base_mensal_exata": exato(monthly),
                "devido": moeda(amount),
                "devido_exato": exato(amount),
            }
        )
        if len(segments) > 2000:
            raise PendenciaApuracao(
                "limite_segmentos", "Divida a substituição: mais de 2000 segmentos."
            )
        segment_bytes += len(
            json.dumps(segments[-1], ensure_ascii=False).encode("utf-8")
        )
        if segment_bytes > 1024 * 1024:
            raise PendenciaApuracao(
                "limite_resultado", "Divida a substituição: detalhamento excede 1 MiB."
            )
    if not eligible_total:
        raise PendenciaApuracao(
            "periodo_sem_intersecao",
            "Não há interseção entre apuração, designação e afastamento do titular.",
        )
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
    lines, due, paid = consolidar_saldos(ledger)
    result = {
        "tipo_substituicao": "periodos_v1",
        "periodo": plan.periodo.model_dump(mode="json"),
        "designacao": plan.designacao.model_dump(mode="json"),
        "total_geral_a_receber": moeda(due - paid),
        "totais": {
            "devido": moeda(due),
            "recebido": moeda(paid),
            "saldo": moeda(due - paid),
            "saldo_exato": exato(due - paid),
        },
        "dias_por_competencia": [
            {
                **summary,
                "grupos_exclusao": [
                    {"motivos": list(group), "dias_excluidos": days}
                    for group, days in summary["grupos_exclusao"].items()
                ],
            }
            for summary in days_by_month.values()
        ],
        "segmentos": segments,
        "por_competencia": lines,
        "recebimentos_considerados": [
            item.model_dump(mode="json") for item in received
        ],
        "duplicidades": duplicates,
        "nota_conferencia": "Designação, afastamentos, impedimentos, opção, componentes, percentuais e direito conferidos manualmente pelo RH. Motivos coincidentes não somam dias novamente.",
    }
    validar_tamanho_resultado(result)
    return result
