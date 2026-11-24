"""Competências financeiras: totais, páginas repetidas e revisão de ambiguidades."""
import pytest

from app.models.tabelas_salariais import TabelaVencimentoBasico
from app.services.dados_pdf import extract_calculation_data
from app.services.motor_calculos_rh import MotorCalculosRH
from app.utils.ficha_financeira import (
    extrair_dados_ficha_financeira,
    valores_principais_da_rubrica,
)


def ficha(linhas: str, meses: str = "JAN|FEV|TOTAL", ano: int = 2026) -> str:
    return f"Ficha Financeira referente a: {ano}\nRubrica |Nome Rubrica|R/D|Seq.|{meses}\n{linhas}\n"


def test_abono_exclui_total_e_deduplica_competencias_entre_paginas_e_sequencias():
    texto = ficha("""98002|CONT. PLANO SEGURIDADE SOCIAL|D|0|330,12|320,25|650,37
98002|CONT. PLANO SEGURIDADE SOCIAL|D|1|330,12|320,25|650,37
98002|CONT. PLANO SEGURIDADE SOCIAL|D|6|999,00|999,00|1.998,00
98002|CONT. PLANO SEGURIDADE SOCIAL|R|0|999,00|999,00|1.998,00""")
    dados = extract_calculation_data(texto + texto, "abono")
    assert dados["valores_anuais"] == {"2026": [330.12, 320.25]}
    assert "alertas_extracao" not in dados
    # 330,12 + 320,25: o TOTAL impresso não pode dobrar o reembolso.
    assert MotorCalculosRH.calcular_abono_permanencia(dados["valores_anuais"])["total_geral"] == 650.37


def test_abono_ordena_anos_e_meses_preservando_zero_e_coluna_vazia():
    texto = ficha("98002|CONT. PLANO SEGURIDADE SOCIAL|D|0|100,00|0|100,00", "FEV|JAN|TOTAL")
    texto += ficha("98002|CONT. PLANO SEGURIDADE SOCIAL|D|0|200,00||300,00|500,00", "JAN||MAR|TOTAL", 2025)
    assert extract_calculation_data(texto, "abono")["valores_anuais"] == {
        "2025": [200.00, 300.00], "2026": [0.0, 100.00],
    }


@pytest.mark.parametrize("celula", ["ilegível", "1.234.56", "-100,00"])
def test_abono_valor_invalido_ou_estorno_requer_conferencia(celula):
    dados = extract_calculation_data(ficha(f"98002|CONT. PLANO SEGURIDADE SOCIAL|D|0|100,00|{celula}|100,00"), "abono")
    assert dados["valores_anuais"] == {"2026": [100.0, None]}
    assert "98002" in dados["alertas_extracao"][0]


@pytest.mark.parametrize("sequencia", [0, 1])
def test_abono_competencia_conflitante_nao_soma_nem_escolhe_ultimo_valor(sequencia):
    texto = ficha(f"""98002|CONT. PLANO SEGURIDADE SOCIAL|D|0|100,00|200,00|300,00
98002|CONT. PLANO SEGURIDADE SOCIAL|D|{sequencia}|150,00|200,00|350,00""")
    dados = extract_calculation_data(texto, "abono")
    assert dados["valores_anuais"] == {"2026": [None, 200.0]}
    assert dados["alertas_extracao"]


@pytest.mark.parametrize("texto,ano", [
    ("Ficha Financeira referente a: 2026\n98002|CONT. PLANO SEGURIDADE SOCIAL|D|0|100,00|200,00", "2026"),
    ("Rubrica|Nome|R/D|Seq.|JAN\n98002|CONT. PLANO SEGURIDADE SOCIAL|D|0|100,00", "Ano a conferir"),
    ("Ficha Financeira referente a: 2026\n98002 CONT. PLANO SEGURIDADE SOCIAL 100,00 200,00", "2026"),
    (ficha("98002|CONT. PLANO SEGURIDADE SOCIAL|D|0||100,00|", "JAN||MAR"), "2026"),
])
def test_abono_sem_evidencia_da_competencia_nao_inventa_zero(texto, ano):
    dados = extract_calculation_data(texto, "abono")
    assert dados["valores_anuais"] == {ano: [None]}
    assert dados["alertas_extracao"]


def test_abono_nao_reaproveita_cabecalho_de_outra_pagina():
    texto = ficha("98002|CONT. PLANO SEGURIDADE SOCIAL|D|0|100,00", "JAN", 2025)
    texto += "Ficha Financeira referente a: 2026\n98002|CONT. PLANO SEGURIDADE SOCIAL|D|0|200,00"
    assert extract_calculation_data(texto, "abono")["valores_anuais"] == {"2025": [100.0], "2026": [None]}


def test_abono_preserva_layout_legado_com_ponto_virgula_e_zero():
    texto = "Ano: 2023 | Valores: R$ 100.50, R$ 200.75, R$ 150.00\nAno: 2024 | Valores: R$ 1.000,00, R$ 0"
    dados = extract_calculation_data(texto, "abono")
    assert dados["valores_anuais"] == {"2023": [100.50, 200.75, 150.0], "2024": [1000.0, 0.0]}
    assert "alertas_extracao" not in dados


@pytest.mark.parametrize("valor", ["ilegível", "123,456", "-100,00", ""])
def test_abono_legado_invalido_nao_vira_zero_ou_valor_parcial(valor):
    dados = extract_calculation_data(f"Ano: 2026 | Valores: R$ {valor}", "abono")
    assert dados["valores_anuais"] == {"2026": [None]}
    assert dados["alertas_extracao"]


def test_abono_layouts_misturados_no_mesmo_ano_exigem_conferencia():
    texto = ficha("98002|CONT. PLANO SEGURIDADE SOCIAL|D|0|100,00", "JAN")
    dados = extract_calculation_data(texto + "Ano: 2026 | Valores: R$ 100,00", "abono")
    assert dados["valores_anuais"] == {"2026": [100.0, None]}


def test_rescisao_usa_742_da_competencia_da_rescisao_sem_total_ou_auxiliares():
    texto = "Data de Rescisão: 28/02/2026\n" + ficha("""00742|SALARIO|R|0|6.100,00|6.200,00|12.300,00
00742|SALARIO|R|1|6.100,00|6.200,00|12.300,00
00742|SALARIO|R|6|200,00|300,00|500,00
00742|SALARIO|D|0|100,00|100,00|200,00""")
    texto += ficha("00742|SALARIO|R|0|5.000,00|5.100,00|10.100,00", ano=2025)
    dados = extract_calculation_data(texto + texto, "rescisao")
    assert dados["valores_recebidos"]["742_salario"] == 6200.0
    assert "alertas_extracao" not in dados


@pytest.mark.parametrize("data", ["", "Data de Rescisão: 31/03/2026\n", "Data de Rescisão: 28/02/2025\n"])
def test_rescisao_sem_competencia_correspondente_nao_usa_ultimo_valor(data):
    dados = extract_calculation_data(data + ficha("00742|SALARIO|R|0|6.100,00|6.200,00|12.300,00"), "rescisao")
    assert dados["valores_recebidos"]["742_salario"] is None
    assert "742" in dados["alertas_extracao"][0]


@pytest.mark.parametrize("linhas", [
    "00742|SALARIO|R|0|6.100,00|ilegível|6.100,00",
    "00742|SALARIO|R|0|6.100,00||6.100,00",
    "00742|SALARIO|R|0|6.100,00|-100,00|6.000,00",
    "00742|SALARIO|R|0|6.100,00|6.200,00|12.300,00\n00742|SALARIO|R|1|6.100,00|6.300,00|12.400,00",
])
def test_rescisao_salario_ausente_ilegivel_ou_conflitante_requer_revisao(linhas):
    dados = extract_calculation_data("Data de Rescisão: 28/02/2026\n" + ficha(linhas), "rescisao")
    assert dados["valores_recebidos"]["742_salario"] is None
    assert dados["alertas_extracao"]


def test_rescisao_preserva_recebimento_zero_explicitamente_informado():
    texto = "Data de Rescisão: 28/02/2026\nRecebido 742_salario: R$ 0,00\n"
    texto += ficha("00742|SALARIO|R|0|6.100,00|6.200,00|12.300,00")
    dados = extract_calculation_data(texto, "rescisao")
    assert dados["valores_recebidos"]["742_salario"] == 0.0
    assert "alertas_extracao" not in dados


def test_vencimento_e_insalubridade_usam_mesma_competencia_e_ignoram_total():
    texto = ficha("""00001|VENCIMENTO BASICO|R|0|3.000,00|4.000,00|7.000,00
00053|ADIC. DE INSALUBRIDADE|R|0|300,00|800,00|1.100,00""")
    texto += ficha("00001|VENCIMENTO BASICO|R|0|2.000,00|2.000,00|4.000,00", ano=2025)
    dados = extrair_dados_ficha_financeira(texto)
    assert dados["vencimento_basico"] == 4000.0
    assert dados["valor_insalubridade"] == 800.0
    assert dados["percentual_adicional_sugerido"] == 20.0
    assert "percentual_insalubridade" not in dados
    assert valores_principais_da_rubrica(dados, "00001") == [2000.0, 2000.0, 3000.0, 4000.0]


def test_insalubridade_nao_compara_parcelas_de_competencias_distintas():
    texto = ficha("""00001|VENCIMENTO BASICO|R|0|3.000,00|4.000,00|7.000,00
00053|ADIC. DE INSALUBRIDADE|R|0|600,00||600,00""")
    dados = extrair_dados_ficha_financeira(texto)
    assert dados["vencimento_basico"] == 4000.0
    assert "percentual_insalubridade" not in dados
    assert "valor_insalubridade" not in dados
    progressao = extract_calculation_data(texto, "progressao")
    assert progressao["insalubridade"] is None
    assert progressao["alertas_extracao"]
    revisado = extract_calculation_data(texto + "Insalubridade (%): 0", "progressao")
    assert revisado["insalubridade"] == 0.0
    assert "alertas_extracao" not in revisado


def test_abono_ambiguo_bloqueia_calculo_ate_revisao_explicita(auth_client_user):
    texto = ficha("""98002|CONT. PLANO SEGURIDADE SOCIAL|D|0|100,00|200,00|300,00
98002|CONT. PLANO SEGURIDADE SOCIAL|D|1|150,00|200,00|350,00""")
    dados = extract_calculation_data(texto, "abono")
    payload = {"tipo_calculo": "abono", "dados_extraidos": dados}
    recusado = auth_client_user.post("/api/calcular", json=payload)
    assert recusado.status_code == 400
    assert any(erro["loc"] == ["dados_extraidos", "valores_anuais", "2026", 0] for erro in recusado.json()["detail"])
    dados["valores_anuais"]["2026"][0] = 100.0
    calculado = auth_client_user.post("/api/calcular", json=payload)
    assert calculado.status_code == 200
    assert calculado.json()["resultado_calculo"]["total_geral"] == 300.0


def test_rescisao_sem_salario_da_competencia_exige_valor_revisado(auth_client_user, db_session):
    db_session.add(TabelaVencimentoBasico(classe="Auxiliar", nivel=1, ano=2026, valor=6200.0))
    db_session.flush()
    texto = "Classe: Auxiliar\nData de Rescisão: 28/02/2026\n" + ficha("00742|SALARIO|R|0|6.200,00", "JAN")
    dados = extract_calculation_data(texto, "rescisao")
    dados["dias_trabalhados"] = 14
    payload = {"tipo_calculo": "rescisao", "dados_extraidos": dados}
    recusado = auth_client_user.post("/api/calcular", json=payload)
    assert recusado.status_code == 400
    assert any(erro["loc"] == ["dados_extraidos", "valores_recebidos", "742_salario"] for erro in recusado.json()["detail"])
    dados["valores_recebidos"]["742_salario"] = 5000.0
    pendente = auth_client_user.post("/api/calcular", json=payload)
    assert pendente.status_code == 400
    assert pendente.json()["detail"][0]["type"] == "referencia_salarial_pendente"
    dados["salario_mensal"] = 6200.0  # Salário explicitamente conferido; o legado anual não seleciona uma referência.
    calculado = auth_client_user.post("/api/calcular", json=payload)
    assert calculado.status_code == 200
    # 6.200 × 14/28 = 3.100 devidos; recebeu 5.000 => devolve 1.900.
    assert calculado.json()["resultado_calculo"]["total_liquido_a_receber"] == -1900.0


def test_insalubridade_sem_base_coerente_exige_percentual_revisado(auth_client_user):
    texto = ficha("""00001|VENCIMENTO BASICO|R|0|3.000,00|4.000,00|7.000,00
00053|ADIC. DE INSALUBRIDADE|R|0|600,00||600,00""")
    dados = extract_calculation_data(texto, "progressao")
    dados.update(salario_antigo=1000.0, salario_novo=2000.0, meses_diferenca=1,
                 quantidade_reflexos_ferias=0, quantidade_reflexos_13=0)
    payload = {"tipo_calculo": "progressao", "dados_extraidos": dados}
    recusado = auth_client_user.post("/api/calcular", json=payload)
    assert recusado.status_code == 400
    assert any(erro["loc"] == ["dados_extraidos", "insalubridade"] for erro in recusado.json()["detail"])
    dados["insalubridade"] = 20.0
    calculado = auth_client_user.post("/api/calcular", json=payload)
    assert calculado.status_code == 200
    assert calculado.json()["resultado_calculo"]["total_geral_devido"] == 1200.0
