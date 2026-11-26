"""Diferenças e reflexos explícitos, sempre acumulados como frações exatas."""

from collections import defaultdict
from fractions import Fraction

from app.schemas.progressao_eventos import PlanoProgressao
from app.services.apuracao_periodos import (
    PendenciaApuracao,
    SaldoCompetencia,
    apurar_periodos,
    consolidar_saldos,
    exato,
    moeda,
    validar_tamanho_resultado,
)


def fracao(value):
    return Fraction(int(value["numerador"]), int(value["denominador"]))


def calcular_progressao_eventos(plan: PlanoProgressao, db):
    # Aplicar ao calcular preserva a leitura e a repetição idempotente dos snapshots anteriores.
    if any(item.rubrica in ("DIF-VB", "DIF-RT") for item in plan.rubricas):
        if not plan.bases_mensais_origem:
            raise PendenciaApuracao("base_mensal_ausente", "Informe o VB e a RT pagos em cada competência da progressão docente.")
        for item in plan.bases_mensais_origem:
            if item.rt is None:
                raise PendenciaApuracao("rt_mensal_ausente", f"Confira a RT paga em {item.competencia}, inclusive zero quando confirmado.")
    apoio: dict = {}
    for event in plan.reflexos:
        apoio.setdefault(event.data_base, set()).update(event.formulas_base)
    monthly = {
        item.competencia: {"vb_manual": item.vb, **({"rt_manual": item.rt} if item.rt is not None else {})}
        for item in plan.bases_mensais_origem
    }
    if monthly:
        start, end = plan.periodo.inicio, plan.periodo.ultimo_dia_considerado
        for index in range(start.year * 12 + start.month - 1, end.year * 12 + end.month):
            year, month = divmod(index, 12)
            competencia = f"{year:04}-{month + 1:02}"
            if competencia not in monthly:
                raise PendenciaApuracao("base_mensal_ausente", f"Faltam valores da folha em {competencia}. Confira a ficha ou informe a base mensal manualmente.")
    result = apurar_periodos(
        plan, db, comparacao=plan.estado_inicial, formulas_apoio=apoio,
        comparacoes_mensais=monthly,
    )
    result = aplicar_reflexos(plan, result)
    result.update(
        modalidade=plan.modalidade,
        tipo_progressao="eventos_v1",
        estado_origem=plan.estado_inicial.model_dump(mode="json"),
        nota_comparacao="Diferenças contra a posição de origem, com as tabelas vigentes em cada segmento e eventuais correções individuais de VB/RT discriminadas nas fontes. Recebimentos representam somente diferenças já pagas. Direito e regras conferidos pelo RH.",
    )
    if monthly:
        result["bases_mensais_origem"] = [item.model_dump(mode="json") for item in plan.bases_mensais_origem]
        result["nota_comparacao"] = "VB da posição de destino contra a base mensal integral conferida em cada competência da ficha. Diferenças já pagas são abatidas separadamente; parcelas proporcionais/mistas exigem revisão. RT e demais componentes mantêm suas regras explícitas."
        if all(item.rt is not None for item in plan.bases_mensais_origem):
            result["nota_comparacao"] = "VB e RT da posição de destino comparados separadamente com os valores mensais integrais pagos e conferidos pelo RH. Abatimentos de diferenças já pagas e reflexos são discriminados à parte."
    validar_tamanho_resultado(result)
    return result


def aplicar_reflexos(plan, result):
    excluded = {
        (r.rubrica, r.natureza_folha, r.natureza_rubrica)
        for r in plan.rubricas
        if r.formula == "ADICIONAL_CONFIRMADO" and not r.apurar_principal
    }
    if any(
        (p.rubrica, p.natureza_folha, p.natureza_rubrica) in excluded
        for p in plan.recebidos
    ):
        raise PendenciaApuracao(
            "recebimento_principal_excluido",
            "O principal foi excluído deste fluxo. Informe somente pagamentos dos reflexos nele apurados.",
        )
    ledger = defaultdict(SaldoCompetencia)
    for line in result["por_competencia"]:
        ledger[
            (
                line["competencia"],
                line["rubrica"],
                line["natureza_folha"],
                line["natureza_rubrica"],
            )
        ] = SaldoCompetencia(
            fracao(line["devido_exato"]),
            fracao(line["recebido_exato"]),
            line["lancamentos_recebidos"],
        )
    reflexos = []
    payments = {item["id"]: item for item in result["recebimentos_considerados"]}
    aliases = {item["id"]: item["original_id"] for item in result["duplicidades"]}
    assigned: set[str] = set()
    dependent_keys = set()
    for event in plan.reflexos:
        segment = next(
            item
            for item in result["segmentos"]
            if item["inicio"]
            <= event.data_base.isoformat()
            <= item["ultimo_dia_considerado"]
        )
        if "ADICIONAL_CONFIRMADO" in event.formulas_base:
            concession = segment["estado"].get("adicional")
            if concession is None or event.origem != concession["identificador"]:
                raise PendenciaApuracao(
                    "origem_reflexo_incompativel",
                    "A origem do reflexo deve identificar a concessão utilizada na data-base.",
                )
        base = sum(
            (
                fracao(item.get("valor_mensal_reflexo_exato", item["valor_mensal_exato"]))
                * (-1 if item["natureza_rubrica"] == "D" else 1)
                for item in segment["parcelas"]
                if item["formula"] in event.formulas_base
            ),
            Fraction(0),
        )
        amount = base * event.avos / (36 if event.tipo == "FERIAS_UM_TERCO" else 12)
        ledger[
            (
                event.competencia,
                event.rubrica,
                event.natureza_folha,
                event.natureza_rubrica,
            )
        ].devido += amount
        previous = []
        for identifier in event.pagamentos_anteriores:
            identifier = aliases.get(identifier, identifier)
            payment = payments.get(identifier)
            if payment is None or (
                payment["competencia"],
                payment["rubrica"],
                payment["natureza_folha"],
                payment["natureza_rubrica"],
            ) != (
                event.competencia,
                event.rubrica,
                event.natureza_folha,
                event.natureza_rubrica,
            ):
                raise PendenciaApuracao(
                    "pagamento_reflexo_incompativel",
                    f"Confira o pagamento anterior do reflexo {event.id}.",
                )
            if identifier in assigned:
                raise PendenciaApuracao(
                    "pagamento_reflexo_duplicado",
                    "Não atribua o mesmo pagamento anterior a duas parcelas de reflexo.",
                )
            assigned.add(identifier)
            previous.append(payment)
        if "ADICIONAL_CONFIRMADO" in event.formulas_base:
            dependent_keys.add(
                (
                    event.competencia,
                    event.rubrica,
                    event.natureza_folha,
                    event.natureza_rubrica,
                )
            )
        reflexos.append(
            {
                **event.model_dump(mode="json"),
                "pagamentos_anteriores": previous,
                "base_exata": exato(base),
                "devido": moeda(amount),
                "devido_exato": exato(amount),
                "segmento_base": segment["id"],
                "referencias_tabelas": segment["referencias_tabelas"],
            }
        )
    for identifier, payment in payments.items():
        if (
            payment["competencia"],
            payment["rubrica"],
            payment["natureza_folha"],
            payment["natureza_rubrica"],
        ) in dependent_keys and identifier not in assigned:
            raise PendenciaApuracao(
                "pagamento_reflexo_nao_discriminado",
                "Vincule cada pagamento anterior do reflexo de adicional ao evento correspondente.",
            )
    lines, due, received = consolidar_saldos(ledger)
    result.update(
        reflexos=reflexos,
        por_competencia=lines,
        total_geral_a_receber=moeda(due - received),
        totais={
            "devido": moeda(due),
            "recebido": moeda(received),
            "saldo": moeda(due - received),
            "saldo_exato": exato(due - received),
        },
    )
    validar_tamanho_resultado(result)
    return result
