"""Supervisiona exportações sem executar o gerador no processo da API."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any

from fastapi import HTTPException

from app.services.pdf_report_limits import (
    MAX_REPORT_FILE_BYTES,
    PDFReportLimitError,
    UnsupportedPDFCharacterError,
    encode_report_payload,
)

PDF_EXPORT_TIMEOUT_SECONDS = 15
_slots = BoundedSemaphore(2)
_worker = Path(__file__).with_name("pdf_export_worker.py")


def generate_pdf_report(tipo_calculo: str, dados_extraidos: dict[str, Any],
                        resultado_calculo: dict[str, Any]) -> str:
    if not _slots.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="Exportação de relatórios ocupada. Tente novamente.")
    output_path = None
    completed = False
    try:
        try:
            if resultado_calculo.get("tipo_substituicao") == "periodos_v1":
                from app.services.substitution_report import substitution_report
                dados_extraidos, resultado_calculo = substitution_report(dados_extraidos, resultado_calculo)
            payload = encode_report_payload(tipo_calculo, dados_extraidos, resultado_calculo)
        except PDFReportLimitError:
            raise HTTPException(status_code=413, detail="O relatório excede o limite de dados, texto ou campos. Divida o período.")
        except (ValueError, TypeError, OverflowError):
            raise HTTPException(status_code=422, detail="O histórico contém dados incompatíveis com a exportação.")
        fd, output_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        environment = {key: value for key, value in os.environ.items()
                       if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL"}}
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-X", "utf8", str(_worker), output_path],
                input=payload, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=environment, timeout=PDF_EXPORT_TIMEOUT_SECONDS, check=False,
            )
        except subprocess.TimeoutExpired:
            # run encerra e aguarda o filho, permitindo excluir até arquivos parciais.
            raise HTTPException(status_code=422, detail="O relatório excedeu o tempo de geração permitido. Divida o período.")
        except OSError:
            raise HTTPException(status_code=503, detail="Gerador de relatórios indisponível.")
        if result.returncode or len(result.stdout) > 8192:
            raise HTTPException(status_code=422, detail="O relatório não pôde ser gerado dentro dos limites permitidos.")
        try:
            message = json.loads(result.stdout)
            status = message["status"]
        except (ValueError, TypeError, KeyError):
            raise HTTPException(status_code=503, detail="Gerador de relatórios indisponível.")
        if status == "limit":
            raise HTTPException(status_code=413, detail="O relatório excede o limite de páginas, dados ou memória. Divida o período.")
        if status == "unavailable":
            raise HTTPException(status_code=503, detail="Gerador de relatórios indisponível.")
        if status == "unsupported":
            raise UnsupportedPDFCharacterError(message["detail"])
        if status != "ok":
            raise HTTPException(status_code=422, detail="Não foi possível gerar o relatório deste histórico.")
        path = Path(output_path)
        if not path.is_file() or not 5 < path.stat().st_size <= MAX_REPORT_FILE_BYTES:
            raise HTTPException(status_code=413, detail="O relatório excede o limite de tamanho ou está incompleto.")
        with path.open("rb") as document:
            if document.read(5) != b"%PDF-":
                raise HTTPException(status_code=503, detail="Gerador de relatórios indisponível.")
        completed = True
        return output_path
    finally:
        try:
            if output_path and not completed:
                Path(output_path).unlink(missing_ok=True)
        finally:
            _slots.release()
