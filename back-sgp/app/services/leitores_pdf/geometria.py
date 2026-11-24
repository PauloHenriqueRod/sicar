"""Reconstrução limitada das tabelas SIAPE e CACOFERIAS tabular."""

import re
from itertools import pairwise

from app.utils.employee_identity import employee_key
from app.utils.ficha_financeira import MESES


def linhas_posicionadas(words, contexto=None, largura=None):
    """Geometria de tabela com continuidade validada e divergências explícitas."""
    context = contexto if contexto is not None else {}
    context["ambiguidades"], context["avisos"] = [], []
    rows = []
    for word in sorted(words, key=lambda w: (round(w["top"] / 3), w["x0"])):
        if not rows or abs(rows[-1][0]["top"] - word["top"]) > 3:
            rows.append([])
        rows[-1].append(word)
    signal_lines, issuer = [], False
    for row in rows:
        line = " ".join(word["text"] for word in row)
        if re.search(
            r"RESPONS[ÁA]VEL\s+(?:PELA\s+)?EMISS[ÃA]O|EMITIDO\s+POR",
            line,
            re.IGNORECASE,
        ):
            issuer = True
            continue
        if issuer and re.match(
            r"\s*(?:Ficha Financeira|CACOFERIAS|CARGO/EMPREGO)", line, re.IGNORECASE
        ):
            issuer = False
        if not issuer:
            signal_lines.append(line)
    text_page = "\n".join(signal_lines)
    signals = {}
    for key, pattern in (
        ("matricula", r"(?:Nome:\s*|Matr[ií]cula(?: SIAPE)?\s*:\s*)(\d+)\b"),
        ("nome", r"^\s*Nome:\s*(?:\d+\s*-\s*)?(.+?)(?:\s+Banco/Ag[êe]ncia.*|$)"),
        ("vinculo", r"^\s*(?:V[ií]nculo|Contrato)\s*:\s*(.+)$"),
        ("ano", r"referente a:\s*(\d{4})"),
    ):
        found = set(re.findall(pattern, text_page, re.IGNORECASE | re.MULTILINE))
        if key == "matricula":
            found = {employee_key(value) for value in found}
        elif key == "nome":
            found = {value.strip().casefold() for value in found}
        if len(found) == 1:
            signals[key] = found.pop()
        elif len(found) > 1:
            signals[key] = "MULTIPLOS"
    previous = context.get("tabela")
    incompatible = previous and (
        any(value == "MULTIPLOS" for value in previous["sinais"].values())
        or (
            largura is not None
            and previous.get("largura") is not None
            and abs(largura - previous["largura"]) > 1
        )
        or any(
            value == "MULTIPLOS"
            or (key in previous["sinais"] and previous["sinais"][key] != value)
            for key, value in signals.items()
        )
        or re.search(r"CARGO\s*[/ ]\s*EMPREGO|DADOS BANC", text_page, re.IGNORECASE)
    )
    inherited = previous if previous and not incompatible else None
    result, columns, vacation_columns = [], None, None
    months, used, header_needed = [], False, bool(inherited)
    if inherited:
        columns, months = inherited["colunas"], inherited["meses"]
        vacation_columns = inherited.get("ferias")

    def financial_row(row):
        nonlocal used, header_needed, columns, months
        # R/D e sequência delimitam a descrição independentemente do tamanho do valor.
        position = next(
            (
                i
                for i in range(1, len(row) - 1)
                if row[i]["text"].upper() in ("R", "D")
                and re.fullmatch(r"\d+", row[i + 1]["text"])
            ),
            None,
        )
        if position is None:
            context["avisos"].append(
                "Linha com código de rubrica sem natureza/sequência delimitadas; confira manualmente."
            )
            return False
        tail = row[position + 2 :]
        if not tail:
            return False
        orphan = columns is None
        labels = months if not orphan else ["SEM_COMPETENCIA"] * len(tail)
        if orphan or header_needed:
            result.append("Rubrica|Nome|R/D|Seq.|" + "|".join(labels))
            header_needed = False
        cells = [[] for _ in labels]
        ambiguous = set()
        starts = columns[2:] if columns else []
        boundaries = [(a + b) / 2 for a, b in pairwise(starts)]
        for index, word in enumerate(tail):
            if orphan:
                target = index
            else:
                center = (word["x0"] + word["x1"]) / 2
                centered = sum(center >= edge for edge in boundaries)
                left = sum(word["x0"] >= start - 0.5 for start in starts) - 1
                contained = left >= 0 and (
                    left == len(starts) - 1 or word["x1"] <= starts[left + 1] + 0.5
                )
                target = left if contained else centered
                if not contained or left != centered:
                    ambiguous.add(target)
            cells[target].append(word["text"])
        if orphan:
            context["avisos"].append(
                "Ocorrências sem cabeçalho compatível: valores preservados sem competência presumida."
            )
        if ambiguous:
            context["avisos"].append(
                "Alinhamento de valores admite mais de uma coluna; confira as competências indicadas como ambíguas."
            )
        line = len(result) + 1
        context["ambiguidades"].extend((line, index) for index in ambiguous)
        result.append(
            "|".join(
                [
                    row[0]["text"],
                    " ".join(w["text"] for w in row[1:position]),
                    row[position]["text"].upper(),
                    row[position + 1]["text"],
                    *(" ".join(cell) for cell in cells),
                ]
            )
        )
        used = not orphan
        # Um cabeçalho provisório não pode mudar a geometria das próximas linhas.
        if orphan:
            header_needed = True
        return True

    for row in rows:
        text = " ".join(w["text"] for w in row)
        upper = text.upper()
        normalized = [w["text"].upper().replace("Í", "I") for w in row]
        if all(label in normalized for label in ("INICIO", "DIAS", "PARCELA")):
            vacation_columns = [
                (w["x0"], label)
                for w, label in zip(row, normalized, strict=True)
                if label
                in (
                    "MATRICULA",
                    "NOME",
                    "VINCULO",
                    "EXERCICIO",
                    "INICIO",
                    "DIAS",
                    "FIM",
                    "PARCELA",
                )
            ]
            columns = None
            months, inherited, header_needed = [], None, False
            used = True
            result.append("|".join(label for _, label in vacation_columns))
            continue
        if vacation_columns and re.search(r"\d{2}(?:/\d{2}/|[A-Za-zÇç]{3})\d{4}", text):
            if header_needed:
                result.append("|".join(label for _, label in vacation_columns))
                header_needed = False
            anchors = [x for x, _ in vacation_columns]
            boundaries = [(a + b) / 2 for a, b in pairwise(anchors)]
            cells = [[] for _ in vacation_columns]
            for word in row:
                center = (word["x0"] + word["x1"]) / 2
                cells[sum(center >= edge for edge in boundaries)].append(word["text"])
            result.append("|".join(" ".join(cell) for cell in cells))
            used = True
            continue
        if "RUBRICA" in upper and any(w["text"].upper()[:3] in MESES for w in row):
            months = [
                w
                for w in row
                if w["text"].upper()[:3] in MESES or w["text"].upper() == "TOTAL"
            ]
            nature = next(
                (w for w in row if w["text"].upper() in ("R/D", "R / D")), None
            )
            sequence = next(
                (
                    w
                    for w in row
                    if w["text"].upper().strip(".") in ("SEQ", "SEQUENCIA", "SEQUÊNCIA")
                ),
                None,
            )
            if nature and sequence:
                vacation_columns = None
                columns = [nature["x0"], sequence["x0"], *[w["x0"] for w in months]]
                months = [w["text"] for w in months]
                result.append("Rubrica|Nome|R/D|Seq.|" + "|".join(months))
                used, header_needed = True, False
                continue
        if re.fullmatch(r"\d{5}", row[0]["text"]) and financial_row(row):
            continue
        result.append(text)
    if (columns or vacation_columns) and used:
        old_signals = inherited["sinais"] if inherited else {}
        context["tabela"] = {
            "colunas": columns,
            "meses": months,
            "largura": largura,
            "sinais": {**old_signals, **signals},
            "ferias": vacation_columns,
        }
    else:
        context.pop("tabela", None)
    return "\n".join(result)
