"""Formulário CACOFERIAS: parcelas e seus estados, sem presumir gozo."""

import re
from datetime import timedelta

from app.services.leitores_pdf.base import data_documental
from app.services.leitores_pdf.comuns import Evidencias, identidade_rotulada, normalizar

DATE = r"\d{2}[A-Za-zÇç]{3}\d{4}|\d{2}/\d{2}/\d{4}"


def ler(pages):
    evidence = Evidencias(pages, "CACOFERIAS")
    for page in pages:
        if page.get("ignorar"):
            continue
        number, text = page["numero"], page.get("texto_original", page["texto"])
        block = evidence.bloco(number)
        identidade_rotulada(evidence, block, text, number)
        exercise = re.search(r"EXERC[IÍ]CIO\s*:\s*(\d{4})\b", text, re.IGNORECASE)
        if exercise:
            evidence.campo(block, "exercicio_ferias", exercise[1], number)
        starts = list(re.finditer(r"\bPARCELA\s*:\s*(\d+)\b", text, re.IGNORECASE))
        for index, match in enumerate(starts):
            body = text[
                match.end() : starts[index + 1].start()
                if index + 1 < len(starts)
                else len(text)
            ]
            period = re.search(rf"({DATE})\s*A\s*({DATE})", body, re.IGNORECASE)
            duration = re.search(r"QTDE\s*DE\s*DIAS\s*:\s*(\d+)\b", body, re.IGNORECASE)
            raw_start, raw_end = period.groups() if period else (None, None)
            start = data_documental(raw_start) if raw_start else None
            end = data_documental(raw_end) if raw_end else None
            days = duration[1] if duration else None
            computed = None
            if start and days and 1 <= int(days) <= 366:
                try:
                    computed = start + timedelta(days=int(days) - 1)
                except OverflowError:
                    pass
            canceled = re.search(
                r"PARCELA\s*CANCELADA\s*:\s*(SIM|NAO|NÃO)\b", body, re.IGNORECASE
            )
            continuation = bool(
                re.search(
                    r"PARCELA\s*DE\s*CONTINUA[CÇ][AÃ]O\s*POR\s*INTERRUP[CÇ][AÃ]O",
                    body,
                    re.IGNORECASE,
                )
            )
            interrupted = re.search(
                rf"DT\s*DE\s*INTERRUP[CÇ][AÃ]O\s*:\s*({DATE})", body, re.IGNORECASE
            )
            restart = re.search(
                rf"DT\s*INICIO\s*DAS\s*FERIAS\s*INTERROMPIDA\s*:\s*({DATE})",
                body,
                re.IGNORECASE,
            )
            remaining = re.search(
                r"DIAS\s*RESTANTES\s*:\s*(\d+)\b", body, re.IGNORECASE
            )
            stop = data_documental(interrupted[1]) if interrupted else None
            resume = data_documental(restart[1]) if restart else None
            state = (
                "EXTRAIDO"
                if start and end and computed == end
                else "AMBIGUO"
                if start and computed and end
                else "ILEGIVEL"
            )
            if interrupted or continuation or not canceled:
                state = "AMBIGUO" if state == "EXTRAIDO" else state
            evidence.campo(
                block,
                "periodo_ferias",
                days,
                number,
                raw=body[:300],
                state=state,
                parcela=match[1],
                inicio=start.isoformat() if start else None,
                fim=end.isoformat() if state == "EXTRAIDO" else None,
                fim_informado=end.isoformat() if end else None,
                fim_calculado=computed.isoformat() if computed else None,
                dias_informados=days,
                cancelada=normalizar(canceled[1]) == "SIM" if canceled else None,
                continuacao=continuation,
                data_interrupcao=stop.isoformat() if stop else None,
                reinicio=resume.isoformat() if resume else None,
                dias_restantes=remaining[1] if remaining else None,
            )
        if not starts:
            evidence.doc["avisos"].append(
                f"Página {number}: parcelas não reconhecidas; complete manualmente."
            )
    return evidence.finalizar(
        "cacoferias_formulario",
        ("nome", "matricula", "exercicio_ferias", "periodo_ferias"),
    )
