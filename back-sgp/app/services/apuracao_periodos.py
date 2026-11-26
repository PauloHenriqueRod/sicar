"""Segmentação e conciliação exatas, sem inferir concessões ou direito."""

import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any

from sqlalchemy.orm import joinedload

from app.models.referencias_salariais import EstruturaRemuneratoria, ReferenciaSalarial
from app.schemas.apuracao_periodos import (
    EstadoRemuneratorio,
    ParcelaRecebida,
    PlanoApuracao,
    ValorManual,
)
from app.schemas.referencias_salariais import PosicaoSalarial
from app.services.adicionais_base import (
    componentes_adicional,
    limites_concessao,
    mensal_adicional,
)
from app.services.correlacao_magisterio import (
    INICIO_MS_2025,
    REGRA_MS_2025,
    posicao_ms_2025,
)
from app.services.pendencias import PendenciaApuracao
from app.services.periodos import dividir_intervalo, limites_mensais
from app.services.salary_references import referencia_json
from app.utils.salary_keys import salary_key

VERSION = "periodos_v1"
MAX_PARCELAS = 2000
MAX_RESULT_BYTES = 1024 * 1024


@dataclass
class SaldoCompetencia:
    devido: Fraction = Fraction(0)
    recebido: Fraction = Fraction(0)
    lancamentos: list[str] = field(default_factory=list)


def moeda(value: Fraction) -> str:
    """Meio centavo para longe de zero; nenhuma divisão periódica antecede o empate."""
    cents = (abs(value.numerator) * 200 + value.denominator) // (2 * value.denominator)
    sign = "-" if value < 0 and cents else ""
    return f"{sign}{cents // 100}.{cents % 100:02}"


def exato(value: Fraction) -> dict[str, str]:
    return {"numerador": str(value.numerator), "denominador": str(value.denominator)}


def chave(item):
    return item.rubrica, item.natureza_folha, item.natureza_rubrica


def conciliar_recebimentos(recebidos):
    """Origem documental não integra a identidade do lançamento financeiro."""
    accepted: list[ParcelaRecebida] = []
    ids: dict[str, tuple[tuple[Any, ...], ParcelaRecebida]] = {}
    postings: dict[tuple[str, ...], tuple[tuple[Any, ...], ParcelaRecebida]] = {}
    duplicates: list[dict[str, str]] = []
    aliases: dict[str, str] = {}
    order: dict[str, int] = {}
    for index, item in enumerate(recebidos):
        order.setdefault(item.id, index)
    # Reconcilia todos os pagamentos antes dos estornos: uma segunda via do
    # pagamento pode aparecer depois do estorno na ordem documental recebida.
    for item in sorted(recebidos, key=lambda row: row.operacao == "ESTORNO"):
        posting_key = (
            item.competencia,
            *chave(item),
            item.identificador_folha,
            item.sequencia,
        )
        target_id = aliases.get(item.estorna_id or "", item.estorna_id)
        financial = (posting_key, item.operacao, item.valor, target_id)
        by_id = ids.get(item.id)
        by_key = postings.get(posting_key)
        for existing in (by_id, by_key):
            if existing and existing[0] != financial:
                raise PendenciaApuracao(
                    "lancamento_conflitante",
                    f"O lançamento {item.id} tem identificador ou sequência com dados divergentes. Confira a folha.",
                )
        existing = by_id or by_key
        if existing:
            canonical_id = existing[1].id
            aliases[item.id] = canonical_id
            duplicates.append(
                {"id": item.id, "original_id": canonical_id, "origem": item.origem}
            )
            ids[item.id] = existing
            continue
        ids[item.id] = postings[posting_key] = (financial, item)
        aliases[item.id] = item.id
        accepted.append(item)
    accepted.sort(key=lambda item: order[item.id])
    reversed_amounts: dict[str, Fraction] = defaultdict(Fraction)
    for item in accepted:
        if item.operacao != "ESTORNO":
            continue
        original_id = aliases.get(item.estorna_id or "")
        original = ids.get(original_id or "")
        if original is None or original[1].operacao == "ESTORNO":
            raise PendenciaApuracao(
                "estorno_sem_origem",
                f"Confira o pagamento original do estorno {item.id}.",
            )
        target = original[1]
        if (item.competencia, *chave(item)) != (target.competencia, *chave(target)):
            raise PendenciaApuracao(
                "estorno_incompativel",
                f"O estorno {item.id} deve identificar a mesma competência, rubrica e naturezas do original.",
            )
        reversed_amounts[target.id] += Fraction(item.valor)
        if reversed_amounts[target.id] > target.valor:
            raise PendenciaApuracao(
                "estorno_excedente",
                f"Os estornos excedem o pagamento original {target.id}.",
            )
    return accepted, duplicates


def _referencias(plan, db, *, correlacao_ms=False):
    positions = {plan.estado_inicial.posicao.chave_estrutura()}
    positions.update(
        event.alteracoes.posicao.chave_estrutura()
        for event in plan.eventos
        if event.alteracoes.posicao
    )
    if correlacao_ms:
        anteriores = [plan.estado_inicial.posicao]
        anteriores.extend(
            event.alteracoes.posicao for event in plan.eventos
            if event.efeitos_financeiros < INICIO_MS_2025 and event.alteracoes.posicao
        )
        for anterior in anteriores:
            nova = posicao_ms_2025(anterior)
            if nova is not None:
                positions.add(nova.chave_estrutura())
    # Uma única leitura inclui VB e todas as RTs de todas as posições utilizadas.
    rows = (
        db.query(ReferenciaSalarial)
        .join(ReferenciaSalarial.estrutura)
        .options(
            joinedload(ReferenciaSalarial.estrutura),
            joinedload(ReferenciaSalarial.retribuicoes),
        )
        .populate_existing()
        .filter(
            EstruturaRemuneratoria.chave.in_(positions),
            ReferenciaSalarial.estado == "CONFIRMADA",
            ReferenciaSalarial.inicio_vigencia <= plan.periodo.ultimo_dia_considerado,
            (ReferenciaSalarial.fim_vigencia.is_(None))
            | (ReferenciaSalarial.fim_vigencia >= plan.periodo.inicio),
        )
        .limit(MAX_PARCELAS + 1)
        .all()
    )
    if len(rows) > MAX_PARCELAS:
        raise PendenciaApuracao(
            "limite_referencias",
            "Divida o período: há mais de 2000 referências salariais candidatas.",
        )
    return [(row.estrutura.chave, referencia_json(row)) for row in rows]


def _bases(state, refs, first, last, need_vb, need_rt, *, exigir_referencia=False):
    sources, values = [], {}
    if need_rt and (
        state.posicao.carreira == "TAE" or salary_key(state.titulacao) == "n/a"
    ):
        raise PendenciaApuracao(
            "rt_incompativel",
            "RT exige carreira docente e titulação explícita compatível.",
        )
    missing = [
        component
        for component, needed, manual in (
            ("VB", need_vb, state.vb_manual),
            ("RT", need_rt, state.rt_manual),
        )
        if needed and (manual is None or exigir_referencia)
    ]
    reference = None
    if missing:
        candidates = [
            item
            for key, item in refs
            if key == state.posicao.chave_estrutura()
            and item["inicio_vigencia"] <= first.isoformat()
            and (
                item["fim_vigencia"] is None or item["fim_vigencia"] >= last.isoformat()
            )
        ]
        if len(candidates) != 1:
            pos = state.posicao
            enquadramento = f"{pos.classe_docente} {pos.nivel_docente}" if pos.classe_docente else f"{pos.classificacao_tae} {pos.padrao_tae}"
            raise PendenciaApuracao(
                "referencia_salarial_pendente",
                f"{len(candidates)} referências confirmadas de {first.isoformat()} a {last.isoformat()} "
                f"para {pos.carreira}, posição {enquadramento}, {pos.jornada}, {pos.vinculo}, estrutura {pos.versao_carreira}. "
                "Confira a posição e a vigência no cadastro salarial.",
            )
        reference = candidates[0]
    for component, needed, manual in (
        ("VB", need_vb, state.vb_manual),
        ("RT", need_rt, state.rt_manual),
    ):
        if not needed:
            continue
        if manual is None or exigir_referencia:
            assert reference is not None
            if component == "VB":
                amount = reference["vencimento_basico"]
            else:
                rt = [
                    item
                    for item in reference["retribuicoes"]
                    if salary_key(item["titulacao"]) == salary_key(state.titulacao)
                ]
                if len(rt) != 1:
                    raise PendenciaApuracao(
                        "rt_pendente",
                        f"A referência {reference['id']} não contém RT compatível com a titulação.",
                    )
                amount = rt[0]["valor"]
            values[component] = Fraction(Decimal(amount))
            sources.append(
                {
                    "componente": component,
                    "origem": "referencia_confirmada",
                    "referencia_id": reference["id"],
                    "inicio_vigencia": reference["inicio_vigencia"],
                    "fim_vigencia": reference["fim_vigencia"],
                    "fonte": reference["fonte"],
                    "valor_decimal": amount,
                    "titulacao": state.titulacao,
                }
            )
        if manual is not None:
            values[component] = Fraction(manual.valor)
            sources.append(
                {
                    "componente": component,
                    "origem": "manual_conferida",
                    **manual.model_dump(mode="json", exclude_none=True),
                    **(
                        {"referencia_id": reference["id"], "valor_sugerido": amount}
                        if exigir_referencia
                        else {}
                    ),
                }
            )
    return values, sources


def valor_mensal(rubric, state, bases, first, last=None):
    if rubric.formula == "ADICIONAL_CONFIRMADO":
        return mensal_adicional(state, bases, first, last or first)
    if rubric.formula == "VALOR_MENSAL":
        assert rubric.valor_mensal is not None
        return Fraction(rubric.valor_mensal.valor)
    if rubric.formula == "VB_RT":
        return bases["VB"] + bases["RT"]
    if rubric.formula in ("VB", "RT"):
        return bases[rubric.formula]
    field = {
        "IQ_SOBRE_VB": "percentual_iq",
        "ADICIONAL_SOBRE_VB": "percentual_adicional",
        "ANUENIO_SOBRE_VB": "percentual_anuenio",
    }[rubric.formula]
    percentage = getattr(state, field)
    if percentage is None:
        raise PendenciaApuracao(
            "percentual_pendente",
            f"Informe {field} explicitamente a partir de {first.isoformat()}.",
        )
    if rubric.formula == "IQ_SOBRE_VB" and state.posicao.carreira != "TAE":
        raise PendenciaApuracao(
            "iq_incompativel",
            "IQ exige uma posição TAE; RT docente é uma parcela distinta.",
        )
    return bases["VB"] * Fraction(percentage) / 100


def _reposicionar_ms(estado: EstadoRemuneratorio, papel: str, correlacoes: dict) -> EstadoRemuneratorio:
    nova = posicao_ms_2025(estado.posicao)
    if nova is None:
        return estado
    correlacoes[papel] = {
        "anterior": estado.posicao.model_dump(mode="json", exclude_none=True),
        "vigente": nova.model_dump(mode="json", exclude_none=True),
    }
    return estado.model_copy(update={"posicao": nova, "vb_manual": None, "rt_manual": None})


def apurar_periodos(
    plan: PlanoApuracao,
    db,
    *,
    comparacao: EstadoRemuneratorio | None = None,
    formulas_apoio: dict[date, set[str]] | None = None,
    comparacoes_mensais: Mapping[str, dict[str, ValorManual]] | None = None,
):
    accepted, duplicates = conciliar_recebimentos(plan.recebidos)
    start, end = plan.periodo.inicio, plan.periodo.ultimo_dia_considerado
    correlacao_ms = getattr(plan, "modalidade", None) == "DOCENTE" and start < INICIO_MS_2025 <= end
    refs = _referencias(plan, db, correlacao_ms=correlacao_ms)
    limits = limites_mensais(start, end)
    events = sorted(
        plan.eventos, key=lambda event: (event.efeitos_financeiros, event.id)
    )
    limits.update(event.efeitos_financeiros.toordinal() for event in events)
    limits.update(limites_concessao(plan.estado_inicial.adicional))
    for event in events:
        limits.update(limites_concessao(event.alteracoes.adicional))
    for item in plan.interrupcoes:
        limits.update(
            (item.inicio.toordinal(), item.ultimo_dia_considerado.toordinal() + 1)
        )
    for _, item in refs:
        limits.add(date.fromisoformat(item["inicio_vigencia"]).toordinal())
        if item["fim_vigencia"] is not None:
            limits.add(date.fromisoformat(item["fim_vigencia"]).toordinal() + 1)
    state = plan.estado_inicial
    event_index = 0
    applied = []
    ledger: dict[tuple[str, ...], SaldoCompetencia] = defaultdict(SaldoCompetencia)
    segments: list[dict[str, Any]] = []
    parcel_count = 0
    segment_bytes = 0
    comparison_default = comparacao
    correlacoes: dict[str, dict] = {}
    for first, last, days, days_month in dividir_intervalo(start, end, limits):
        if correlacao_ms and first == INICIO_MS_2025:
            state = _reposicionar_ms(state, "DESTINO", correlacoes)
            if comparison_default is not None:
                comparison_default = _reposicionar_ms(comparison_default, "ORIGEM", correlacoes)
        mensal = (comparacoes_mensais or {}).get(f"{first:%Y-%m}")
        comparacao = comparison_default
        if mensal is not None and comparison_default is not None:
            comparacao = comparison_default.model_copy(update=mensal)
        while (
            event_index < len(events)
            and events[event_index].efeitos_financeiros <= first
        ):
            effective = events[event_index].efeitos_financeiros
            changes = {}
            same_date = []
            while (
                event_index < len(events)
                and events[event_index].efeitos_financeiros == effective
            ):
                event = events[event_index]
                changes.update(event.alteracoes.model_dump(exclude_unset=True))
                same_date.append(event)
                event_index += 1
            # Não transporta bases manuais de uma posição/titulação para outra.
            new_position = changes.get("posicao")
            if (
                new_position is not None
                and PosicaoSalarial.model_validate(new_position).chave_estrutura()
                != state.posicao.chave_estrutura()
            ):
                changes = {"vb_manual": None, "rt_manual": None, **changes}
            elif "titulacao" in changes and salary_key(
                changes["titulacao"]
            ) != salary_key(state.titulacao):
                changes = {"rt_manual": None, **changes}
            state = EstadoRemuneratorio.model_validate(
                {**state.model_dump(), **changes}
            )
            applied.extend(same_date)
        interruptions = [
            item
            for item in plan.interrupcoes
            if item.inicio <= first <= item.ultimo_dia_considerado
        ]
        computed_days = 0 if interruptions else days
        apoio = set().union(
            *(
                value
                for when, value in (formulas_apoio or {}).items()
                if first <= when <= last
            )
        )
        formulas = {
            item.formula
            for item in plan.rubricas
            if getattr(item, "apurar_principal", True) or item.formula in apoio
        }
        need_vb = bool(
            formulas
            & {"VB", "VB_RT", "IQ_SOBRE_VB", "ADICIONAL_SOBRE_VB", "ANUENIO_SOBRE_VB"}
        )
        need_rt = bool(formulas & {"RT", "VB_RT"})
        current_components = (
            componentes_adicional(state, first, last)
            if "ADICIONAL_CONFIRMADO" in formulas
            else set()
        )
        original_components = (
            componentes_adicional(comparacao, first, last)
            if comparacao is not None and "ADICIONAL_CONFIRMADO" in formulas
            else set()
        )
        bases, sources = _bases(
            state,
            refs,
            first,
            last,
            need_vb or "VB" in current_components,
            need_rt or "RT" in current_components,
            exigir_referencia=comparacao is not None,
        )
        if "ADICIONAL_CONFIRMADO" in formulas and state.adicional is not None:
            sources.append(
                {
                    "componente": "ADICIONAL_CONFIRMADO",
                    "origem": "concessao_declarada",
                    **state.adicional.model_dump(mode="json"),
                }
            )
        origin_bases = {}
        if comparacao is not None:
            origin_bases, origin_sources = _bases(
                comparacao,
                refs,
                first,
                last,
                need_vb or "VB" in original_components,
                need_rt or "RT" in original_components,
                exigir_referencia=True,
            )
            if "ADICIONAL_CONFIRMADO" in formulas and comparacao.adicional is not None:
                origin_sources.append(
                    {
                        "componente": "ADICIONAL_CONFIRMADO",
                        "origem": "concessao_declarada",
                        **comparacao.adicional.model_dump(mode="json"),
                    }
                )
            sources = [{**item, "papel": "DESTINO"} for item in sources] + [
                {**item, "papel": "ORIGEM"} for item in origin_sources
            ]
        reflex_origin_bases = None
        if comparacoes_mensais and apoio and comparison_default is not None:
            reflex_origin_bases, reflex_sources = _bases(
                comparison_default, refs, first, last,
                need_vb or "VB" in original_components,
                need_rt or "RT" in original_components,
                exigir_referencia=True,
            )
            sources.extend({**item, "papel": "ORIGEM_REFLEXO"} for item in reflex_sources)
        parcels = []
        rules = [item.regra.model_dump(mode="json") for item in plan.rubricas]
        rules.extend(event.regra.model_dump(mode="json") for event in applied)
        rules.extend(item.regra.model_dump(mode="json") for item in interruptions)
        if correlacoes:
            rules.append({**REGRA_MS_2025, "posicoes_na_transicao": correlacoes})
        for rubric in plan.rubricas:
            used = rubric.formula in formulas
            monthly = (
                valor_mensal(rubric, state, bases, first, last) if used else Fraction(0)
            )
            if rubric.formula == "VALOR_MENSAL":
                assert rubric.valor_mensal is not None
                sources.append(
                    {
                        "componente": rubric.rubrica,
                        "origem": "manual_conferida",
                        **rubric.valor_mensal.model_dump(mode="json"),
                    }
                )
            original_monthly = (
                valor_mensal(rubric, comparacao, origin_bases, first, last)
                if comparacao is not None and used
                else Fraction(0)
            )
            destination_monthly = monthly
            monthly -= original_monthly
            value = (
                monthly * computed_days / days_month
                if getattr(rubric, "apurar_principal", True)
                else Fraction(0)
            )
            competence = f"{first.year:04}-{first.month:02}"
            key = (competence, *chave(rubric))
            ledger[key].devido += value
            parcels.append(
                {
                    "rubrica": rubric.rubrica,
                    "natureza_folha": rubric.natureza_folha,
                    "natureza_rubrica": rubric.natureza_rubrica,
                    "formula": rubric.formula,
                    "valor_mensal_exato": exato(monthly),
                    "devido": moeda(value),
                    "devido_exato": exato(value),
                    "regra": rubric.regra.model_dump(mode="json"),
                }
            )
            if reflex_origin_bases is not None and rubric.formula in apoio and comparison_default is not None:
                parcels[-1]["valor_mensal_reflexo_exato"] = exato(destination_monthly - valor_mensal(rubric, comparison_default, reflex_origin_bases, first, last))
            if comparacao is not None:
                parcels[-1].update(
                    valor_mensal_origem_exato=exato(original_monthly),
                    valor_mensal_destino_exato=exato(destination_monthly),
                )
            if hasattr(rubric, "apurar_principal"):
                parcels[-1]["incluido_principal"] = rubric.apurar_principal
            parcel_count += 1
            if parcel_count > MAX_PARCELAS:
                raise PendenciaApuracao(
                    "limite_segmentos",
                    "Divida a apuração: máximo de 2000 parcelas devidas por cálculo.",
                )
        segments.append(
            {
                "id": len(segments) + 1,
                "inicio": first.isoformat(),
                "ultimo_dia_considerado": last.isoformat(),
                "competencia": competence,
                "dias_calendario": days,
                "dias_computados": computed_days,
                "dias_reais_mes": days_month,
                "estado": state.model_dump(mode="json"),
                "eventos_aplicados": [event.id for event in applied],
                "interrupcoes": [item.id for item in interruptions],
                "referencias_regras": rules,
                "referencias_tabelas": sources,
                "parcelas": parcels,
            }
        )
        segment_bytes += len(
            json.dumps(segments[-1], ensure_ascii=False).encode("utf-8")
        )
        if segment_bytes > MAX_RESULT_BYTES:
            raise PendenciaApuracao(
                "limite_resultado", "Divida o período: o detalhamento excede 1 MiB."
            )
    for item in accepted:
        key = (item.competencia, *chave(item))
        ledger[key].recebido += Fraction(item.valor) * (
            -1 if item.operacao == "ESTORNO" else 1
        )
        ledger[key].lancamentos.append(item.id)
    lines, total_due, total_received = consolidar_saldos(ledger)
    result = {
        "tipo_apuracao": VERSION,
        "periodo": plan.periodo.model_dump(mode="json"),
        "data_documento": plan.data_documento.isoformat()
        if plan.data_documento
        else None,
        "data_implantacao": plan.data_implantacao.isoformat()
        if plan.data_implantacao
        else None,
        "total_geral_a_receber": moeda(total_due - total_received),
        "totais": {
            "devido": moeda(total_due),
            "recebido": moeda(total_received),
            "saldo": moeda(total_due - total_received),
            "saldo_exato": exato(total_due - total_received),
        },
        "por_competencia": lines,
        "segmentos": segments,
        "recebimentos_considerados": [
            item.model_dump(mode="json") for item in accepted
        ],
        "duplicidades": duplicates,
        "eventos": [
            {
                **event.model_dump(mode="json"),
                "alteracoes": event.alteracoes.model_dump(
                    mode="json", exclude_unset=True
                ),
            }
            for event in events
        ],
        "nota_conferencia": "Período, bases, naturezas, regras, interrupções e direito conferidos manualmente pelo RH. Valores monetários em texto decimal; totais acumulados antes do arredondamento.",
    }
    validar_tamanho_resultado(result)
    return result


def validar_tamanho_resultado(result):
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_RESULT_BYTES:
        raise PendenciaApuracao(
            "limite_resultado", "Divida o período: o resultado excede 1 MiB."
        )


def consolidar_saldos(ledger):
    lines, total_due, total_received = [], Fraction(0), Fraction(0)
    for (competence, code, nature, kind), balance in sorted(ledger.items()):
        due, received, posting_ids = (
            balance.devido,
            balance.recebido,
            balance.lancamentos,
        )
        lines.append(
            {
                "competencia": competence,
                "rubrica": code,
                "natureza_folha": nature,
                "natureza_rubrica": kind,
                "devido": moeda(due),
                "recebido": moeda(received),
                "saldo": moeda(due - received),
                "devido_exato": exato(due),
                "recebido_exato": exato(received),
                "saldo_exato": exato(due - received),
                "lancamentos_recebidos": posting_ids,
            }
        )
        sign = -1 if kind == "D" else 1
        total_due += due * sign
        total_received += received * sign
    return lines, total_due, total_received
