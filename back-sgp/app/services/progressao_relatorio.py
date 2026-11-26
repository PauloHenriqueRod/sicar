"""Apresentação da memória salva de progressão, sem consultar tabelas ou recalcular."""

import json
from collections import defaultdict
from fractions import Fraction

from app.services.apuracao_periodos import moeda


def _mensal(exato):
    return moeda(Fraction(int(exato["numerador"]), int(exato["denominador"])))


def comparativo_folha(resultado):
    """Lê os operandos do motor, inclusive as vigências que dividem uma competência."""
    if not resultado.get("bases_mensais_origem") or not all(item.get("rt") for item in resultado["bases_mensais_origem"]):
        return []
    linhas = []
    for segmento in resultado["segmentos"]:
        for parcela in segmento["parcelas"]:
            componente = parcela["formula"]
            if componente not in ("VB", "RT"):
                continue
            fontes = [item["fonte"] for item in segmento["referencias_tabelas"]
                      if item.get("papel") == "DESTINO" and item.get("componente") == componente and item.get("fonte")]
            linhas.append({
                "inicio": segmento["inicio"], "fim": segmento["ultimo_dia_considerado"],
                "componente": componente, "pago": _mensal(parcela["valor_mensal_origem_exato"]),
                "destino": _mensal(parcela["valor_mensal_destino_exato"]),
                "diferenca": parcela["devido"], "fonte": " · ".join(dict.fromkeys(fontes)),
            })
    return linhas


def _texto(valor):
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, dict):
        if set(valor) == {"numerador", "denominador"}:
            return f"{valor['numerador']}/{valor['denominador']}"
        return " · ".join(f"{k.replace('_', ' ')}: {_texto(v)}" for k, v in valor.items() if v is not None)
    if isinstance(valor, list):
        return ", ".join(_texto(item) for item in valor)
    return str(valor)


def _fontes_documentais(revisao):
    aplicacoes = defaultdict(list)
    for item in revisao.get("aplicacoes", []):
        aplicacoes[item["documento_id"], item["campo_id"]].append(item)
    fontes = []
    for doc in revisao.get("documentos", []):
        nome = doc["nome_arquivo"]
        fontes.append(f"{nome} · {doc['situacao']}")
        for campo in doc["campos"]:
            usos = aplicacoes.get((doc["id"], campo["id"]), ())
            if not usos and not campo.get("correcao"):
                continue
            origem = f"{nome}, pág. {campo['pagina']} · {campo.get('rubrica') or campo['campo']}"
            if campo.get("competencia"):
                origem += f" · {campo['competencia']}"
            origem += f" · observado: {campo.get('valor')}"
            if campo.get("correcao"):
                origem += " · correção: " + _texto(campo["correcao"])
            for uso in usos:
                destino = ".".join(map(str, uso["destino"]))
                origem += f" · {destino}: {uso['valor_revisado']}"
                if uso.get("justificativa"):
                    origem += f" ({uso['justificativa']})"
            fontes.append(origem)
    return fontes


def relatorio_progressao(dados, resultado):
    entradas = {k: dados[k] for k in ("nome", "matricula", "identificacao_historico") if k in dados}
    plano = dados.get("progressao", {})
    for chave, valor in plano.items():
        if valor is None or valor == []:
            continue
        entradas[chave] = [_texto(x) for x in valor] if isinstance(valor, list) else _texto(valor)
    if dados.get("revisao_extracao"):
        entradas["fontes_documentais"] = _fontes_documentais(dados["revisao_extracao"])

    saida = {k: resultado[k] for k in ("total_geral_a_receber", "totais", "politica_arredondamento", "nota_arredondamento") if k in resultado}
    comparativo = comparativo_folha(resultado)
    if comparativo:
        saida["comparação_da_folha"] = [
            f"{r['inicio']} a {r['fim']} · {r['componente']} | pago mensal R$ {r['pago']} · "
            f"destino mensal R$ {r['destino']} · diferença do período R$ {r['diferenca']} · {r['fonte']}"
            for r in comparativo
        ]
    saldos = defaultdict(list)
    for linha in resultado["por_competencia"]:
        saldos[linha["competencia"]].append(
            f"{linha['rubrica']} · {linha['natureza_folha']} · {linha['natureza_rubrica']} | "
            f"Diferença devida R$ {linha['devido']} · Diferença já paga R$ {linha['recebido']} · Saldo R$ {linha['saldo']}"
            + (f" · lançamentos: {_texto(linha['lancamentos_recebidos'])}" if linha.get("lancamentos_recebidos") else "")
        )
    saida["saldos_por_competência"] = {mes: "\n".join(itens) for mes, itens in saldos.items()}
    catalogo = {}

    def registrar(tipo, item):
        chave = (tipo, json.dumps(item, ensure_ascii=False, sort_keys=True))
        if chave not in catalogo:
            catalogo[chave] = (f"{tipo} {len(catalogo) + 1}", _texto(item))
        return catalogo[chave][0]

    segmentos = {}
    for trecho in resultado["segmentos"]:
        referencias = [registrar("Estado", trecho["estado"])]
        referencias.extend(registrar("Regra", regra) for regra in trecho["referencias_regras"])
        referencias.extend(registrar("Base", base) for base in trecho["referencias_tabelas"])
        linhas = [f"{trecho['dias_computados']} dias computados · {', '.join(dict.fromkeys(referencias))}"]
        for chave in ("eventos_aplicados", "interrupcoes"):
            if trecho.get(chave):
                linhas.append(f"{chave.replace('_', ' ')}: {_texto(trecho[chave])}")
        for parcela in trecho["parcelas"]:
            valores = {k: v for k, v in parcela.items() if k not in ("regra", "rubrica")}
            regra = registrar("Regra", parcela["regra"])
            linhas.append(f"{parcela['rubrica']} · {regra} · " + _texto(valores))
        segmentos[f"{trecho['id']} · {trecho['inicio']} a {trecho['ultimo_dia_considerado']}"] = "\n".join(linhas)
    saida["segmentos"] = segmentos
    for chave in ("reflexos", "recebimentos_considerados", "duplicidades"):
        if resultado.get(chave):
            registros = []
            for item in resultado[chave]:
                registro = dict(item)
                if "referencias_tabelas" in registro:
                    registro["referencias_tabelas"] = [registrar("Base", base) for base in registro["referencias_tabelas"]]
                registros.append(_texto(registro))
            saida[chave] = registros
    saida["referências_dos_segmentos"] = dict(catalogo.values())
    return entradas, saida
