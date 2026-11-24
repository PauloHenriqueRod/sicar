"""Somente rótulos inequívocos; candidatos exigem aplicação pelo operador."""

import re
from datetime import datetime


def substitution_candidates(text, alertas=None):
    date = r"(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}/[0-9]{2}/[0-9]{4})"
    pattern = re.compile(
        rf"^\s*(Designa[cç][aã]o|Afastamento do titular|F[eé]rias do substituto|Impedimento do substituto)\s*:\s*({date})\s+(?:a|at[eé])\s+({date})\s*\.?\s*$",
        re.IGNORECASE,
    )
    results = []
    for index, line in enumerate(text.splitlines()):
        match = pattern.fullmatch(line)
        if match is None:
            continue
        label, start, end = match.groups()
        try:
            values = [
                datetime.strptime(value, "%d/%m/%Y" if "/" in value else "%Y-%m-%d")
                .date()
                .isoformat()
                for value in (start, end)
            ]
        except ValueError:
            continue
        if len(results) >= 100:
            if alertas is not None:
                alertas.append(
                    "Extração incompleta: o documento contém mais de 100 períodos de substituição. "
                    "Somente os primeiros 100 foram apresentados; confira o documento completo "
                    "e preencha os períodos restantes manualmente ou divida o processo."
                )
            break
        field = (
            "DESIGNACAO"
            if label.casefold().startswith("designa")
            else "AFASTAMENTO_TITULAR"
            if label.casefold().startswith("afastamento")
            else "IMPEDIMENTO_SUBSTITUTO"
        )
        results.append(
            {
                "campo": field,
                "inicio": values[0],
                "ultimo_dia_considerado": values[1],
                "localizador": f"Linha {index + 1} do texto extraído",
            }
        )
    return results


def substitution_payment_observations(ficha, alertas=None):
    from app.utils.ficha_financeira import MESES

    results = []
    for row_index, row in enumerate(ficha.get("rubricas", {}).get("83185", [])):
        invalid = set(row.get("celulas_invalidas", []))
        for index, value in enumerate(row.get("celulas", [])):
            label = (
                row.get("meses", [])[index] if index < len(row.get("meses", [])) else ""
            )
            if label.strip().upper() in ("TOTAL", "TOTAIS") or (
                value is None and index not in invalid
            ):
                continue
            if len(results) >= 200:
                if alertas is not None:
                    alertas.append(
                        "Extração incompleta: o documento contém mais de 200 pagamentos observados da rubrica 83185. "
                        "Somente os primeiros 200 foram apresentados; confira a ficha completa "
                        "e preencha os pagamentos restantes manualmente ou divida o processo."
                    )
                return results
            month = MESES.get(label.strip().upper()[:3])
            text = str(value) if value is not None else ""
            results.append(
                {
                    "competencia": f"{row['ano']:04}-{month:02}"
                    if row.get("ano") and month
                    else None,
                    "rubrica": "83185",
                    "natureza_rubrica": row.get("natureza")
                    if row.get("natureza") in ("R", "D")
                    else None,
                    "sequencia": str(row["sequencia"]),
                    "valor_observado": text
                    if re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", text) and len(text) <= 60
                    else None,
                    "localizador": f"Rubrica 83185, registro {row_index + 1}, coluna {index + 1} ({label[:60]})",
                }
            )
    return results
