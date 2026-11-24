import csv

import pytest

from app.utils.csv_leitores import (
    ler_csv_abono_permanencia,
    ler_csv_exercicio_anterior,
    ler_csv_insalubridade,
    ler_csv_progressao,
    ler_csv_rescisao,
    ler_csv_substituicao,
)


@pytest.mark.parametrize("valor,esperado", [("1.00499999999999999", 1.00), ("1.005", 1.01)])
def test_csv_preserva_decimal_antes_da_finalizacao(tmp_path, valor, esperado):
    csv_file = tmp_path / "precisao.csv"
    with csv_file.open("w", newline="", encoding="utf-8-sig") as arquivo:
        writer = csv.writer(arquivo)
        writer.writerow(["Ano", "Valor"])
        writer.writerow(["2026", valor])
    resultado = ler_csv_abono_permanencia(str(csv_file))
    assert resultado["total_geral"] == esperado

def test_ler_csv_substituicao(tmp_path):
    csv_file = tmp_path / "substituicao.csv"
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Nome do Servidor:", "João Silva"])
        writer.writerow(["Matrícula:", "123456"])
        writer.writerow(["Função que possui", "CD-04"])
        writer.writerow(["Função que substitui", "CD-03"])
        writer.writerow([])
        writer.writerow(["Função que substitui", "FG_01", "CD_03", "CD_04"])
        writer.writerow(["Valor", "1000.0", "7374.97", "4989.43"])

    resultado = ler_csv_substituicao(str(csv_file))
    
    assert resultado["nome"] == "João Silva"
    assert resultado["matricula"] == "123456"
    assert resultado["funcao_propria"] == "CD-04"
    assert resultado["funcao_substituta"] == "CD-03"
    assert "tabela_salarios_referencia" in resultado
    assert "calculo" not in resultado
    assert resultado["tabela_salarios_referencia"]["CD_03"] == "7374.97"
    assert resultado["alertas_extracao"]

def test_ler_csv_insalubridade(tmp_path):
    csv_file = tmp_path / "insalubridade.csv"
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["PLAN 2 - INSALUBRIDADE"])
        writer.writerow(["MÊS/ANO", "A", "B", "VALOR"])
        writer.writerow(["01/2023", "x", "y", "100.50"])
        writer.writerow(["02/2023", "x", "y", "100.50"])
        writer.writerow(["TOTAL", "x", "y", "201.00"])

    resultado = ler_csv_insalubridade(str(csv_file))
    
    assert len(resultado["detalhamento_mensal"]) == 2
    assert resultado["total_acumulado"] == 201.0

def test_ler_csv_abono_permanencia(tmp_path):
    csv_file = tmp_path / "abono.csv"
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Ano", "Valor"])
        writer.writerow(["2022", "100.00"])
        writer.writerow(["2022", "150.00"])
        writer.writerow(["2023", "200.00"])

    resultado = ler_csv_abono_permanencia(str(csv_file))
    
    assert resultado["total_geral"] == 450.0
    assert resultado["consolidado_anual"] == {2022: 250.0, 2023: 200.0}

def test_ler_csv_rescisao(tmp_path):
    csv_file = tmp_path / "rescisao.csv"
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Salário Mensal", "3000.00"])
        writer.writerow(["Meses Férias", "1.5"])
        writer.writerow(["Meses 13", "6"])
        writer.writerow(["Dias Trabalhados", "15"])
        writer.writerow(["Valor já recebido", "742_salario", "500.00"])

    resultado = ler_csv_rescisao(str(csv_file))
    
    rubricas = resultado["detalhamento_rubricas"]
    assert rubricas["772_ferias"]["devido"] == 375.0
    assert rubricas["82407_decimo_terceiro"]["devido"] == 1500.0
    # O leitor usa dezembro de 2024 por padrão, com 31 dias.
    # 3.000 × 15/31 = 1.451,612903…; exibição final em centavos.
    assert rubricas["742_salario"]["devido"] == 1451.61
    assert rubricas["742_salario"]["recebido"] == 500.0
    assert resultado["total_liquido_a_receber"] == 2951.61


def test_ler_csv_progressao(tmp_path):
    csv_file = tmp_path / "progressao.csv"
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Salário Antigo", "5000.00"])
        writer.writerow(["Salário Novo", "6000.00"])
        writer.writerow(["Percentual Anuênio", "5.0"])
        writer.writerow(["Percentual Insalubridade", "10.0"])
        writer.writerow(["Meses de Diferença", "3"])

    resultado = ler_csv_progressao(str(csv_file))
    
    assert "diferenca_base" in resultado
    assert resultado["diferenca_base"] == 1000.0 # 6000 - 5000
    assert resultado["total_geral_devido"] == 3450.0
    assert resultado["multiplicador_tempo"] == 3

def test_ler_csv_exercicio_anterior(tmp_path):
    csv_file = tmp_path / "exercicio.csv"
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Periodo", "Devido", "Recebido", "Ferias", "13o"])
        writer.writerow(["01/2023", "2000.00", "1500.00", "0", "0"])
        writer.writerow(["02/2023", "2000.00", "2000.00", "0", "0"])
        writer.writerow(["03/2023", "2000.00", "1000.00", "500.00", "100.00"])

    resultado = ler_csv_exercicio_anterior(str(csv_file))
    
    resumo = resultado["resumo_consolidado"]
    assert resumo["total_devido_base"] == 6000.0
    assert resumo["total_recebido_base"] == 4500.0
    assert resumo["total_diferenca_salarial"] == 1500.0
    assert resumo["total_geral_a_receber"] == 2100.0
