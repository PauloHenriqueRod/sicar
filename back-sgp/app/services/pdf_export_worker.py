"""Gera um único relatório em processo descartável com memória limitada."""
import json
import sys
from pathlib import Path


def main():
    # -I ignora configurações de import externas. Somente a raiz conhecida é incluída.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.services.pdf_worker import limit_memory

    try:
        limit_memory()
    except Exception:
        print(json.dumps({"status": "unavailable"}))
        return
    from app.services.pdf_report_limits import (
        MAX_REPORT_PAYLOAD_BYTES, PDFReportLimitError, UnsupportedPDFCharacterError,
    )
    try:
        from app.services.gerador_pdf import GeradorPDF

        raw = sys.stdin.buffer.read(MAX_REPORT_PAYLOAD_BYTES + 1)
        if len(raw) > MAX_REPORT_PAYLOAD_BYTES:
            raise PDFReportLimitError()
        payload = json.loads(raw)
        GeradorPDF.gerar_relatorio(**payload, output_path=sys.argv[1])
        print(json.dumps({"status": "ok"}))
    except (MemoryError, PDFReportLimitError):
        print(json.dumps({"status": "limit"}))
    except UnsupportedPDFCharacterError as exc:
        # A exceção contém somente códigos Unicode, sem reproduzir dados de RH.
        print(json.dumps({"status": "unsupported", "detail": str(exc)}))
    except Exception:
        print(json.dumps({"status": "invalid"}))


if __name__ == "__main__":
    main()
