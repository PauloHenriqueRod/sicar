"""Despacho por conteúdo; uma região pertence a apenas um leitor."""

import re
from uuid import uuid4

from app.schemas.extracao_documentos import DocumentoExtraido
from app.services.leitores_pdf import (
    cacoferias_formulario,
    cadastro_substituto,
    fichas_siape,
)
from app.services.leitores_pdf.base import extrair_base
from app.services.leitores_pdf.comuns import normalizar, origem


def reconhecer(page):
    text = normalizar(page.get("texto_original", page["texto"]))
    candidates = []
    if re.search(r"FICHA\s+FINANCEIRA|RUBRICA\s*\|", text):
        candidates.append("ficha")
    if re.search(r"CARGO\s*[/ ]\s*EMPREGO|DADOS INDIVIDUAIS FUNCIONAIS", text):
        candidates.append("cadastro")
    if re.search(r"PARCELA\s*:\s*\d+", text) and re.search(r"QTDE\s*DE\s*DIAS", text):
        candidates.append("caco_form")
    elif "INICIO" in text and "DIAS" in text and "PARCELA" in text:
        candidates.append("caco_tab")
    return candidates


def extrair_documento(pages):
    from app.services.extracao_portarias import extrair_atos, linhas_anexo_tae

    prepared = [
        {
            **p,
            "linhas_tae": p.get("linhas_tae") or linhas_anexo_tae(p["palavras"])
            if p.get("palavras")
            else p.get("linhas_tae", []),
        }
        for p in pages
    ]
    acts, consumed = extrair_atos(prepared)
    documents = []
    if acts:
        documents.append(acts)
    groups = []
    previous = None
    vacation_start_column = None
    for page in prepared:
        if page["numero"] in consumed:
            previous = None
            continue
        if previous != "caco_tab":
            vacation_start_column = None
        candidates = reconhecer(page)
        text = page.get("texto_original", page["texto"])
        for raw in text.splitlines():
            labels = [normalizar(cell.strip()) for cell in raw.split("|")]
            if all(label in labels for label in ("INICIO", "DIAS", "PARCELA")):
                vacation_start_column = labels.index("INICIO")
        continuation = vacation_start_column is not None and any(
            len(cells := raw.split("|")) > vacation_start_column
            and re.fullmatch(r"\s*\d{2}(?:/\d{2}/|[A-Za-zÇç]{3})\d{4}\s*", cells[vacation_start_column])
            for raw in text.splitlines()
        )
        if len(candidates) > 1:
            family = "ambiguo"
        elif candidates:
            family = candidates[0]
        elif previous in ("ficha", "cadastro", "caco_tab") and (
            not text.strip()
            or (previous == "ficha" and re.search(r"^\s*\d{5}\b", text, re.MULTILINE))
            or (
                previous == "caco_tab"
                and (continuation or re.search(
                    r"^\s*\d{2}(?:/\d{2}/|[A-Za-zÇç]{3})\d{4}\b", text, re.MULTILINE
                ))
            )
            or (
                previous == "cadastro"
                and (
                    all(
                        marker in normalizar(text)
                        for marker in (
                            "DATA OPCAO VINC. RPC",
                            "RPPS",
                            "AUTORIZA ACESSO IRPF",
                        )
                    )
                )
            )
        ):
            family = previous
        else:
            family = "desconhecido"
        if groups and groups[-1][0] == family and previous == family:
            groups[-1][1].append(page["numero"])
        else:
            groups.append((family, [page["numero"]]))
        previous = family
    readers = {
        "ficha": fichas_siape.ler,
        "cadastro": cadastro_substituto.ler,
        "caco_form": cacoferias_formulario.ler,
        "caco_tab": fichas_siape.ler_tabular_ferias,
    }
    for family, numbers in groups:
        subset = [{**p, "ignorar": p["numero"] not in numbers} for p in prepared]
        if family in readers:
            doc = readers[family](subset)
        else:
            subset = [
                {
                    **p,
                    "texto": "Layout sem leitor delimitado; revisão manual."
                    if p["texto"].strip()
                    else "",
                }
                if not p["ignorar"]
                else p
                for p in subset
            ]
            doc = origem(extrair_base(subset), "nao_suportado", numbers)
            if family == "ambiguo":
                doc["avisos"].append(
                    "Mais de um layout na mesma região; nenhum leitor foi escolhido automaticamente."
                )
        documents.append(doc)
    if not documents:
        return extrair_base(pages)
    layouts = {d["layout"] for d in documents if d["layout"] != "NAO_SUPORTADO"}
    combined = {
        "id": str(uuid4()),
        "versao_leitor": "rh_paginas_v5",
        "total_paginas": len(pages),
        "layout": next(iter(layouts))
        if len(layouts) == 1
        else "MISTO"
        if layouts
        else "NAO_SUPORTADO",
        "situacao": "CONCLUIDO"
        if all(d["situacao"] == "CONCLUIDO" for d in documents)
        else "PARCIAL"
        if layouts
        else "SEM_TEXTO"
        if all(d["situacao"] == "SEM_TEXTO" for d in documents)
        else "NAO_SUPORTADO",
        "blocos": [b for d in documents for b in d["blocos"]],
        "campos": [f for d in documents for f in d["campos"]],
        "avisos": [w for d in documents for w in d["avisos"]][:100],
        "leitores": [r for d in documents for r in d.get("leitores", [])],
    }
    return DocumentoExtraido.model_validate(combined).model_dump(mode="json")
