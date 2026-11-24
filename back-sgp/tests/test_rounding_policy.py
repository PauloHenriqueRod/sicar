"""Regressões da regra de meio centavo para cima confirmada pelo usuário."""
import calendar
from decimal import Decimal
from fractions import Fraction

import pytest

from app.services.calculation_service import resolve_salary
from app.services.motor_calculos_rh import MotorCalculosRH


def expected_cents(value: Fraction) -> float:
    """Oráculo racional, independente do contexto e quantizador Decimal do motor."""
    cents = abs(value) * 100 + Fraction(1, 2)
    rounded = cents.numerator // cents.denominator
    return (-rounded if value < 0 else rounded) / 100


@pytest.mark.parametrize("base_cents,months,days,month,year", [
    (7, "0.5", 16, 2, 2026), (-7, "0.5", 16, 2, 2026),
    (1, "0", 14, 2, 2026), (-1, "0", 14, 2, 2026),
    (31, "1.5", 15, 1, 2026), (29, "0.5", 14, 2, 2024),
])
def test_progression_preserves_exact_tie_through_calendar_rate(base_cents, months, days, month, year):
    expected = expected_cents(
        Fraction(base_cents, 100) * (Fraction(months) + Fraction(days, calendar.monthrange(year, month)[1]))
    )
    result = MotorCalculosRH.calcular_progressao_docente(
        salario_antigo=max(0, -base_cents) / 100,
        salario_novo=max(0, base_cents) / 100,
        meses_diferenca=float(months), dias_proporcionais=days, aplica_proporcao_dias=True,
        mes_proporcao=month, ano_proporcao=year,
        quantidade_reflexos_ferias=0, quantidade_reflexos_13=0,
    )
    assert result["total_geral_devido"] == expected
    assert result["total_com_reflexos"] == expected


def test_substitution_multiplies_before_periodic_division():
    result = MotorCalculosRH.calcular_substituicao(0.01, 0, 14, mes=2, ano=2026)
    assert result["valor_proporcional_devido"] == 0.01


def test_insalubridade_sums_exact_months_before_final_rounding():
    result = MotorCalculosRH.calcular_retroativo_insalubridade({"2026-01": 0.015, "2026-02": 0.045})
    assert [item["valor_calculado"] for item in result["detalhamento_mensal"]] == [0.02, 0.05]
    # 0,015 + 0,045 = 0,060; não somar 0,02 + 0,05.
    assert result["total_acumulado"] == 0.06


def test_abono_annual_display_does_not_feed_overall_total():
    result = MotorCalculosRH.calcular_abono_permanencia({2025: [0.005], 2026: [0.005]})
    assert result == {"total_geral": 0.01, "consolidado_anual": {2025: 0.01, 2026: 0.01}}


@pytest.mark.parametrize("received,expected", [(0, 0.01), (0.01, -0.01)])
def test_termination_rounds_positive_and_negative_half_cent(received, expected):
    result = MotorCalculosRH.calcular_rescisao_substituto(
        salario_mensal=0.01, meses_completos_13o=6,
        valores_ja_recebidos={"82407_decimo_terceiro": received}, mes_rescisao=2, ano_rescisao=2026,
    )
    rubric = result["detalhamento_rubricas"]["82407_decimo_terceiro"]
    assert rubric["devido"] == 0.01  # Exibição; a diferença usa o devido interno de 0,005.
    assert rubric["diferenca"] == expected
    assert result["total_liquido_a_receber"] == expected


def test_previous_year_keeps_decimal_input_until_rounding_and_sum():
    result = MotorCalculosRH.calcular_exercicio_anterior([
        {"periodo": "01/2026", "v_dev": Decimal("1234.56499999999999999"), "v_rec": 0},
        {"periodo": "02/2026", "v_dev": 2.675, "v_rec": 0},
        {"periodo": "03/2026", "v_dev": 0, "v_rec": 2.675},
    ])
    assert [item["diferenca_salarial"] for item in result["detalhamento_por_competencia"]] == [1234.56, 2.68, -2.68]
    assert result["resumo_consolidado"]["total_geral_a_receber"] == 1234.56


def test_salary_lookup_and_trace_use_same_decimal_sum(db_session, salary_reference):
    _, query = salary_reference(vencimento_basico="2.675", retribuicoes=[{"titulacao": "Mestrado", "valor": "0.01"}])
    value, trace = resolve_salary(db_session, query, "Mestrado")
    assert value == Decimal("2.685")
    assert Decimal(str(trace["valor_utilizado"])) == value
    assert Decimal(trace["valor_decimal"]) == Decimal("2.685")
    assert MotorCalculosRH._obter_salario_tabela("D", 1, "Mestrado", 2026, referencia=query) == Decimal("2.685")
