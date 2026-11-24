"""Regressões financeiras com fichas sintéticas da revisão de outubro."""
from datetime import date
from time import perf_counter
from unittest.mock import patch

import pytest

from app.services.dados_pdf import extract_calculation_data
from app.services.motor_calculos_rh import MotorCalculosRH
from app.utils.ficha_financeira import VALOR_RE, extrair_dados_ficha_financeira

FICHA_PROGRESSAO = """Ficha Financeira referente a: 2026 - 1º Semestre
T.serv.: 12
Rubrica| Nome Rubrica |R/D|Seq.| JAN | FEV
00001 |VENCIMENTO BASICO|R|0|3.000,00|3.000,00
00053 |ADIC. DE INSALUBRIDADE|R|0|600,00|600,00
82922 |IQ - 30% - LEI 11.091/05 AT|R|0|900,00|900,00
"""


def ficha_ferias(linhas, ano=2026, meses="JAN|FEV|MAR|ABR|MAI|JUN"):
    return f"Ficha Financeira referente a: {ano}\nRubrica|Nome Rubrica|R/D|Seq.|{meses}\n{linhas}\n"


def test_extracao_progressao_exige_confirmar_adicional_sugerido(auth_client_user):
    dados = extract_calculation_data(FICHA_PROGRESSAO, "progressao")
    assert dados["anuenio"] == 12
    assert dados["insalubridade"] is None
    assert dados["percentual_adicional_sugerido"] == 20
    assert dados["incentivo"] == 30
    assert "percentual_anuenio" not in dados and "percentual_insalubridade" not in dados
    with patch("app.routers.calculos_router.extract_pdf_data", return_value=dados):
        extraido = auth_client_user.post("/api/extrair-pdf", data={"tipo_calculo": "progressao"}, files={
            "arquivos": ("sintetico.pdf", b"%PDF-1.4\n", "application/pdf"),
        })
    assert extraido.status_code == 200
    payload = extraido.json()["resultados"][0]["dados_extraidos"]
    payload.update(salario_antigo=3000, salario_novo=4000, meses_diferenca=1,
                   mes_proporcao=1, ano_proporcao=2026, quantidade_reflexos_ferias=0,
                   quantidade_reflexos_13=0, incentivo=0)
    calculado = auth_client_user.post("/api/calcular", json={"tipo_calculo": "progressao", "dados_extraidos": payload})
    assert calculado.status_code == 400
    payload["insalubridade"] = 20  # Confirmação manual explícita no contrato legado.
    calculado = auth_client_user.post("/api/calcular", json={"tipo_calculo": "progressao", "dados_extraidos": payload})
    assert calculado.status_code == 200
    resultado = calculado.json()["resultado_calculo"]
    assert resultado["diferenca_anuenio"] == 120
    assert resultado["diferenca_insalubridade"] == 200
    assert resultado["total_geral_devido"] == 1320
    payload.update(anuenio=0, insalubridade=0)
    revisado = auth_client_user.post("/api/calcular", json={"tipo_calculo": "progressao", "dados_extraidos": payload})
    assert revisado.json()["resultado_calculo"]["total_geral_devido"] == 1000


@pytest.mark.parametrize("valor", ["0", "5,5"])
def test_progressao_preserva_percentuais_explicitos_inclusive_zero(valor):
    dados = extract_calculation_data(FICHA_PROGRESSAO + f"\nAnuênio (%): {valor}\nInsalubridade (%): {valor}\nIncentivo (%): {valor}", "progressao")
    esperado = float(valor.replace(",", "."))
    assert dados["anuenio"] == dados["insalubridade"] == dados["incentivo"] == esperado


def test_ferias_conta_competencias_na_mesma_linha_e_deduplica_sequencias():
    texto = ficha_ferias("""00750|FERIAS - ADICIONAL 1/3 CDT|R|0|1.000,00|||2.000,00||
00750|FERIAS - ADICIONAL 1/3 CDT|R|1|1.000,00|||2.000,00||
00750|FERIAS - ADICIONAL 1/3 CDT|R|6||200,00||||
00750|FERIAS - ADICIONAL 1/3 CDT|D|0|||100,00|||""")
    dados = extract_calculation_data(texto + texto, "rescisao")
    assert dados["ocorrencias_adicional_ferias"] == 2
    assert "alertas_extracao" not in dados


@pytest.mark.parametrize("valores", ["0,00|0,00||||", "|-100,00||||", "|||||"])
def test_ferias_sem_pagamento_positivo_nao_desconta_avos(valores):
    dados = extract_calculation_data(ficha_ferias(f"00750|FERIAS - ADICIONAL 1/3 CDT|R|0|{valores}"), "rescisao")
    assert dados["ocorrencias_adicional_ferias"] == 0


def test_ferias_preserva_alinhamento_das_colunas_vazias():
    texto = ficha_ferias("00750|FERIAS - ADICIONAL 1/3 CDT|R|0|||1.000,00", meses="JAN||MAR")
    registro = extrair_dados_ficha_financeira(texto)["rubricas"]["00750"][0]
    assert registro["meses"] == ["JAN", "", "MAR"]
    assert registro["celulas"] == [None, None, 1000]
    assert registro["valores"] == [1000]
    assert extract_calculation_data(texto, "rescisao")["ocorrencias_adicional_ferias"] == 1


def test_ferias_mesmo_mes_em_anos_distintos_sao_dois_pagamentos():
    linha = "00750|FERIAS - ADICIONAL 1/3 CDT|R|0|1.000,00|||||"
    dados = extract_calculation_data(ficha_ferias(linha, 2025) + ficha_ferias(linha, 2026), "rescisao")
    assert dados["ocorrencias_adicional_ferias"] == 2


@pytest.mark.parametrize("texto", [
    "Rubrica|Nome Rubrica|R/D|Seq.|JAN|FEV\n00750|FERIAS - ADICIONAL 1/3 CDT|R|0|1.000,00|",
    "Ficha Financeira referente a: 2026\n00750|FERIAS - ADICIONAL 1/3 CDT|R|0|1.000,00|2.000,00",
    ficha_ferias("00750|FERIAS - ADICIONAL 1/3 CDT|R|0||1.000,00|", meses="JAN||MAR"),
    ficha_ferias("00750|FERIAS - ADICIONAL 1/3 CDT|R|0|ilegível|||||"),
    ficha_ferias("00750|FERIAS - ADICIONAL 1/3 CDT|R|0|1.000,00|||||", 2025)
    + "Ficha Financeira referente a: 2026\n00750|FERIAS - ADICIONAL 1/3 CDT|R|0|1.000,00|||||",
])
def test_ferias_sem_competencia_ou_valor_legivel_exige_conferencia(texto):
    dados = extract_calculation_data(texto, "rescisao")
    assert dados["ocorrencias_adicional_ferias"] is None
    assert "750" in dados["alertas_extracao"][0]


def test_ferias_total_da_linha_nao_e_uma_nova_ocorrencia():
    texto = ficha_ferias("00750|FERIAS - ADICIONAL 1/3 CDT|R|0|1.000,00|1.000,00|2.000,00", meses="JAN|FEV|TOTAL")
    assert extract_calculation_data(texto, "rescisao")["ocorrencias_adicional_ferias"] == 2


@pytest.mark.parametrize("pagamentos,avos,principal,terco,total", [
    (0, 20, 10000, 3333.33, 13333.33),
    (1, 8, 4000, 1333.33, 5333.33),
    (2, -4, 0, -666.67, -666.67),
])
def test_rescisao_exemplo_com_devolucao_apenas_do_adicional(pagamentos, avos, principal, terco, total):
    resultado = MotorCalculosRH.calcular_rescisao_substituto(
        salario_mensal=6000, data_exercicio=date(2025, 1, 16), data_rescisao=date(2026, 8, 31),
        ocorrencias_adicional_ferias=pagamentos, mes_rescisao=8, ano_rescisao=2026,
    )
    assert resultado["avos_ferias_devidos"] == avos
    assert resultado["detalhamento_rubricas"]["772_ferias"]["devido"] == principal
    assert resultado["detalhamento_rubricas"]["82696_terco_ferias"]["devido"] == terco
    assert resultado["total_liquido_a_receber"] == total


def test_busca_monetaria_nao_trunca_numeros_e_preserva_centavos_e_sinal():
    assert VALOR_RE.findall("R$ 1.234,56 | -500,00 | 1234.56 | +0,25") == ["1.234,56", "-500,00", "1234.56", "+0,25"]
    assert VALOR_RE.findall("123,456 1.234.56 1.23,45 12345678901234567890,12") == []


def test_numero_longo_nao_produz_busca_quadratica_ou_valor_parcial():
    token = "7" * 100_000 + ",00"
    inicio = perf_counter()
    assert VALOR_RE.findall(token) == []
    dados = extract_calculation_data(ficha_ferias(f"00750|FERIAS - ADICIONAL 1/3 CDT|R|0|{token}|||||"), "rescisao")
    assert perf_counter() - inicio < 1.0
    assert dados["ocorrencias_adicional_ferias"] is None
