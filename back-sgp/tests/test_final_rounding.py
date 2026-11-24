"""Política v3: esperados independentes, frações exatas e dados sintéticos."""
from decimal import Decimal
from fractions import Fraction

import pytest

from app.schemas.calculos import ProgressaoDados
from app.services.calculation_service import execute_calculation, resolve_salary
from app.services.motor_calculos_rh import MotorCalculosRH
from app.utils.conversor import ConversorSaneador


def centavos_exatos(valor: Fraction) -> float:
    """Oráculo inteiro: empate decidido pelo resto, sem Decimal do motor."""
    centavos, resto = divmod(abs(valor.numerator) * 100, valor.denominator)
    if resto * 2 >= valor.denominator:
        centavos += 1
    return (-1 if valor < 0 else 1) * centavos / 100


@pytest.mark.parametrize("meses,principal,total", [(1, 192.02, 448.04), (10, 1920.17, 2176.19)])
def test_progressao_acumula_parcelas_e_reflexos_sem_quantizar(meses, principal, total):
    # 148,85 × (1 + 25/100 + 4/100) = 192,0165.
    resultado = MotorCalculosRH.calcular_progressao_docente(
        salario_antigo=3721.27, salario_novo=3870.12,
        percentual_incentivo=25, percentual_anuenio=4, meses_diferenca=meses,
    )
    assert resultado["diferenca_mensal_total"] == 192.02
    assert resultado["diferenca_incentivo_qualificacao"] == 37.21
    assert resultado["diferenca_anuenio"] == 5.95
    assert resultado["total_geral_devido"] == principal
    assert resultado["reflexo_ferias"] == 64.01
    assert resultado["total_com_reflexos"] == total


@pytest.mark.parametrize("antigo,novo,anuenio,adicional,iq,meses,dias,esperado", [
    ("8601.31", "8945.36", 0, 10, 52, 0, 4, 71.92),
    ("9675.31", "10062.32", 0, 10, 30, 1, 0, 541.81),
    ("9675.31", "10062.32", 0, 0, 75, 0, 17, 371.40),
    ("3686.33", "3833.79", 0, 0, 30, 0, 14, 86.57),
    ("3544.55", "3686.33", 0, 0, 30, 0, 14, 83.24),
    ("3987.14", "4146.62", 0, 0, 30, 1, 0, 207.32),
    ("3721.27", "3870.12", 5, 0, 10, 1, 0, 171.18),
    ("3721.27", "3870.12", 4, 0, 25, 1, 0, 192.02),
    ("3220.33", "3349.14", 17, 0, 0, 1, 0, 150.71),
])
def test_nove_referencias_numericas_recalculadas_pela_politica_final(antigo, novo, anuenio, adicional, iq, meses, dias, esperado):
    # Somente parâmetros remuneratórios, sem identificação de servidor ou
    # documento. O oráculo usa frações e calendário real, não o resultado
    # salvo pelo Excel (que usava divisor 30) nem quantizações da política v2.
    mensal = (Fraction(novo) - Fraction(antigo)) * (1 + Fraction(anuenio + adicional + iq, 100))
    principal = mensal * (meses + Fraction(dias, 31))
    assert centavos_exatos(principal) == esperado
    resultado = MotorCalculosRH.calcular_progressao_docente(
        salario_antigo=Decimal(antigo), salario_novo=Decimal(novo), percentual_anuenio=anuenio,
        percentual_insalubridade=adicional, percentual_incentivo=iq, meses_diferenca=meses,
        aplica_proporcao_dias=dias > 0, dias_proporcionais=dias, mes_proporcao=1, ano_proporcao=2026,
        quantidade_reflexos_ferias=0, quantidade_reflexos_13=0,
    )
    assert resultado["total_geral_devido"] == esperado
    assert resultado["total_com_reflexos"] == esperado


@pytest.mark.parametrize("sinal", [1, -1])
def test_empate_final_positivo_e_negativo(sinal):
    resultado = MotorCalculosRH.calcular_progressao_docente(
        salario_antigo=Decimal("2674.495") if sinal < 0 else 0,
        salario_novo=Decimal("2674.495") if sinal > 0 else 0,
        meses_diferenca=1, quantidade_reflexos_ferias=0, quantidade_reflexos_13=0,
    )
    assert resultado["total_com_reflexos"] == sinal * 2674.50


@pytest.mark.parametrize("dias_mes,mes,ano", [(28, 2, 2023), (29, 2, 2024), (30, 4, 2026), (31, 1, 2026)])
def test_progressao_proporcional_e_reflexos_contra_fracoes_exatas(dias_mes, mes, ano):
    mensal = Fraction(14885, 100) * (1 + Fraction(25, 100) + Fraction(4, 100))
    periodo = Fraction(7, 2) + Fraction(15, dias_mes)
    resultado = MotorCalculosRH.calcular_progressao_docente(
        salario_antigo=3721.27, salario_novo=3870.12, percentual_incentivo=25,
        percentual_anuenio=4, meses_diferenca=3.5, aplica_proporcao_dias=True,
        dias_proporcionais=15, mes_proporcao=mes, ano_proporcao=ano,
        quantidade_reflexos_ferias=2, quantidade_reflexos_13=1.5,
    )
    assert resultado["total_geral_devido"] == centavos_exatos(mensal * periodo)
    assert resultado["total_com_reflexos"] == centavos_exatos(mensal * (periodo + Fraction(2, 3) + Fraction(3, 2)))


def test_empate_apos_soma_de_dizimas_e_exato():
    # 0,015 × (2/3 do mês + 1/3 de férias) = 0,015.
    resultado = MotorCalculosRH.calcular_progressao_docente(
        salario_antigo=0, salario_novo=Decimal("0.015"), meses_diferenca=0,
        aplica_proporcao_dias=True, dias_proporcionais=20, mes_proporcao=4,
        quantidade_reflexos_ferias=1, quantidade_reflexos_13=0,
    )
    assert resultado["total_com_reflexos"] == 0.02


def test_substituicao_nao_arredonda_diferenca_antes_do_rateio():
    resultado = MotorCalculosRH.calcular_substituicao(Decimal("1.005"), 0, 15, mes=4, ano=2026)
    assert resultado["diferenca_mensal_cheia"] == 1.01
    assert resultado["valor_proporcional_devido"] == 0.50  # 1,005 / 2 = 0,5025


def test_insalubridade_soma_meses_antes_de_arredondar():
    resultado = MotorCalculosRH.calcular_retroativo_insalubridade({"2026-01": 0.015, "2026-02": 0.015})
    assert [linha["valor_calculado"] for linha in resultado["detalhamento_mensal"]] == [0.02, 0.02]
    assert resultado["total_acumulado"] == 0.03


def test_abono_nao_soma_anuais_ja_arredondados():
    resultado = MotorCalculosRH.calcular_abono_permanencia({2025: [Decimal("0.004")], 2026: [Decimal("0.004")]})
    assert resultado["consolidado_anual"] == {2025: 0, 2026: 0}
    assert resultado["total_geral"] == 0.01


@pytest.mark.parametrize("avos", [1, -4, 20, 24])
def test_rescisao_total_usa_rubricas_exatas_antes_dos_recebidos(avos):
    salario = Fraction(594907, 100)
    recebido = Fraction(480064 + 160021 + 30004, 100)
    esperado = salario * (Fraction(18, 31) + Fraction(max(0, avos), 12) + Fraction(avos, 36) + Fraction(6, 12)) - recebido
    resultado = MotorCalculosRH.calcular_rescisao_substituto(
        salario_mensal=5949.07, meses_ferias_indenizadas=avos, meses_completos_13o=6,
        dias_trabalhados_ultimo_mes=18, mes_rescisao=12,
        valores_ja_recebidos={"772_ferias": 4800.64, "82696_terco_ferias": 1600.21, "82407_decimo_terceiro": 300.04},
    )
    assert resultado["total_liquido_a_receber"] == centavos_exatos(esperado)
    assert resultado["detalhamento_rubricas"]["772_ferias"]["devido"] >= 0


def test_rescisao_soma_fracoes_inferiores_a_um_centavo():
    resultado = MotorCalculosRH.calcular_rescisao_substituto(
        salario_mensal=0.03, meses_ferias_indenizadas=1, meses_completos_13o=1,
    )
    assert resultado["total_liquido_a_receber"] == 0.01  # 0,0025 + 0,000833… + 0,0025


def test_exercicios_anteriores_preservam_texto_decimal_e_parcelas():
    resultado = MotorCalculosRH.calcular_exercicio_anterior([
        {"v_dev": "R$ 1,004", "v_rec": "1,00", "ab_ferias": "0,004", "periodo": "01/2026"},
        {"v_dev": "1,004", "v_rec": "1,00", "periodo": "02/2026"},
    ])
    assert resultado["resumo_consolidado"]["total_geral_a_receber"] == 0.01
    assert resultado["resumo_consolidado"]["total_diferenca_salarial"] == 0.01
    assert ConversorSaneador.para_decimal("1,00499999999999999") == Decimal("1.00499999999999999")


def test_composicao_vb_rt_nao_finaliza_salario_antes_do_calculo(db_session, salary_reference):
    _, query = salary_reference(vencimento_basico="1.001", retribuicoes=[{"titulacao": "Mestrado", "valor": "0.004"}])
    salario, origem = resolve_salary(db_session, query, "Mestrado")
    assert salario == Decimal("1.005")
    assert Decimal(origem["valor_decimal"]) == Decimal("1.005")
    assert MotorCalculosRH._obter_salario_tabela("Teste", 1, "Mestrado", 2026, referencia=query) == Decimal("1.005")
    resultado, trace = execute_calculation(ProgressaoDados(
        classe_atual="Teste", classe_antiga="Teste", titulacao="Mestrado", salario_antigo=0, referencia_nova=query,
        ano_proporcao=2026, mes_proporcao=4, dias_proporcionais=15,
        quantidade_reflexos_ferias=0, quantidade_reflexos_13=0,
    ), db_session)
    assert resultado["total_geral_devido"] == 0.50
    assert Decimal(trace["referencias_salariais"]["salario_novo"]["valor_decimal"]) == Decimal("1.005")
