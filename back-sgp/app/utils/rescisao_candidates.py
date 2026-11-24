"""Leitores delimitados: observações editáveis, nunca concessões confirmadas."""

import re

from app.utils.conversor import ConversorSaneador
from app.utils.ficha_financeira import MESES


def extrair_fontes_rescisao(text, ficha):
    candidates, payments, warnings = [], [], []
    cargo = False
    cargo_lines = 0
    for number, line in enumerate(text.splitlines(), 1):
        if re.search(r"CARGO\s*[/ ]\s*EMPREGO", line, re.IGNORECASE):
            cargo, cargo_lines = True, 0
        if cargo:
            cargo_lines += 1
            if cargo_lines > 12 or re.match(
                r"\s*(?:DADOS BANC|DEPENDENTES|APOSENTADORIA|LOTA[CÇ])",
                line,
                re.IGNORECASE,
            ):
                cargo = False
        patterns = [
            (
                "data_termino",
                r"^\s*(?:Data (?:de )?(?:Rescis[ãa]o|T[ée]rmino)|T[ée]rmino do contrato)\s*:\s*(.+?)\s*$",
            ),
            ("contrato_id", r"^\s*Contrato(?:\s+n[ºo°.]*)?\s*:\s*(.+?)\s*$"),
        ]
        if cargo:
            patterns.append(
                (
                    "inicio_exercicio",
                    r"\bEXERC[IÍ]CIO\s*:?\s*(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})",
                )
            )
        for field, pattern in patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if not match:
                continue
            value = match.group(1)
            if field != "contrato_id":
                parsed = ConversorSaneador.para_data(value)
                if parsed is None:
                    continue
                value = parsed.isoformat()
            if len(candidates) >= 100:
                if not any("100 campos" in warning for warning in warnings):
                    warnings.append(
                        "Extração incompleta: mais de 100 campos de rescisão; confira o documento completo e preencha manualmente."
                    )
                continue
            candidates.append(
                {
                    "campo": field,
                    "valor": value[:200],
                    "localizador": f"Linha {number} do texto extraído",
                }
            )
    # Layout delimitado CACOFERIAS; outros layouts permanecem manuais.
    header = None
    for number, line in enumerate(text.splitlines(), 1):
        cells = [cell.strip() for cell in re.split(r"\s*\|\s*|\s{2,}", line.strip())]
        if len(cells) == 1:
            cells = line.split()
        upper = [cell.upper().replace("Í", "I") for cell in cells]
        if all(label in upper for label in ("INICIO", "DIAS", "PARCELA")):
            header = (upper.index("INICIO"), upper.index("DIAS"))
            continue
        if not header:
            continue
        if "|" not in line:
            row = re.search(
                r"\b(\d{2}[A-Za-zÇç]{3}\d{4}|\d{2}/\d{2}/\d{4})\s+(\d{1,3})\s+(\d{1,2})\s*$",
                line,
            )
            if row is None:
                continue
            raw, days = row.group(1), row.group(2)
        else:
            if len(cells) <= max(header):
                continue
            raw, days = cells[header[0]], cells[header[1]]
        match = re.fullmatch(r"(\d{2})([A-Za-zÇç]{3})(\d{4})", raw)
        if match and match.group(2).upper() in MESES:
            raw = (
                f"{match.group(1)}/{MESES[match.group(2).upper()]:02}/{match.group(3)}"
            )
        parsed = ConversorSaneador.para_data(raw)
        if parsed and days.isdigit() and 1 <= int(days) <= 366:
            if len(candidates) + 2 > 100:
                warnings.append(
                    "Extração incompleta: limite de 100 campos de férias; confira as parcelas restantes manualmente."
                )
                break
            candidates.extend(
                [
                    {
                        "campo": "inicio_ferias",
                        "valor": parsed.isoformat(),
                        "localizador": f"Linha {number}, coluna INICIO",
                    },
                    {
                        "campo": "dias_ferias",
                        "valor": days,
                        "localizador": f"Linha {number}, coluna DIAS",
                    },
                ]
            )
    for code in ("00742", "00750", "00772", "82696", "82407"):
        for row_index, row in enumerate(ficha.get("rubricas", {}).get(code, []), 1):
            for col, value in enumerate(row.get("celulas", [])):
                labels = row.get("meses", [])
                label = labels[col].upper().strip() if col < len(labels) else ""
                if label in ("TOTAL", "TOTAIS") or (
                    value is None and col not in row.get("celulas_invalidas", [])
                ):
                    continue
                if len(payments) >= 200:
                    warnings.append(
                        "Extração incompleta: mais de 200 pagamentos observados; confira todas as fichas e preencha os restantes manualmente."
                    )
                    return {
                        "candidatos": candidates,
                        "pagamentos_observados": payments,
                    }, warnings
                month = MESES.get(label[:3])
                amount = str(value) if value is not None else None
                payments.append(
                    {
                        "competencia": f"{row['ano']:04}-{month:02}"
                        if month and row.get("ano")
                        else None,
                        "rubrica": code,
                        "natureza_rubrica": row.get("natureza")
                        if row.get("natureza") in ("R", "D")
                        else None,
                        "sequencia": str(row.get("sequencia", "")),
                        "valor_observado": amount
                        if amount
                        and re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", amount)
                        and len(amount) <= 60
                        else None,
                        "localizador": f"Rubrica {code}, registro {row_index}, coluna {col + 1} ({label[:40]})",
                    }
                )
    return {"candidatos": candidates, "pagamentos_observados": payments}, warnings
