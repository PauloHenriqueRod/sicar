from datetime import date

import pytest

from app.services.motor_calculos_rh import MotorCalculosRH
from app.utils.ficha_financeira import (
    extrair_dados_ficha_financeira,
    valores_da_rubrica,
    valores_principais_da_rubrica,
)

FICHA = """Ficha Financeira referente a: 2026 - 1º Semestre
Nome: 9997999 - SERVIDOR TESTE Banco/Agência/C. Corrente: 001/1
Cargo/Lotação: 701200 D 303 - 99999999 Função/Exerc.: FG 2 - 99999999 Localização: X Dep.IR/SF: 03 T.serv.: 12
Rubrica| Nome Rubrica |R/D|Seq.| JAN | FEV | MAR | ABR | MAI | JUN
00001 |VENCIMENTO BASICO | R | 0 | 3.000,00| 3.000,00| 3.000,00| 3.000,00| 3.000,00| 3.000,00
00053 |ADIC. DE INSALUBRIDADE | | 0 | 600,00| 600,00| 600,00| 600,00| 600,00| 600,00
98002 |CONT. PLANO SEGURIDADE SOCIAL | D | 0 | 330,00| 330,00| 330,00| 330,00| 330,00| 330,00
00742 |SALARIO CONTRATO | R | 1 | 6.000,00| 6.000,00| 6.000,00| 6.000,00| 6.000,00| 6.000,00
00742 |SALARIO CONTRATO | | 6 | | | | | 200,00|
82922 |IQ - 30% - LEI 11.091/05 AT | | 0 | 900,00| 900,00| 900,00| 900,00| 900,00| 900,00
"""


def test_extrai_cabecalho_rubricas_e_percentuais():
    dados = extrair_dados_ficha_financeira(FICHA)
    assert dados["matricula"] == "9997999"
    assert dados["nome"] == "SERVIDOR TESTE"
    assert dados["classe"] == "D"
    assert dados["nivel"] == 303
    assert dados["funcao_exercida"] == "FG 2 - 99999999"
    assert dados["quantidade_anuenios"] == 12
    assert dados["percentual_adicional_sugerido"] == 20
    assert "percentual_insalubridade" not in dados
    assert valores_da_rubrica(dados, "98002") == [330.0] * 6
    assert valores_principais_da_rubrica(dados, "00742") == [6000.0] * 6
    assert dados["percentual_incentivo"] == 30


@pytest.mark.parametrize(
    ("pagamentos_ferias", "avos_esperados"),
    [(0, 20), (1, 8), (2, -4)],
)
def test_avos_ferias_rescisao_conforme_exemplo(pagamentos_ferias, avos_esperados):
    assert MotorCalculosRH.calcular_avos_ferias(
        date(2025, 1, 16), date(2026, 8, 31), pagamentos_ferias
    ) == avos_esperados


def test_rescisao_usa_datas_e_desconta_ferias_ja_pagas():
    resultado = MotorCalculosRH.calcular_rescisao_substituto(
        salario_mensal=6000,
        data_exercicio=date(2025, 1, 16),
        data_rescisao=date(2026, 8, 31),
        ocorrencias_adicional_ferias=1,
    )
    assert resultado["avos_ferias_devidos"] == 8
    assert resultado["detalhamento_rubricas"]["772_ferias"]["devido"] == 4000
    assert resultado["detalhamento_rubricas"]["82696_terco_ferias"]["devido"] == 1333.33


def test_interrupcao_reduz_dias_efetivos_da_substituicao():
    resultado = MotorCalculosRH.calcular_substituicao(
        salario_substituta=7000,
        salario_propria=4000,
        dias_substituidos=20,
        dias_interrupcao=5,
        mes=4,
        ano=2026,
    )
    assert resultado["dias_efetivos"] == 15
    assert resultado["valor_proporcional_devido"] == 1500
