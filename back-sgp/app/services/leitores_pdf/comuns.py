"""Evidências pequenas e limitadas; não interpreta direitos ou remuneração devida."""

import re
import unicodedata
from uuid import uuid4

from app.schemas.extracao_documentos import DocumentoExtraido


def normalizar(text):
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)
    ).upper()


def linhas(words):
    rows = []
    for word in sorted(words, key=lambda w: (round(w["top"] / 3), w["x0"])):
        if not rows or abs(rows[-1][0]["top"] - word["top"]) > 3:
            rows.append([])
        rows[-1].append(word)
    return rows


def origem(doc, identifier, pages, version="1"):
    doc["leitores"] = [
        {"identificador": identifier, "versao": version, "paginas": pages}
    ]
    for field in doc["campos"]:
        field["leitor_id"], field["leitor_versao"] = identifier, version
    return doc


class Evidencias:
    def __init__(self, pages, layout):
        self.doc = {
            "id": str(uuid4()),
            "layout": layout,
            "situacao": "PARCIAL",
            "total_paginas": len(pages),
            "blocos": [],
            "campos": [],
            "avisos": [],
        }

    def bloco(self, page, **identity):
        block = {"id": str(uuid4()), "paginas": [page], **identity}
        self.doc["blocos"].append(block)
        return block

    def campo(self, block, name, value, page, raw=None, state=None, **extra):
        if len(self.doc["campos"]) >= 1900:
            raise ValueError("Divida o documento: excesso de campos.")
        if page not in block["paginas"]:
            block["paginas"].append(page)
        field = {
            "id": str(uuid4()),
            "bloco_id": block["id"],
            "campo": name,
            "valor": str(value)[:300] if value is not None else None,
            "observado": str(raw if raw is not None else value)[:300]
            if raw is not None or value is not None
            else None,
            "pagina": page,
            "localizador": f"Página {page}, campo {name}",
            "estado": state or ("EXTRAIDO" if value is not None else "ILEGIVEL"),
            **extra,
        }
        self.doc["campos"].append(field)
        if name in ("nome", "matricula", "vinculo") and value is not None:
            block[name] = str(value)
        return field

    def finalizar(self, identifier, required):
        for block in self.doc["blocos"]:
            fields = [f for f in self.doc["campos"] if f["bloco_id"] == block["id"]]
            for name in required:
                if not any(f["campo"] == name for f in fields):
                    self.doc["campos"].append(
                        {
                            "id": str(uuid4()),
                            "bloco_id": block["id"],
                            "campo": name,
                            "valor": None,
                            "estado": "AUSENTE",
                            "pagina": None,
                            "paginas_analisadas": block["paginas"],
                            "localizador": "Não encontrado nas páginas analisadas",
                        }
                    )
            for name in required:
                if name in ("periodo_ferias", "rubrica"):
                    continue
                found = [
                    f for f in fields if f["campo"] == name and f["valor"] is not None
                ]
                if len({f["valor"] for f in found}) > 1:
                    for field in found:
                        field["candidatos"] = list(
                            dict.fromkeys(f["valor"] for f in found)
                        )[:10]
                        field["valor"], field["estado"] = None, "AMBIGUO"
        self.doc["situacao"] = (
            "PARCIAL"
            if self.doc["avisos"]
            or any(f["estado"] != "EXTRAIDO" for f in self.doc["campos"])
            else "CONCLUIDO"
        )
        pages = sorted({p for b in self.doc["blocos"] for p in b["paginas"]})
        return DocumentoExtraido.model_validate(
            origem(self.doc, identifier, pages)
        ).model_dump(mode="json")


def identidade_rotulada(evidence, block, text, page):
    for name, pattern in (
        ("nome", r"\bNOME\s*:\s*([^\n]+)"),
        ("matricula", r"\bMATR[IÍ]CULA(?:SIAPE|\s+SIAPE)?\s*:\s*(\d+)\b"),
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            evidence.campo(block, name, match[1].strip(), page)
