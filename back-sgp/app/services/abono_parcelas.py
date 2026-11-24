"""Vinculação por parcela; datas de folha e de direito não são intercambiáveis."""

import calendar
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import NoReturn

from app.schemas.abono_parcelas import PlanoAbono
from app.services.apuracao_periodos import exato, moeda, validar_tamanho_resultado
from app.services.pendencias import PendenciaApuracao
from app.services.periodos import dividir_intervalo


def pending(code, message) -> NoReturn:
    raise PendenciaApuracao(code, message)


def conciliar_abono(records):
    """Deduplica identidade de folha; referências entre competências são explícitas."""
    aliases, ids, postings, duplicates, accepted = {}, {}, {}, [], []
    for row in records:
        if row.valor is None or not row.conferido:
            pending(
                "lancamento_abono_pendente",
                f"Confira valor, operação e origem do lançamento {row.id}; desconhecido não é zero.",
            )
        key = (
            row.competencia,
            row.rubrica,
            row.natureza_folha,
            row.natureza_rubrica,
            row.identificador_folha,
            row.sequencia,
        )
        signature = (
            key,
            row.valor,
            row.operacao,
            row.papel,
            row.categoria,
            row.parcela_id,
        )
        existing_id, existing_key = ids.get(row.id), postings.get(key)
        for existing in (existing_id, existing_key):
            if existing and existing[0] != signature:
                pending(
                    "lancamento_abono_conflitante",
                    "Mesmo identificador ou lançamento de folha com valor, operação ou parcela divergentes.",
                )
        existing = existing_id or existing_key
        if existing:
            aliases[row.id] = existing[1].id
            duplicates.append(
                {"id": row.id, "original_id": existing[1].id, "origem": row.origem}
            )
            ids[row.id] = existing
        else:
            ids[row.id] = postings[key] = (signature, row)
            aliases[row.id] = row.id
            accepted.append(row)
    canonical = {row.id: row for row in accepted}
    for row in records:
        original = canonical[aliases[row.id]]
        for field in ("estorna_id", "complementa_id"):
            left, right = getattr(row, field), getattr(original, field)
            if aliases.get(left, left) != aliases.get(right, right):
                pending(
                    "lancamento_abono_conflitante",
                    "Cópias do mesmo lançamento apontam para origens diferentes.",
                )
    reversed_amounts = {}
    for row in accepted:
        if row.operacao == "LANCAMENTO":
            expected = "D" if row.papel == "CONTRIBUICAO" else "R"
            if row.natureza_rubrica != expected:
                pending(
                    "natureza_abono_pendente",
                    "Confira natureza e operação: desconto previdenciário e crédito de abono são fatos distintos.",
                )
            continue
        reference = row.estorna_id if row.operacao == "ESTORNO" else row.complementa_id
        target = canonical.get(aliases.get(reference, reference))
        if (
            target is None
            or target.operacao == "ESTORNO"
            or (row.operacao == "COMPLEMENTO" and target.operacao != "LANCAMENTO")
        ):
            pending(
                "acerto_abono_sem_origem",
                "Associe o acerto ao lançamento original; estorno também pode apontar para complemento.",
            )
        if (row.papel, row.categoria, row.parcela_id, row.rubrica) != (
            target.papel,
            target.categoria,
            target.parcela_id,
            target.rubrica,
        ):
            pending(
                "acerto_abono_incompativel",
                "Acerto e origem devem pertencer ao mesmo papel, categoria, rubrica e parcela de direito.",
            )
        if (
            row.operacao == "COMPLEMENTO"
            and row.natureza_rubrica != target.natureza_rubrica
        ):
            pending(
                "natureza_abono_pendente",
                "Complemento deve preservar a natureza do lançamento original.",
            )
        if row.operacao == "ESTORNO":
            reversed_amounts[target.id] = reversed_amounts.get(
                target.id, Fraction(0)
            ) + Fraction(row.valor)
            if reversed_amounts[target.id] > target.valor:
                pending(
                    "estorno_abono_excedente",
                    "Estornos excedem o valor do lançamento original ou complemento vinculado.",
                )
    return accepted, duplicates


def calcular_abono_parcelas(plan: PlanoAbono):
    start, end = (
        plan.periodo_direito.inicio,
        plan.periodo_direito.ultimo_dia_considerado,
    )
    if not plan.conferido_pelo_rh or not plan.regra.confirmada:
        pending(
            "direito_abono_pendente",
            "Confirme o período de direito, a regra e os dados pelo RH; PSS não comprova direito ao abono.",
        )
    if not plan.regra.cobre(start) or not plan.regra.cobre(end):
        pending(
            "regra_abono_sem_vigencia",
            "A regra confirmada deve cobrir o período de direito informado.",
        )
    mappings = {(row.rubrica, row.categoria): row for row in plan.mapeamentos}
    parcels = {row.id: row for row in plan.parcelas}
    expected_months = {
        f"{first.year:04}-{first.month:02}"
        for first, _, _, _ in dividir_intervalo(start, end, set())
    }
    regular = {
        row.competencia_direito for row in plan.parcelas if row.categoria == "REGULAR"
    }
    if regular != expected_months:
        pending(
            "cobertura_abono_pendente",
            "Confira todas as competências regulares do período; mês ausente não representa zero.",
        )
    coverage = {row.exercicio: row for row in plan.cobertura_13}
    if set(coverage) != set(range(start.year, end.year + 1)):
        pending(
            "cobertura_13_abono_pendente",
            "Confirme inclusão ou não aplicabilidade do 13º em cada exercício do período.",
        )
    included = {
        row.exercicio_13 for row in plan.parcelas if row.categoria == "DECIMO_TERCEIRO"
    }
    for year, coverage_row in coverage.items():
        if coverage_row.situacao == "PENDENTE" or (
            (coverage_row.situacao == "INCLUIDO") != (year in included)
        ):
            pending(
                "cobertura_13_abono_pendente",
                "Cobertura de 13º desconhecida ou incompatível com as parcelas incluídas.",
            )
    if not included <= set(coverage):
        pending(
            "cobertura_13_abono_pendente",
            "Parcela de 13º fora dos exercícios conferidos.",
        )
    accepted, duplicates = conciliar_abono(plan.lancamentos)
    all_records = {row.id: row for row in plan.lancamentos}
    for doc in plan.documentos:
        if not doc.vinculo_confirmado or doc.vinculo_identificado != plan.vinculo_id:
            pending(
                "documento_abono_pendente",
                "Confira pessoa e vínculo de cada documento antes de calcular.",
            )
        for observation in doc.observacoes:
            if observation.decisao == "DESCARTADO" and observation.justificativa:
                continue
            record = all_records.get(observation.lancamento_id or "")
            if observation.decisao != "UTILIZADO" or record is None:
                pending(
                    "observacao_abono_pendente",
                    "Revise cada observação: vincule a um lançamento ou justifique sua exclusão.",
                )
            if (
                (
                    observation.rubrica,
                    observation.competencia,
                    observation.natureza_rubrica,
                    observation.sequencia,
                )
                != (
                    record.rubrica,
                    record.competencia,
                    record.natureza_rubrica,
                    record.sequencia,
                )
                or observation.valor_observado is None
                or record.valor is None
                or abs(Decimal(observation.valor_observado)) != record.valor
            ):
                pending(
                    "observacao_abono_divergente",
                    "Observação e lançamento divergem; confira e corrija os dados antes de confirmar.",
                )
            if (
                Decimal(observation.valor_observado) < 0
                and record.operacao != "ESTORNO"
                and not (
                    observation.correcao_sinal_confirmada and observation.justificativa
                )
            ):
                pending(
                    "sinal_observado_abono_pendente",
                    "Valor observado negativo exige estorno vinculado ou correção de sinal explicitamente confirmada e justificada pelo RH.",
                )
    for row in accepted:
        parcel = parcels.get(row.parcela_id)
        mapping = mappings.get((row.rubrica, row.categoria))
        if parcel is None or row.categoria != parcel.categoria:
            pending(
                "parcela_abono_sem_vinculo",
                "Vincule cada lançamento à parcela regular ou ao exercício de 13º correto.",
            )
        if (
            mapping is None
            or not mapping.confirmado
            or (mapping.papel, mapping.categoria) != (row.papel, row.categoria)
        ):
            pending(
                "rubrica_abono_pendente",
                "Confirme o mapeamento da rubrica por papel e categoria; descrição não é confirmação.",
            )
        if row.papel == "ABONO" and row.rubrica != parcel.rubrica_abono:
            pending(
                "rubrica_abono_incompativel",
                "O pagamento deve identificar a rubrica de abono da parcela vinculada.",
            )
    rows = []
    total_due = total_paid = Fraction(0)
    annual: dict[str, list[Fraction]] = {}
    for parcel in plan.parcelas:
        reference = parcel.periodo_referencia
        if reference.inicio > end or reference.ultimo_dia_considerado < start:
            pending(
                "parcela_abono_fora_direito",
                "Parcela fora do período de direito confirmado; remova ou corrija a associação explicitamente.",
            )
        if parcel.categoria == "REGULAR" and (
            reference.inicio.day != 1
            or reference.ultimo_dia_considerado.day
            != calendar.monthrange(reference.inicio.year, reference.inicio.month)[1]
        ):
            pending(
                "periodo_regular_abono_incompleto",
                "Informe o mês completo como referência regular; a elegibilidade parcial é conferida separadamente.",
            )
        if parcel.categoria == "DECIMO_TERCEIRO" and (
            parcel.exercicio_13 is None
            or reference.inicio != date(parcel.exercicio_13, 1, 1)
            or reference.ultimo_dia_considerado != date(parcel.exercicio_13, 12, 31)
        ):
            pending(
                "periodo_13_abono_incompleto",
                "Informe o ano completo como referência do 13º; elegibilidade parcial deve ser confirmada separadamente.",
            )
        mapping = mappings.get((parcel.rubrica_abono, parcel.categoria))
        if (
            mapping is None
            or not mapping.confirmado
            or mapping.papel != "ABONO"
            or mapping.categoria != parcel.categoria
        ):
            pending(
                "rubrica_abono_pendente",
                "Confirme a rubrica do abono devido para cada categoria.",
            )
        contributions = [
            row
            for row in accepted
            if row.parcela_id == parcel.id and row.papel == "CONTRIBUICAO"
        ]
        payments = [
            row
            for row in accepted
            if row.parcela_id == parcel.id and row.papel == "ABONO"
        ]
        if parcel.contribuicao == "PENDENTE" or parcel.recebimento == "PENDENTE":
            pending(
                "dados_parcela_abono_pendentes",
                "Contribuição ou pesquisa de pagamentos desconhecida; confirme cada parcela.",
            )
        if parcel.contribuicao == "IDENTIFICADA" and not contributions:
            pending(
                "contribuicao_abono_ausente",
                "Contribuição identificada exige lançamento; ausência não é zero.",
            )
        if (parcel.recebimento == "IDENTIFICADO") != bool(payments):
            pending(
                "recebimento_abono_pendente",
                "Confirmação de pagamentos incompatível com os lançamentos vinculados.",
            )
        contribution = sum(
            (
                Fraction(row.valor) * (-1 if row.operacao == "ESTORNO" else 1)
                for row in contributions
            ),
            Fraction(0),
        )
        paid = sum(
            (
                Fraction(row.valor) * (-1 if row.operacao == "ESTORNO" else 1)
                for row in payments
            ),
            Fraction(0),
        )
        if (
            contribution < 0
            or paid < 0
            or (parcel.contribuicao == "ZERO_CONFIRMADO" and contribution != 0)
        ):
            pending(
                "contribuicao_abono_conflitante",
                "Confira descontos, restituições e zero declarado; não se zera saldo inconsistente automaticamente.",
            )
        partial = reference.inicio < start or reference.ultimo_dia_considerado > end
        if partial and parcel.valor_elegivel is None:
            pending(
                "base_parcial_abono_pendente",
                "Direito parcial exige valor elegível e justificativa conferidos; não há rateio automático da PSS.",
            )
        due = (
            Fraction(parcel.valor_elegivel.valor)
            if parcel.valor_elegivel
            else contribution
        )
        if due > contribution:
            pending(
                "base_abono_excede_desconto",
                "Valor elegível excede a contribuição efetiva conciliada; confira a base da parcela.",
            )
        first, last = (
            max(start, reference.inicio),
            min(end, reference.ultimo_dia_considerado),
        )
        row = {
            "parcela_id": parcel.id,
            "categoria": parcel.categoria,
            "competencia_direito": parcel.competencia_direito,
            "exercicio_13": parcel.exercicio_13,
            "periodo_considerado": {
                "inicio": first.isoformat(),
                "ultimo_dia_considerado": last.isoformat(),
            },
            "rubrica": parcel.rubrica_abono,
            "natureza_folha_devida": parcel.natureza_folha_devida,
            "contribuicao_conciliada": moeda(contribution),
            "devido": moeda(due),
            "recebido": moeda(paid),
            "saldo": moeda(due - paid),
            "devido_exato": exato(due),
            "recebido_exato": exato(paid),
            "saldo_exato": exato(due - paid),
            "contribuicoes_ids": [row.id for row in contributions],
            "pagamentos_ids": [row.id for row in payments],
            "regra": plan.regra.model_dump(mode="json"),
            "fonte_conferencia": parcel.fonte_conferencia,
            "valor_elegivel": parcel.valor_elegivel.model_dump(mode="json")
            if parcel.valor_elegivel
            else None,
            "justificativa_elegivel": parcel.justificativa_elegivel,
        }
        rows.append(row)
        year = parcel.exercicio_13 or reference.inicio.year
        amounts = annual.setdefault(str(year), [Fraction(0), Fraction(0)])
        amounts[0] += due
        amounts[1] += paid
        total_due += due
        total_paid += paid
    result = {
        "tipo_abono": "parcelas_v1",
        "periodo": plan.periodo_direito.model_dump(mode="json"),
        "parcelas": rows,
        "lancamentos_considerados": [row.model_dump(mode="json") for row in accepted],
        "duplicidades": duplicates,
        "consolidado_anual": {
            year: {
                "devido": moeda(amounts[0]),
                "recebido": moeda(amounts[1]),
                "saldo": moeda(amounts[0] - amounts[1]),
            }
            for year, amounts in annual.items()
        },
        "totais": {
            "devido": moeda(total_due),
            "recebido": moeda(total_paid),
            "saldo": moeda(total_due - total_paid),
            "saldo_exato": exato(total_due - total_paid),
        },
        "total_geral": moeda(total_due - total_paid),
        "saldo_parcelas_calculadas": moeda(total_due - total_paid),
        "nota_conferencia": "Direito, rubricas, elegibilidade, vínculo e cobertura de dados conferidos manualmente pelo RH. PSS não comprova direito. Competência da folha preservada, sem rateio automático.",
    }
    validar_tamanho_resultado(result)
    return result
