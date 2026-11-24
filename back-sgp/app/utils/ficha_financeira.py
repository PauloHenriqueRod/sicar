import re
from typing import Any

from app.utils.conversor import ConversorSaneador

# Limites e fronteiras evitam recomeçar uma busca sem limite dentro de uma
# sequência de dígitos. Um token malformado não pode virar um valor parcial.
VALOR_RE = re.compile(
    r"(?<![\w.,+-])[+-]?(?:[0-9]{1,3}(?:\.[0-9]{3}){1,5},[0-9]{2}|[0-9]{1,18}[.,][0-9]{2})(?![\w.,])"
)
MESES = {nome: indice for indice, nome in enumerate(
    ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"), 1
)}


def _valor_celula(celula: str) -> float | None:
    texto = celula.replace("R$", "").replace(" ", "").strip()
    if texto == "0":
        return 0.0
    if VALOR_RE.fullmatch(texto):
        return ConversorSaneador.para_float(texto)
    return None


def extrair_dados_ficha_financeira(texto: str) -> dict[str, Any]:
    """Extrai cabeçalho e rubricas de fichas financeiras do SIAPE."""
    dados: dict[str, Any] = {"rubricas": {}}

    servidor = re.search(
        r"^Nome:\s*(\d+)\s*-\s*(.+?)\s+Banco/Ag[êe]ncia",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if servidor:
        dados["matricula"] = servidor.group(1)
        dados["nome"] = servidor.group(2).strip()

    cargo = re.search(
        r"Cargo/Lota[çc][ãa]o:\s*(.+?)\s+-\s*\d+\s+Fun[çc][ãa]o/Exerc\.?:\s*(.*?)\s+Localiza[çc][ãa]o:",
        texto,
        re.IGNORECASE,
    )
    if cargo:
        identificacao = cargo.group(1).strip()
        dados["cargo_lotacao"] = identificacao
        partes = identificacao.split()
        if len(partes) >= 3:
            dados["classe"] = partes[-2]
            nivel = re.sub(r"\D", "", partes[-1])
            if nivel:
                dados["nivel"] = int(nivel)
        funcao = cargo.group(2).strip()
        if funcao:
            dados["funcao_exercida"] = funcao

    tempo = re.search(r"T\.\s*serv\.?:\s*([\d.,]+)", texto, re.IGNORECASE)
    if tempo:
        dados["quantidade_anuenios"] = ConversorSaneador.para_float(tempo.group(1))
        dados["percentual_anuenio"] = dados["quantidade_anuenios"]

    ano_atual: str | None = None
    meses: list[str] = []
    for numero_linha, linha in enumerate(texto.splitlines(), 1):
        ano = re.search(r"referente a:\s*(\d{4})", linha, re.IGNORECASE)
        if ano:
            ano_atual = ano.group(1)
            meses = []
            continue
        if re.match(r"\s*RUBRICA\s*\|", linha, re.IGNORECASE):
            # Células vazias também ocupam uma coluna; removê-las desloca os
            # pagamentos para meses diferentes daqueles impressos na ficha.
            meses = [parte.strip() for parte in linha.split("|")[4:]]
            continue
        rubrica = re.match(r"\s*(\d{5})\s*\|\s*([^|]+)\|([^|]*)\|\s*(\d+)\s*\|(.*)", linha)
        if not rubrica:
            continue
        codigo, nome, natureza, sequencia, resto = rubrica.groups()
        # Sequência zero/um contém o valor normal da competência. Sequências
        # complementares são preservadas, mas não substituem o valor mensal.
        celulas_texto = resto.split("|")
        celulas = [_valor_celula(celula) for celula in celulas_texto]
        valores = [valor for valor in celulas if valor is not None]
        registro = {
            "celulas_texto": celulas_texto,
            "localizador": f"Linha {numero_linha} do texto extraído",
            "ano": int(ano_atual) if ano_atual else None, "nome": nome.strip(), "natureza": natureza.strip().upper(),
            "sequencia": int(sequencia), "valores": valores, "celulas": celulas,
            "celulas_invalidas": [
                indice for indice, (original, valor) in enumerate(zip(celulas_texto, celulas))
                if valor is None and original.strip() not in ("", "-", "—")
            ],
        }
        if meses:
            registro["meses"] = meses
        dados["rubricas"].setdefault(codigo, []).append(registro)

    vencimentos, vencimentos_pendentes = valores_por_competencia_da_rubrica(dados, "00001")
    adicionais, adicionais_pendentes = valores_por_competencia_da_rubrica(dados, "00053")
    if vencimentos and not vencimentos_pendentes:
        competencia = max(vencimentos)
        vencimento = vencimentos[competencia]
        if vencimento is not None and vencimento >= 0:
            dados["vencimento_basico"] = vencimento
            # Os dois valores devem pertencer à mesma competência. Uma coluna
            # total ou um adicional de outro mês não fornece o percentual atual.
            adicional = adicionais.get(competencia)
            if not adicionais_pendentes and adicional is not None and adicional >= 0 and vencimento:
                dados["valor_insalubridade"] = adicional
                # A razão observada não comprova espécie, base legal ou concessão.
                dados["percentual_adicional_sugerido"] = round(adicional / vencimento * 100, 2)

    for registros in dados["rubricas"].values():
        for registro in registros:
            incentivo = re.search(r"\bIQ\s*-\s*([\d.,]+)%", registro["nome"], re.IGNORECASE)
            if incentivo:
                dados["percentual_incentivo"] = ConversorSaneador.para_float(incentivo.group(1))

    return dados


def contar_pagamentos_ferias(dados: dict[str, Any]) -> tuple[int | None, list[str]]:
    """Conta uma parcela regular positiva da 750 por competência identificada.

    As sequências auxiliares e os descontos não são novas concessões. Sem
    cabeçalho/coluna legível, a quantidade precisa de conferência humana.
    """
    competencias: set[tuple[int, int]] = set()
    ambiguo = False
    for registro in dados.get("rubricas", {}).get("00750", []):
        if registro["sequencia"] not in (0, 1) or registro.get("natureza") == "D":
            continue
        meses = registro.get("meses", [])
        ambiguo |= bool(registro.get("celulas_invalidas"))
        for indice, valor in enumerate(registro.get("celulas", [])):
            if valor is None or valor <= 0:
                continue
            rotulo = meses[indice].strip().upper() if indice < len(meses) else ""
            if rotulo in ("TOTAL", "TOTAIS"):
                continue
            mes = MESES.get(rotulo[:3])
            if mes is None or registro["ano"] is None:
                ambiguo = True
            else:
                competencias.add((registro["ano"], mes))
    if ambiguo:
        return None, [
            (
                "Não foi possível identificar todas as competências ou valores da rubrica 750. "
                "Confira os pagamentos do adicional de férias e informe a quantidade de ocorrências."
            )
        ]
    return len(competencias), []


def valores_da_rubrica(dados: dict[str, Any], codigo: str) -> list[float]:
    return [valor for item in dados.get("rubricas", {}).get(codigo, []) for valor in item["valores"]]


def valores_principais_da_rubrica(dados: dict[str, Any], codigo: str) -> list[float]:
    """Retorna valores mensais inequívocos em ordem cronológica, sem totais."""
    competencias, pendentes = valores_por_competencia_da_rubrica(dados, codigo)
    if pendentes or any(valor is None for valor in competencias.values()):
        return []
    return [valor for _, valor in sorted(competencias.items()) if valor is not None]


def valores_por_competencia_da_rubrica(
    dados: dict[str, Any], codigo: str, *, naturezas: tuple[str, ...] = ("R", ""),
) -> tuple[dict[tuple[int, int], float | None], set[int | None]]:
    """Seleciona parcelas regulares por ano/mês, sem adivinhar colunas.

    Páginas/seq. 0 e 1 repetidas com o mesmo valor representam uma só parcela.
    Valores conflitantes ou ilegíveis mantêm None e exigem revisão. O conjunto
    retornado identifica anos com células sem competência/valor confiável.
    A natureza é específica da rubrica: PSS aceita deduções, salários não.
    """
    competencias: dict[tuple[int, int], float | None] = {}
    pendentes: set[int | None] = set()
    for registro in dados.get("rubricas", {}).get(codigo, []):
        if registro["sequencia"] not in (0, 1) or registro.get("natureza", "") not in naturezas:
            continue
        ano = registro.get("ano")
        meses = registro.get("meses", [])
        invalidas = set(registro.get("celulas_invalidas", []))
        for indice, valor in enumerate(registro.get("celulas", [])):
            rotulo = meses[indice].strip().upper() if indice < len(meses) else ""
            if rotulo in ("TOTAL", "TOTAIS"):
                continue
            if valor is None and indice not in invalidas:
                continue
            mes = MESES.get(rotulo[:3])
            if mes is None or ano is None:
                pendentes.add(ano)
                continue
            competencia = (ano, mes)
            if competencia in competencias and competencias[competencia] != valor:
                competencias[competencia] = None
                pendentes.add(ano)
            else:
                competencias[competencia] = valor
                if valor is None:
                    pendentes.add(ano)
    return competencias, pendentes
