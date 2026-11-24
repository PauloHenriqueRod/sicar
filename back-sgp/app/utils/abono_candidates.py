"""Observações de desconto e abono; nenhuma observação confirma o direito."""

import re
from decimal import Decimal, InvalidOperation

from app.utils.ficha_financeira import MESES, VALOR_RE


def extrair_observacoes_abono(ficha):
    observations, warnings = [], []
    for code, records in ficha.get("rubricas", {}).items():
        for row in records:
            description = row.get("nome", "")
            if code not in ("98002", "98004") and not (
                re.search(r"ABONO|\bAB\.", description, re.IGNORECASE)
                and re.search(r"PERM", description, re.IGNORECASE)
            ):
                continue
            for index, raw in enumerate(row.get("celulas_texto", [])):
                labels = row.get("meses", [])
                label = labels[index].strip().upper() if index < len(labels) else ""
                if label in ("TOTAL", "TOTAIS") or raw.strip() in ("", "-", "—"):
                    continue
                if len(observations) >= 200:
                    warnings.append(
                        "Extração incompleta: mais de 200 observações de contribuição/abono neste documento. Confira a ficha completa e preencha os demais lançamentos manualmente."
                    )
                    return observations, warnings
                token = raw.replace("R$", "").replace(" ", "").strip()
                value = None
                if token == "0" or VALOR_RE.fullmatch(token):
                    try:
                        parsed = Decimal(
                            token.replace(".", "").replace(",", ".")
                            if "," in token
                            else token
                        )
                        if parsed.is_finite() and len(format(parsed, "f")) <= 60:
                            value = format(parsed, "f")
                    except InvalidOperation:
                        pass
                month = MESES.get(label[:3])
                observation = {
                    "rubrica": code,
                    "descricao": description[:200],
                    "competencia": f"{row['ano']:04}-{month:02}"
                    if row.get("ano") and month
                    else None,
                    "natureza_rubrica": row.get("natureza")
                    if row.get("natureza") in ("R", "D")
                    else None,
                    "sequencia": str(row.get("sequencia", "")),
                    "valor_observado": value,
                    "localizador": f"{row.get('localizador', 'Linha a conferir')}, coluna {index + 1} ({label[:40]})",
                    "decisao": "PENDENTE",
                }
                observations.append(observation)
                if (
                    value is None
                    or observation["competencia"] is None
                    or observation["natureza_rubrica"] is None
                ):
                    if not any("ilegíveis" in warning for warning in warnings):
                        warnings.append(
                            "Há observações ilegíveis ou sem competência/natureza: revise os campos, sem presumir zero."
                        )
    return observations, warnings
