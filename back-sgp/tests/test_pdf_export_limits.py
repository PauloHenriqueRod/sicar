"""Orçamento e encerramento da geração de relatórios com dados sintéticos."""
import json
import subprocess
from pathlib import Path
from threading import BoundedSemaphore

import pdfplumber
import pytest
from fastapi import HTTPException

from app.services import pdf_export
from app.services.pdf_report_limits import (
    MAX_REPORT_DEPTH, MAX_REPORT_NODES, MAX_REPORT_STRING_CHARS,
    UnsupportedPDFCharacterError,
)


@pytest.fixture
def export_directory(tmp_path, monkeypatch):
    original = pdf_export.tempfile.mkstemp

    def create_local(*args, **kwargs):
        kwargs["dir"] = tmp_path
        return original(*args, **kwargs)

    monkeypatch.setattr(pdf_export.tempfile, "mkstemp", create_local)
    monkeypatch.setattr(pdf_export, "_slots", BoundedSemaphore(2))
    return tmp_path


def test_exportacao_real_preserva_unicode_e_roda_fora_da_api(export_directory, monkeypatch):
    def forbid_local(*args, **kwargs):
        pytest.fail("O gerador não deve executar no processo da API.")

    monkeypatch.setattr("app.services.gerador_pdf.GeradorPDF.gerar_relatorio", forbid_local)
    rows = [{"competência": f"MÊS-{index:03}", "total": index + 0.5} for index in range(35)]
    path = pdf_export.generate_pdf_report(
        "progressao", {"matricula": "DEMO-123", "nome": "João Łukasz — revisão"},
        {"detalhamento": rows},
    )
    with pdfplumber.open(path) as pdf:
        assert len(pdf.pages) > 1
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "João Łukasz — revisão" in text
    assert all(f"MÊS-{index:03}" in text for index in range(35))
    assert "R$ 34.50" in text
    assert Path(path).parent == export_directory


def test_exportacao_real_interrompe_relatorio_acima_de_cem_paginas(export_directory):
    # Cabe no orçamento JSON, mas produziria mais de 100 páginas se não houvesse teto.
    result = {f"campo_{index}": 1.0 for index in range(2400)}
    with pytest.raises(HTTPException) as error:
        pdf_export.generate_pdf_report("abono", {}, result)
    assert error.value.status_code == 413
    assert "páginas" in error.value.detail
    assert not list(export_directory.glob("*.pdf"))


def test_exportacao_real_timeout_remove_arquivo_parcial(export_directory, monkeypatch):
    original_worker = pdf_export._worker
    worker = export_directory / "slow_report.py"
    marker = export_directory / "generator_started.txt"
    worker.write_text(
        "import runpy, sys, time\nfrom pathlib import Path\n"
        f"sys.path.insert(0, {str(original_worker.resolve().parents[2])!r})\n"
        "from app.services.gerador_pdf import GeradorPDF\n"
        "def slow(*args, output_path, **kwargs):\n"
        f"    Path({str(marker)!r}).write_text('started')\n"
        "    Path(output_path).write_bytes(b'%PDF-partial')\n"
        "    time.sleep(30)\n"
        "GeradorPDF.gerar_relatorio = slow\n"
        f"runpy.run_path({str(original_worker)!r}, run_name='__main__')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pdf_export, "_worker", worker)
    monkeypatch.setattr(pdf_export, "PDF_EXPORT_TIMEOUT_SECONDS", 5)
    with pytest.raises(HTTPException) as error:
        pdf_export.generate_pdf_report("abono", {}, {})
    assert error.value.status_code == 422
    assert "tempo" in error.value.detail
    assert marker.read_text() == "started"
    assert not list(export_directory.glob("*.pdf"))
    # Após o encerramento do processo, as duas vagas continuam disponíveis.
    assert pdf_export._slots.acquire(blocking=False)
    assert pdf_export._slots.acquire(blocking=False)
    pdf_export._slots.release()
    pdf_export._slots.release()


def test_exportacao_timeout_libera_vagas_e_nao_envia_segredos(export_directory, monkeypatch):
    worker = export_directory / "wait.py"
    worker.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    monkeypatch.setattr(pdf_export, "_worker", worker)
    monkeypatch.setattr(pdf_export, "PDF_EXPORT_TIMEOUT_SECONDS", 0.2)
    original_run = subprocess.run
    environments = []

    def spy(*args, **kwargs):
        environments.append(kwargs["env"])
        assert args[0][1:4] == ["-I", "-X", "utf8"]
        return original_run(*args, **kwargs)

    monkeypatch.setattr(pdf_export.subprocess, "run", spy)
    for _ in range(3):
        with pytest.raises(HTTPException) as error:
            pdf_export.generate_pdf_report("abono", {}, {})
        assert error.value.status_code == 422
    assert len(environments) == 3
    for environment in environments:
        assert not {"SECRET_KEY", "DATABASE_URL", "ENCRYPTION_KEY", "ADMIN_INITIAL_PASSWORD"} & environment.keys()
    assert not list(export_directory.glob("*.pdf"))


def test_exportacao_ocupada_nao_inicia_processo(export_directory, monkeypatch):
    monkeypatch.setattr(pdf_export, "_slots", BoundedSemaphore(0))
    monkeypatch.setattr(pdf_export.subprocess, "run", lambda *a, **k: pytest.fail("Não deve iniciar processo."))
    with pytest.raises(HTTPException) as error:
        pdf_export.generate_pdf_report("abono", {}, {})
    assert error.value.status_code == 503
    assert not list(export_directory.glob("*.pdf"))


@pytest.mark.parametrize("result", [
    {"texto": "x" * (MAX_REPORT_STRING_CHARS + 1)},
    {"itens": [None] * MAX_REPORT_NODES},
    {"texto_total": ["x" * 4000] * 26},
    {"utf8": ["王" * 4000] * 24},
])
def test_exportacao_recusa_excesso_de_dados_antes_de_iniciar_processo(result, export_directory, monkeypatch):
    monkeypatch.setattr(pdf_export.subprocess, "run", lambda *a, **k: pytest.fail("Não deve iniciar processo."))
    with pytest.raises(HTTPException) as error:
        pdf_export.generate_pdf_report("abono", {}, result)
    assert error.value.status_code == 413
    assert not list(export_directory.glob("*.pdf"))


def test_exportacao_recusa_aninhamento_excessivo(export_directory, monkeypatch):
    nested = {}
    for _ in range(MAX_REPORT_DEPTH + 1):
        nested = {"nivel": nested}
    monkeypatch.setattr(pdf_export.subprocess, "run", lambda *a, **k: pytest.fail("Não deve iniciar processo."))
    with pytest.raises(HTTPException) as error:
        pdf_export.generate_pdf_report("abono", {}, nested)
    assert error.value.status_code == 413


@pytest.mark.parametrize("result", [{"total": float("inf")}, {"total": object()}, {1: "chave inválida"}])
def test_exportacao_recusa_dados_incompativeis_sem_erro_interno(result, export_directory):
    with pytest.raises(HTTPException) as error:
        pdf_export.generate_pdf_report("abono", {}, result)
    assert error.value.status_code == 422
    assert not list(export_directory.glob("*.pdf"))


@pytest.mark.parametrize("status, expected", [("unavailable", 503), ("limit", 413), ("invalid", 422)])
def test_exportacao_remove_parciais_quando_worker_falha(status, expected, export_directory, monkeypatch):
    def failed(command, **kwargs):
        Path(command[-1]).write_bytes(b"%PDF-partial")
        return subprocess.CompletedProcess(command, 0, json.dumps({"status": status}).encode())

    monkeypatch.setattr(pdf_export.subprocess, "run", failed)
    with pytest.raises(HTTPException) as error:
        pdf_export.generate_pdf_report("abono", {}, {})
    assert error.value.status_code == expected
    assert not list(export_directory.glob("*.pdf"))


def test_exportacao_real_caractere_sem_fonte_nao_produz_documento_incompleto(export_directory):
    with pytest.raises(UnsupportedPDFCharacterError, match="U\\+738B"):
        pdf_export.generate_pdf_report("abono", {"nome": "João 王"}, {})
    assert not list(export_directory.glob("*.pdf"))
