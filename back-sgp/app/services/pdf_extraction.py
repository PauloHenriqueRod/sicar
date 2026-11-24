import json
import os
import subprocess
import sys
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any

from fastapi import HTTPException

PDF_TIMEOUT_SECONDS = 15
_slots = BoundedSemaphore(2)
_worker = Path(__file__).with_name("pdf_worker.py")


def _read_pdf(path: str, tipo_calculo: str | None = None) -> dict[str, Any]:
    if not _slots.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="Leitura de documentos ocupada. Tente novamente.")
    try:
        # Não repassa chaves, senhas, URL do banco ou configuração de imports ao leitor.
        environment = {key: value for key, value in os.environ.items()
                       if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL"}}
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-X", "utf8", str(_worker), path, *([tipo_calculo] if tipo_calculo else [])],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=environment, timeout=PDF_TIMEOUT_SECONDS, check=False,
            )
        except subprocess.TimeoutExpired:
            # subprocess.run encerra e aguarda o filho antes de retornar.
            raise HTTPException(status_code=422, detail="O PDF excedeu o tempo de leitura permitido. Divida o documento.")
        if result.returncode:
            raise HTTPException(status_code=422, detail="O PDF não pôde ser lido dentro dos limites permitidos.")
        payload = json.loads(result.stdout)
        if payload["status"] == "limit":
            raise HTTPException(status_code=413, detail="O PDF excede o limite de páginas, texto ou memória.")
        if payload["status"] == "unavailable":
            raise HTTPException(status_code=503, detail="Leitor de documentos indisponível.")
        if payload["status"] != "ok":
            raise HTTPException(status_code=422, detail="Não foi possível ler o PDF enviado.")
        return payload
    finally:
        _slots.release()


def extract_pdf_text(path: str) -> str:
    """Leitura simples usada por ferramentas e verificações do leitor."""
    return _read_pdf(path)["text"]


def extract_pdf_data(path: str, tipo_calculo: str) -> dict[str, Any]:
    """Texto e interpretação compartilham o mesmo timeout e limite de memória."""
    return _read_pdf(path, tipo_calculo)["data"]
