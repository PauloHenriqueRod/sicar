"""Orçamento de um relatório, independente dos limites de upload e extração."""
import json
import math
from typing import Any

MAX_REPORT_PAGES = 100
MAX_REPORT_FILE_BYTES = 5 * 1024 * 1024
MAX_REPORT_PAYLOAD_BYTES = 256 * 1024
MAX_REPORT_NODES = 10_000
MAX_REPORT_DEPTH = 8
MAX_REPORT_STRING_CHARS = 4096
MAX_REPORT_TOTAL_CHARS = 100_000


class PDFReportLimitError(ValueError):
    """Relatório maior ou mais complexo que o orçamento admitido."""


class UnsupportedPDFCharacterError(ValueError):
    """Impede que um relatório oficial omita caracteres sem glifos."""


def encode_report_payload(tipo_calculo: str, dados_extraidos: dict[str, Any],
                          resultado_calculo: dict[str, Any]) -> bytes:
    payload = {"tipo_calculo": tipo_calculo, "dados_extraidos": dados_extraidos,
               "resultado_calculo": resultado_calculo}
    stack: list[tuple[Any, int]] = [(payload, 0)]
    nodes, characters = 0, 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_REPORT_NODES or depth > MAX_REPORT_DEPTH:
            raise PDFReportLimitError("O relatório excede o limite de campos ou de profundidade.")
        if isinstance(item, dict):
            if nodes + len(stack) + 2 * len(item) > MAX_REPORT_NODES:
                raise PDFReportLimitError("O relatório excede o limite de campos.")
            for key, value in item.items():
                if not isinstance(key, str):
                    raise ValueError("Chave de relatório inválida.")  # noqa: TRY004
                stack.append((key, depth + 1))
                stack.append((value, depth + 1))
        elif isinstance(item, list):
            if nodes + len(stack) + len(item) > MAX_REPORT_NODES:
                raise PDFReportLimitError("O relatório excede o limite de campos.")
            stack.extend((value, depth + 1) for value in item)
        elif isinstance(item, str):
            characters += len(item)
            if len(item) > MAX_REPORT_STRING_CHARS or characters > MAX_REPORT_TOTAL_CHARS:
                raise PDFReportLimitError("O relatório excede o limite de texto.")
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("Valor não finito no relatório.")
        elif item is not None and not isinstance(item, (bool, int)):
            raise ValueError("Tipo de valor inválido no relatório.")
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_REPORT_PAYLOAD_BYTES:
        raise PDFReportLimitError("O relatório excede o limite de dados.")
    return encoded
