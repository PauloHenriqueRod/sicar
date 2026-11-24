"""Cadastro SIAPECAD: cabeçalhos em colunas e exercício em CARGO/EMPREGO."""

import re

from app.services.leitores_pdf.base import data_documental, extrair_base
from app.services.leitores_pdf.comuns import Evidencias, linhas, normalizar, origem

DATE = r"\d{2}(?:/\d{2}/\d{4}|[A-Za-zÇç]{3}\d{4})|\d{4}-\d{2}-\d{2}"


def ler(pages):
    active = [p for p in pages if not p.get("ignorar")]
    # O formato rotulado anterior continua delimitado e tem regressões próprias.
    if not any(
        "DADOS INDIVIDUAIS FUNCIONAIS" in normalizar(p["texto"]) for p in active
    ):
        return origem(
            extrair_base(pages), "cadastro_rotulado", [p["numero"] for p in active]
        )
    evidence = Evidencias(pages, "CADASTRO_FUNCIONAL")
    previous = None
    for page in active:
        number, text = page["numero"], page.get("texto_original", page["texto"])
        if not text.strip():
            evidence.doc["avisos"].append(
                f"Página {number} sem texto utilizável; confira manualmente. Não há OCR."
            )
        rows = linhas(page.get("palavras", []))
        values = {}
        for index, row in enumerate(rows):
            labels = " ".join(w["text"] for w in row)
            norm = normalizar(labels)
            anchors = []
            if "MATRICULA:" in norm and ("ORGAO:" in norm or "IDENT." in norm):
                anchors = [
                    (
                        "matricula",
                        next(
                            (
                                w["x0"]
                                for w in row
                                if "MATRICULA:" in normalizar(w["text"])
                            ),
                            None,
                        ),
                        next(
                            (
                                w["x0"]
                                for w in row
                                if normalizar(w["text"]).startswith("IDENT")
                            ),
                            float("inf"),
                        ),
                    )
                ]
            elif re.match(r"NOME:\s+REGIME", norm):
                regime = next(
                    (
                        w["x0"]
                        for w in row
                        if normalizar(w["text"]).startswith("REGIME")
                    ),
                    None,
                )
                situation = next(
                    (
                        w["x0"]
                        for w in row
                        if normalizar(w["text"]).startswith("SITUACAO")
                    ),
                    float("inf"),
                )
                anchors = [
                    ("nome", row[0]["x0"], regime),
                    ("regime_juridico", regime, situation),
                ]
            for key, left, right in anchors:
                if left is None or right is None:
                    continue
                for following in rows[index + 1 : index + 5]:
                    if following[0]["top"] - row[0]["top"] > 30:
                        break
                    value = " ".join(
                        w["text"] for w in following if left - 2 <= w["x0"] < right - 2
                    ).strip()
                    if not value:
                        continue
                    if key == "matricula" and not re.fullmatch(r"\d{1,12}", value):
                        break
                    if ":" in value or not value.strip():
                        break
                    values[key] = value
                    break
        mat, name = values.get("matricula"), values.get("nome")
        if (
            previous
            and (not mat or mat == previous.get("matricula"))
            and (not name or name == previous.get("nome"))
        ):
            block = previous
            if number not in block["paginas"]:
                block["paginas"].append(number)
        else:
            category = (
                "SUBSTITUTO"
                if "PROFESSOR SUBSTITUTO" in normalizar(text)
                else "NAO_IDENTIFICADA"
            )
            block = evidence.bloco(number, categoria=category, matricula=mat, nome=name)
        previous = block
        for key, value in values.items():
            evidence.campo(block, key, value, number)
        cargo = False
        for line in text.splitlines():
            norm = normalizar(line)
            if re.search(r"CARGO\s*[/ ]\s*EMPREGO", norm):
                cargo = True
                continue
            if cargo and re.match(
                r"\s*(?:FUNCAO|DADOS BANC|JORNADA|LOTA[CÇ]|DEPENDENTES|PREVIDENCIA|APOSENTADORIA)",
                norm,
            ):
                cargo = False
            if cargo:
                match = re.search(
                    rf"\bEXERC[IÍ]CIO\s*:\s*({DATE})", line, re.IGNORECASE
                )
                if match:
                    parsed = data_documental(match[1])
                    evidence.campo(
                        block,
                        "inicio_exercicio",
                        parsed.isoformat() if parsed else None,
                        number,
                        match[1],
                    )
                if re.match(r"\s*(?:GRUPO/CARGO|CARGO|CODIGO)\s*:", norm):
                    evidence.campo(
                        block, "cargo_lotacao", line.split(":", 1)[1].strip(), number
                    )
                for key, pattern in (
                    ("classe_observada", r"CLASSE\s*:\s*([A-Z0-9]+)"),
                    ("nivel_observado", r"NIVEL\s*:\s*(\d+)"),
                ):
                    match = re.search(pattern, norm)
                    if match:
                        evidence.campo(block, key, match[1], number)
        for match in re.finditer(
            r"JORNADA DE TRABALHO\s*\n([^\n]+)", text, re.IGNORECASE
        ):
            raw = match[1].strip()
            evidence.campo(block, "jornada_observada", raw, number)
            hours = re.search(r"\b(20|40)\s+HORAS\b", normalizar(raw))
            if hours:
                evidence.campo(block, "jornada", hours[1] + "H", number, raw)
    return evidence.finalizar(
        "cadastro_siapecad_colunas",
        ("nome", "matricula", "inicio_exercicio", "cargo_lotacao", "jornada"),
    )
