"""Interpretação pura de documentos; executada dentro do leitor com limites de recursos."""
import re
from typing import Any

from app.utils.conversor import ConversorSaneador
from app.utils.ficha_financeira import (
    VALOR_RE,
    contar_pagamentos_ferias,
    extrair_dados_ficha_financeira,
    valores_por_competencia_da_rubrica,
)


def _ano_documento(texto: str) -> int | None:
    anos = set(re.findall(r"referente a:\s*(\d{4})", texto, re.IGNORECASE))
    return int(anos.pop()) if len(anos) == 1 else None


def _sanitize(value):
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return ConversorSaneador.sanitizar_texto(value)
    return value


def _extrair_abono(texto: str, ficha: dict[str, Any]) -> dict[str, Any]:
    competencias, pendentes = valores_por_competencia_da_rubrica(
        ficha, "98002", naturezas=("D", ""),
    )
    anuais: dict[str, list[float | None]] = {}
    for (ano_competencia, _), valor in sorted(competencias.items()):
        # Estornos exigem análise da competência; não podem desaparecer da
        # soma nem ser convertidos automaticamente em um novo pagamento.
        anuais.setdefault(str(ano_competencia), []).append(valor if valor is not None and valor >= 0 else None)
        if valor is not None and valor < 0:
            pendentes.add(ano_competencia)
    legados: dict[str, list[float | None]] = {}
    ano_atual: int | None = None
    for linha in texto.splitlines():
        ano_cabecalho = re.search(r"referente a:\s*(\d{4})", linha, re.IGNORECASE)
        if ano_cabecalho:
            ano_atual = int(ano_cabecalho.group(1))
        legado = re.search(r"Ano:\s*(\d{4})\s*\|\s*Valores:\s*(.*)", linha, re.IGNORECASE)
        if legado:
            ano_legado, texto_valores = legado.groups()
            parcelas: list[float | None] = []
            # Neste layout explícito cada R$ delimita uma parcela; a vírgula
            # entre parcelas não é parte do token monetário nem um TOTAL.
            for parcela in re.split(r",\s*(?=R\$)|;", texto_valores):
                token = parcela.replace("R$", "").strip()
                valor = ConversorSaneador.para_float(token) if token == "0" or VALOR_RE.fullmatch(token) else None
                parcelas.append(valor if valor is not None and valor >= 0 else None)
            legados.setdefault(ano_legado, []).extend(parcelas)
        elif re.match(r"\s*98002\b", linha) and not re.match(
            r"\s*98002\s*\|[^|]+\|[^|]*\|\s*\d+\s*\|", linha,
        ):
            # Texto sem cabeçalho/delimitação não diferencia parcelas de TOTAL.
            pendentes.add(ano_atual)
    for ano_legado, valores_legados in legados.items():
        if ano_legado in anuais:
            pendentes.add(int(ano_legado))
        else:
            anuais[ano_legado] = valores_legados
    for ano_pendente in pendentes:
        valores = anuais.setdefault(str(ano_pendente) if ano_pendente is not None else "Ano a conferir", [])
        if None not in valores:
            valores.append(None)
    dados: dict[str, Any] = {"valores_anuais": anuais}
    if any(valor is None for valores in anuais.values() for valor in valores):
        dados["alertas_extracao"] = [
            (
                "Confira as competências e os valores da rubrica 98002. "
                "Há valores ilegíveis, conflitantes ou sem competência identificada; "
                "preencha os campos pendentes antes de calcular."
            )
        ]
    return dados


def extract_calculation_data(texto_completo: str, tipo_calculo: str, *, incluir_fontes_rescisao: bool = False, incluir_fontes_abono: bool = False, incluir_fontes_exercicios: bool = False) -> dict[str, Any]:
    dados_extraidos: dict[str, Any] = {}
    percentuais_informados: set[str] = set()
    dados_ficha = extrair_dados_ficha_financeira(texto_completo)

    if tipo_calculo == "substituicao":
        from app.utils.substitution_candidates import (
            substitution_candidates,
            substitution_payment_observations,
        )
        alertas_substituicao: list[str] = []
        dados_extraidos = {
            "nome": "N/A", "matricula": "N/A", "salario_substituta": None,
            "salario_propria": None, "dias_substituidos": None, "dias_interrupcao": None,
            "mes": None, "ano": _ano_documento(texto_completo),
            "_candidatos_substituicao": substitution_candidates(texto_completo, alertas_substituicao),
            "_pagamentos_substituicao": substitution_payment_observations(dados_ficha, alertas_substituicao),
            "alertas_extracao": alertas_substituicao,
        }
        match_nome = re.search(r"Nome:\s*(.+)", texto_completo, re.IGNORECASE)
        if match_nome: dados_extraidos["nome"] = match_nome.group(1).strip()
        match_mat = re.search(r"Matr[íi]cula:\s*(\d+)", texto_completo, re.IGNORECASE)
        if match_mat: dados_extraidos["matricula"] = match_mat.group(1).strip()
        match_sal_sub = re.search(r"Sal[áa]rio Substituta:\s*R?\$\s*([\d\.,]+)", texto_completo, re.IGNORECASE)
        if match_sal_sub: dados_extraidos["salario_substituta"] = ConversorSaneador.para_float(match_sal_sub.group(1))
        match_sal_prop = re.search(r"Sal[áa]rio Pr[óo]pria:\s*R?\$\s*([\d\.,]+)", texto_completo, re.IGNORECASE)
        if match_sal_prop: dados_extraidos["salario_propria"] = ConversorSaneador.para_float(match_sal_prop.group(1))
        match_dias = re.search(r"Dias Substitu[íi]dos:\s*(\d+)", texto_completo, re.IGNORECASE)
        if match_dias: dados_extraidos["dias_substituidos"] = int(match_dias.group(1))
        match_mes = re.search(r"M[êe]s:\s*(\d+)", texto_completo, re.IGNORECASE)
        if match_mes: dados_extraidos["mes"] = int(match_mes.group(1))
        match_ano = re.search(r"Ano:\s*(\d+)", texto_completo, re.IGNORECASE)
        if match_ano: dados_extraidos["ano"] = int(match_ano.group(1))
        # No layout da ficha, Nome contém a matrícula do servidor; uma
        # matrícula isolada pode identificar o responsável pela emissão.
        for field in ("nome", "matricula"):
            if field in dados_ficha:
                dados_extraidos[field] = dados_ficha[field]

    elif tipo_calculo == "insalubridade":
        valores_mensais = {}
        for linha in texto_completo.split('\n'):
            match = re.search(r"Mes:\s*(.+?)\s*\|\s*Valor Base:\s*R?\$\s*([\d\.,]+)", linha, re.IGNORECASE)
            if match:
                valores_mensais[match.group(1).strip()] = ConversorSaneador.para_float(match.group(2))
        dados_extraidos = {"valores_mensais": valores_mensais}

    elif tipo_calculo == "abono":
        dados_extraidos = _extrair_abono(texto_completo, dados_ficha)
        if incluir_fontes_abono:
            from app.utils.abono_candidates import extrair_observacoes_abono
            observacoes, avisos = extrair_observacoes_abono(dados_ficha)
            dados_extraidos["_observacoes_abono"] = observacoes
            if avisos:
                dados_extraidos.setdefault("alertas_extracao", []).extend(avisos)

    elif tipo_calculo == "rescisao":
        from app.utils.rescisao_candidates import extrair_fontes_rescisao
        fontes_rescisao, avisos_rescisao = extrair_fontes_rescisao(texto_completo, dados_ficha)
        dados_extraidos = {
            "classe": "", "nivel": None, "titulacao": "", "meses_ferias": 0.0, "meses_13": 0, "dias_trabalhados": 0, "valores_recebidos": {},
            "mes_rescisao": None, "ano_rescisao": None,
        }
        match_classe = re.search(r"Classe:\s*(.+)", texto_completo, re.IGNORECASE)
        if match_classe: dados_extraidos["classe"] = match_classe.group(1).strip()
        match_nivel = re.search(r"N[ií]vel:\s*(\d+)", texto_completo, re.IGNORECASE)
        if match_nivel: dados_extraidos["nivel"] = int(match_nivel.group(1))
        match_titulacao = re.search(r"Titula[çc][ãa]o:[ \t]*([^\r\n]+)", texto_completo, re.IGNORECASE)
        if match_titulacao: dados_extraidos["titulacao"] = match_titulacao.group(1).strip()
        match_ferias = re.search(r"Meses de F[eé]rias:\s*([\d\.,]+)", texto_completo, re.IGNORECASE)
        if match_ferias: dados_extraidos["meses_ferias"] = ConversorSaneador.para_float(match_ferias.group(1))
        match_13 = re.search(r"Meses 13[oº]?:\s*(\d+)", texto_completo, re.IGNORECASE)
        if match_13: dados_extraidos["meses_13"] = int(match_13.group(1))
        match_dias = re.search(r"Dias Trabalhados:\s*(\d+)", texto_completo, re.IGNORECASE)
        if match_dias: dados_extraidos["dias_trabalhados"] = int(match_dias.group(1))

        for linha in texto_completo.split('\n'):
            match_rec = re.search(r"Recebido (.+?):\s*R?\$\s*([\d\.,]+)", linha, re.IGNORECASE)
            if match_rec:
                dados_extraidos["valores_recebidos"][match_rec.group(1).strip()] = ConversorSaneador.para_float(match_rec.group(2))  # type: ignore

        exercicio = re.search(r"EXERCICIO:\s*(\d{2}[A-ZÇ]{3}\d{4})", texto_completo, re.IGNORECASE)
        if exercicio:
            dados_extraidos["data_exercicio"] = exercicio.group(1).upper()
        rescisao = re.search(r"Data (?:de )?Rescis[ãa]o:\s*(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})", texto_completo, re.IGNORECASE)
        if rescisao and (data_rescisao := ConversorSaneador.para_data(rescisao.group(1))):
            dados_extraidos["data_rescisao"] = data_rescisao.isoformat()
            dados_extraidos["mes_rescisao"] = data_rescisao.month
            dados_extraidos["ano_rescisao"] = data_rescisao.year
        salarios, salarios_pendentes = valores_por_competencia_da_rubrica(dados_ficha, "00742")
        if dados_ficha["rubricas"].get("00742") and "742_salario" not in dados_extraidos["valores_recebidos"]:
            competencia = (dados_extraidos["ano_rescisao"], dados_extraidos["mes_rescisao"])
            salario = salarios.get(competencia)
            if None in salarios_pendentes or competencia[0] in salarios_pendentes or salario is None or salario < 0:
                dados_extraidos["valores_recebidos"]["742_salario"] = None
                dados_extraidos.setdefault("alertas_extracao", []).append(
                    "Confira o salário recebido na competência da rescisão (rubrica 742). "
                    "Não foi possível selecionar um valor mensal inequívoco."
                )
            else:
                dados_extraidos["valores_recebidos"]["742_salario"] = salario
        if incluir_fontes_rescisao:
            dados_extraidos["_fontes_rescisao"] = fontes_rescisao
        if avisos_rescisao:
            dados_extraidos.setdefault("alertas_extracao", []).extend(avisos_rescisao)
        ocorrencias_ferias, alertas = contar_pagamentos_ferias(dados_ficha)
        dados_extraidos["ocorrencias_adicional_ferias"] = ocorrencias_ferias
        if alertas:
            dados_extraidos.setdefault("alertas_extracao", []).extend(alertas)

    elif tipo_calculo == "progressao":
        dados_extraidos = {
            "classe_atual": "", "nivel_atual": None, "titulacao": "",
            "classe_antiga": "", "nivel_antigo": None, "anuenio": 0.0,
            "insalubridade": 0.0, "incentivo": 0.0,
            "incentivo_antigo": None, "incentivo_novo": None,
            "meses_diferenca": 0.0, "dias_proporcionais": 0,
            "mes_proporcao": None, "ano_proporcao": _ano_documento(texto_completo),
            "quantidade_reflexos_ferias": 1.0, "quantidade_reflexos_13": 1.0,
        }
        match_c_atual = re.search(r"Classe Atual:\s*(.+)", texto_completo, re.IGNORECASE)
        if match_c_atual: dados_extraidos["classe_atual"] = match_c_atual.group(1).strip()
        match_n_atual = re.search(r"N[ií]vel Atual:\s*(\d+)", texto_completo, re.IGNORECASE)
        if match_n_atual: dados_extraidos["nivel_atual"] = int(match_n_atual.group(1))
        match_titulacao = re.search(r"Titula[çc][ãa]o:[ \t]*([^\r\n]+)", texto_completo, re.IGNORECASE)
        if match_titulacao: dados_extraidos["titulacao"] = match_titulacao.group(1).strip()

        match_c_antiga = re.search(r"Classe Antiga:\s*(.+)", texto_completo, re.IGNORECASE)
        if match_c_antiga: dados_extraidos["classe_antiga"] = match_c_antiga.group(1).strip()
        match_n_antiga = re.search(r"N[ií]vel Antigo:\s*(\d+)", texto_completo, re.IGNORECASE)
        if match_n_antiga: dados_extraidos["nivel_antigo"] = int(match_n_antiga.group(1))
        match_anuenio = re.search(r"Anu[êe]nio \(%\):\s*([\d\.,]+)", texto_completo, re.IGNORECASE)
        if match_anuenio: dados_extraidos["anuenio"] = ConversorSaneador.para_float(match_anuenio.group(1))
        match_insalub = re.search(r"Insalubridade \(%\):\s*([\d\.,]+)", texto_completo, re.IGNORECASE)
        if match_insalub: dados_extraidos["insalubridade"] = ConversorSaneador.para_float(match_insalub.group(1))
        match_incentivo = re.search(r"Incentivo \(%\):\s*([\d\.,]+)", texto_completo, re.IGNORECASE)
        if match_incentivo: dados_extraidos["incentivo"] = ConversorSaneador.para_float(match_incentivo.group(1))
        percentuais_informados = {
            campo for campo, encontrado in (
                ("anuenio", match_anuenio), ("insalubridade", match_insalub), ("incentivo", match_incentivo)
            ) if encontrado is not None
        }
        match_incentivo_antigo = re.search(r"Incentivo Antigo \(%\):\s*([\d\.,]+)", texto_completo, re.IGNORECASE)
        if match_incentivo_antigo: dados_extraidos["incentivo_antigo"] = ConversorSaneador.para_float(match_incentivo_antigo.group(1))
        match_incentivo_novo = re.search(r"Incentivo Novo \(%\):\s*([\d\.,]+)", texto_completo, re.IGNORECASE)
        if match_incentivo_novo: dados_extraidos["incentivo_novo"] = ConversorSaneador.para_float(match_incentivo_novo.group(1))
        match_meses = re.search(r"Meses de Diferen[çc]a:\s*([\d\.,]+)", texto_completo, re.IGNORECASE)
        if match_meses: dados_extraidos["meses_diferenca"] = ConversorSaneador.para_float(match_meses.group(1))
        match_dias = re.search(r"Dias Proporcionais:\s*(\d+)", texto_completo, re.IGNORECASE)
        if match_dias: dados_extraidos["dias_proporcionais"] = int(match_dias.group(1))
        match_mes = re.search(r"M[êe]s Proporcional:\s*(\d+)", texto_completo, re.IGNORECASE)
        if match_mes: dados_extraidos["mes_proporcao"] = int(match_mes.group(1))
        match_ano = re.search(r"Ano Proporcional:\s*(\d{4})", texto_completo, re.IGNORECASE)
        if match_ano: dados_extraidos["ano_proporcao"] = int(match_ano.group(1))

    elif tipo_calculo == "exercicio_anterior":
        fluxo = []
        for linha in texto_completo.split('\n'):
            match = re.search(r"Periodo:\s*(.+?)\s*\|\s*Devido:\s*R?\$\s*([\d\.,]+)\s*\|\s*Recebido:\s*R?\$\s*([\d\.,]+)\s*\|\s*Abono:\s*R?\$\s*([\d\.,]+)\s*\|\s*13o:\s*R?\$\s*([\d\.,]+)", linha, re.IGNORECASE)
            if match:
                fluxo.append({
                    "periodo": match.group(1).strip(),
                    "v_dev": ConversorSaneador.para_float(match.group(2)),
                    "v_rec": ConversorSaneador.para_float(match.group(3)),
                    "ab_ferias": ConversorSaneador.para_float(match.group(4)),
                    "13_sal": ConversorSaneador.para_float(match.group(5)),
                })
        dados_extraidos = {"fluxo_mensal": fluxo}
        if incluir_fontes_exercicios:
            from app.utils.exercicios_candidates import extrair_candidatos_exercicios
            candidates, warnings = extrair_candidatos_exercicios(texto_completo, dados_ficha)
            dados_extraidos["_candidatos_exercicios"] = candidates
            if warnings:
                dados_extraidos.setdefault("alertas_extracao", []).extend(warnings)
    else:
        raise ValueError("Tipo de cálculo desconhecido")

    for campo in (
        "nome", "matricula", "cargo_lotacao", "classe", "nivel", "funcao_exercida",
        "quantidade_anuenios", "percentual_anuenio", "vencimento_basico",
        "valor_insalubridade", "percentual_insalubridade", "percentual_adicional_sugerido",
    ):
        if tipo_calculo == "progressao" and campo in ("percentual_anuenio", "percentual_insalubridade"):
            continue
        if campo in dados_ficha and dados_extraidos.get(campo) in (None, "", "N/A", 0, 0.0):
            dados_extraidos[campo] = dados_ficha[campo]
    if tipo_calculo == "progressao":
        if dados_extraidos.get("classe_atual") in (None, "", "N/A") and dados_ficha.get("classe"):
            dados_extraidos["classe_atual"] = dados_ficha["classe"]
        if dados_extraidos.get("nivel_atual") in (None, 0) and dados_ficha.get("nivel"):
            dados_extraidos["nivel_atual"] = dados_ficha["nivel"]
        # A ausência de um campo permite completar a ficha; zero informado
        # explicitamente também é um valor revisado e precisa ser preservado.
        for campo, origem in (
            ("anuenio", "percentual_anuenio"),
            ("insalubridade", "percentual_insalubridade"),
            ("incentivo", "percentual_incentivo"),
        ):
            if campo not in percentuais_informados and origem in dados_ficha:
                dados_extraidos[campo] = dados_ficha[origem]
        if (
            "insalubridade" not in percentuais_informados
            and dados_ficha["rubricas"].get("00053")
            and "percentual_insalubridade" not in dados_ficha
        ):
            dados_extraidos["insalubridade"] = None
            dados_extraidos.setdefault("alertas_extracao", []).append(
                "Confira espécie, percentual, base, regra e vigência do adicional na concessão. "
                "A razão adicional/VB, quando disponível, é somente uma sugestão revisável."
            )
    return _sanitize(dados_extraidos)
