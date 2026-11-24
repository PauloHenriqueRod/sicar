import csv
from decimal import Decimal
from typing import Any

from app.utils.conversor import ConversorSaneador


def ler_csv_substituicao(caminho_arquivo: str) -> dict[str, Any]:
    """Lê candidatos da PLAN 1; datas, opções e direitos exigem revisão."""
    dados: dict[str, Any] = {}
    with open(caminho_arquivo, mode="r", encoding="utf-8-sig") as f:
        reader = list(csv.reader(f))

        for linha in reader:
            if len(linha) > 1:
                if "Nome" in linha[0]:
                    dados["nome"] = linha[1]
                elif "Matrícula" in linha[0]:
                    dados["matricula"] = linha[1]
                elif "Função que possui" in linha[0]:
                    dados["funcao_propria"] = linha[1]
                elif "Função que substitui" in linha[0] and "FG_01" not in linha:
                    dados["funcao_substituta"] = linha[1]

        tabela_salarios = {}
        for idx, linha in enumerate(reader):
            if len(linha) > 0 and "Função que substitui" in linha[0] and "FG_01" in linha and idx + 1 < len(reader):
                valores_linha = reader[idx + 1]
                for col_idx, col_name in enumerate(linha):
                    if col_name.strip() and col_idx < len(valores_linha):
                        tabela_salarios[col_name.strip()] = ConversorSaneador.para_decimal(valores_linha[col_idx])
                break

        dados["tabela_salarios_referencia"] = {chave: str(valor) for chave, valor in tabela_salarios.items()}
        dados["alertas_extracao"] = ["Confira as funções, a vigência dos valores, a designação, o afastamento do titular, os impedimentos e a opção remuneratória. O CSV não define automaticamente dias ou direito."]

    return dados


def ler_csv_insalubridade(caminho_arquivo: str) -> dict[str, Any]:
    from app.services.motor_calculos_rh import MotorCalculosRH
    """Lê a PLAN 2 de valores retroativos de insalubridade."""
    valores_mensais = {}
    with open(caminho_arquivo, mode="r", encoding="utf-8-sig") as f:
        reader = list(csv.reader(f))
        cabecalho_encontrado = False
        for linha in reader:
            if len(linha) > 0 and "MÊS/ANO" in linha[0]:
                cabecalho_encontrado = True
                continue
            if cabecalho_encontrado:
                if len(linha) > 3 and "TOTAL" not in linha[0] and linha[0].strip():
                    mes = linha[0].strip()
                    valores_mensais[mes] = ConversorSaneador.para_decimal(linha[3])

    return MotorCalculosRH.calcular_retroativo_insalubridade(valores_mensais)


def ler_csv_abono_permanencia(caminho_arquivo: str) -> dict[str, Any]:
    from app.services.motor_calculos_rh import MotorCalculosRH
    valores_anuais: dict[int, list[Decimal]] = {}
    with open(caminho_arquivo, mode="r", encoding="utf-8-sig") as f:
        reader = list(csv.reader(f))
        for linha in reader:
            if len(linha) > 1 and str(linha[0]).isdigit():
                ano = int(linha[0])
                if ano not in valores_anuais:
                    valores_anuais[ano] = []
                valores_anuais[ano].append(ConversorSaneador.para_decimal(linha[1]))

    return MotorCalculosRH.calcular_abono_permanencia(valores_anuais)


def ler_csv_rescisao(caminho_arquivo: str) -> dict[str, Any]:
    from app.services.motor_calculos_rh import MotorCalculosRH
    salario_mensal = Decimal(0)
    meses_ferias = Decimal(0)
    meses_13 = 0
    dias_trab = 0
    valores_rec = {}
    
    with open(caminho_arquivo, mode="r", encoding="utf-8-sig") as f:
        reader = list(csv.reader(f))
        for linha in reader:
            if len(linha) > 1:
                col = linha[0].lower()
                val = linha[1]
                if "salário" in col or "salario" in col:
                    salario_mensal = ConversorSaneador.para_decimal(val)
                elif "meses férias" in col or "meses ferias" in col:
                    meses_ferias = ConversorSaneador.para_decimal(val)
                elif "meses 13" in col or "décimo terceiro" in col:
                    meses_13 = int(ConversorSaneador.para_decimal(val))
                elif "dias trabalhados" in col:
                    dias_trab = int(ConversorSaneador.para_decimal(val))
                elif "recebido" in col and len(linha) > 2:
                    rubrica = linha[1].strip()
                    valores_rec[rubrica] = ConversorSaneador.para_decimal(linha[2])

    return MotorCalculosRH.calcular_rescisao_substituto(
        salario_mensal=salario_mensal,
        meses_ferias_indenizadas=meses_ferias,
        meses_completos_13o=meses_13,
        dias_trabalhados_ultimo_mes=dias_trab,
        valores_ja_recebidos=valores_rec
    )


def ler_csv_progressao(caminho_arquivo: str) -> dict[str, Any]:
    from app.services.motor_calculos_rh import MotorCalculosRH
    salario_novo = Decimal(0)
    salario_antigo = Decimal(0)
    perc_anuenio = Decimal(0)
    perc_insalub = Decimal(0)
    meses_diff = Decimal(0)

    with open(caminho_arquivo, mode="r", encoding="utf-8-sig") as f:
        reader = list(csv.reader(f))
        for linha in reader:
            if len(linha) > 1:
                col = linha[0].lower()
                val = ConversorSaneador.para_decimal(linha[1])
                if "novo" in col:
                    salario_novo = val
                elif "antigo" in col:
                    salario_antigo = val
                elif "anuênio" in col or "anuenio" in col:
                    perc_anuenio = val
                elif "insalubridade" in col:
                    perc_insalub = val
                elif "meses" in col or "diferença" in col:
                    meses_diff = val

    return MotorCalculosRH.calcular_progressao_docente(
        salario_novo=salario_novo,
        salario_antigo=salario_antigo,
        percentual_anuenio=perc_anuenio,
        percentual_insalubridade=perc_insalub,
        meses_diferenca=meses_diff
    )


def ler_csv_exercicio_anterior(caminho_arquivo: str) -> dict[str, Any]:
    from app.services.motor_calculos_rh import MotorCalculosRH
    fluxo = []
    with open(caminho_arquivo, mode="r", encoding="utf-8-sig") as f:
        reader = list(csv.reader(f))
        for idx, linha in enumerate(reader):
            if idx > 0 and len(linha) >= 5: # Ignorar cabeçalho, assumir formato posicional
                fluxo.append({
                    "periodo": linha[0],
                    "v_dev": ConversorSaneador.para_decimal(linha[1]),
                    "v_rec": ConversorSaneador.para_decimal(linha[2]),
                    "ab_ferias": ConversorSaneador.para_decimal(linha[3]),
                    "13_sal": ConversorSaneador.para_decimal(linha[4]),
                })

    return MotorCalculosRH.calcular_exercicio_anterior(fluxo)
