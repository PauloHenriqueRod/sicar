"""Candidatos de demonstrativos e fichas; direito e rubrica devida não são presumidos."""

import re
from decimal import Decimal, InvalidOperation

from app.utils.ficha_financeira import MESES, VALOR_RE


def valor_observado(raw):
    token = raw.replace("R$", "").replace(" ", "").strip()
    if token not in ("0", "+0", "-0") and not VALOR_RE.fullmatch(token):
        return None
    try:
        value = Decimal(
            token.replace(".", "").replace(",", ".") if "," in token else token
        )
        return (
            format(value, "f")
            if value.is_finite() and len(format(value, "f")) <= 60
            else None
        )
    except InvalidOperation:
        return None


def extrair_candidatos_exercicios(text, ficha):
    results, warnings = [], []
    for line_number, line in enumerate(text.splitlines(), 1):
        period = re.search(
            r"(?:Per[ií]odo|Compet[eê]ncia)\s*:\s*([0-9]{4}-[0-9]{2}|[0-9]{2}/[0-9]{4})\b",
            line,
            re.IGNORECASE,
        )
        if not period:
            continue
        competence = period.group(1)
        if "/" in competence:
            month, year = competence.split("/")
            competence = f"{year}-{month}"
        if not 1 <= int(competence[5:]) <= 12 or int(competence[:4]) < 1:
            competence = None
        rubric = re.search(r"\bRubrica\s*:\s*([0-9]{1,8})\b", line, re.IGNORECASE)
        for cell in line.split("|"):
            match = re.fullmatch(
                r"\s*(Devido|Recebido|F[eé]rias|Abono|13[oº]|13_sal)\s*:\s*(.*?)\s*",
                cell,
                re.IGNORECASE,
            )
            if not match:
                continue
            label, raw = match.groups()
            results.append(
                {
                    "tipo": "RECEBIMENTO"
                    if label.casefold() == "recebido"
                    else "DEVIDO",
                    "competencia": competence,
                    "rubrica": rubric.group(1).zfill(5) if rubric else None,
                    "valor_observado": valor_observado(raw),
                    "descricao": label,
                    "localizador": f"Linha {line_number}, campo {label}",
                    "decisao": "PENDENTE",
                }
            )
            if len(results) > 200:
                return results[:200], [
                    "Extração incompleta: mais de 200 candidatos; confira o documento inteiro e complete manualmente."
                ]
    for code, rows in ficha.get("rubricas", {}).items():
        for row in rows:
            for index, raw in enumerate(row.get("celulas_texto", [])):
                labels = row.get("meses", [])
                label = labels[index].strip().upper() if index < len(labels) else ""
                if label in ("TOTAL", "TOTAIS") or raw.strip() in ("", "-", "—"):
                    continue
                month = MESES.get(label[:3])
                results.append(
                    {
                        "tipo": "RECEBIMENTO",
                        "competencia": f"{row['ano']:04}-{month:02}"
                        if row.get("ano") and month
                        else None,
                        "rubrica": code,
                        "sequencia": str(row["sequencia"])
                        if row.get("sequencia") is not None
                        else None,
                        "natureza_rubrica": row.get("natureza")
                        if row.get("natureza") in ("R", "D")
                        else None,
                        "valor_observado": valor_observado(raw),
                        "descricao": row.get("nome", "")[:200],
                        "localizador": f"{row.get('localizador', 'Linha a conferir')}, coluna {index + 1} ({label[:40]})",
                        "decisao": "PENDENTE",
                    }
                )
                if len(results) > 200:
                    return results[:200], [
                        "Extração incompleta: mais de 200 candidatos; confira o documento inteiro e complete manualmente."
                    ]
    if any(
        row["valor_observado"] is None or row["competencia"] is None for row in results
    ):
        warnings.append(
            "Há valores ou competências desconhecidos. Revise os candidatos, sem presumir zero."
        )
    if not results:
        warnings.append(
            "Layout sem dados estruturados reconhecidos; preencha as parcelas e fontes manualmente."
        )
    return results, warnings
