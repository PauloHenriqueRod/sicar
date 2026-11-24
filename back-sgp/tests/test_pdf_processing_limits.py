"""PDFs sintéticos atravessam o leitor e a interpretação no subprocesso real."""
from pathlib import Path

import pytest
from fastapi import HTTPException
from fpdf import FPDF

from app.services import dados_pdf, pdf_extraction


def write_pdf(path: Path, lines: list[str]) -> Path:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for index, line in enumerate(lines):
        # text não quebra a sequência adversarial em várias linhas.
        pdf.text(10, 15 + index * 8, line)
    pdf.output(str(path))
    return path


def test_upload_real_interpreta_sem_executar_parser_na_api(auth_client_user, monkeypatch, tmp_path):
    path = write_pdf(tmp_path / "substituicao.pdf", [
        "Nome: Servidor Sintetico", "Matricula: 1234567", "Mes: 4", "Ano: 2026",
        "Salario Substituta: R$ 5000,00", "Salario Propria: R$ 3000,00", "Dias Substituidos: 10",
    ])

    def forbidden_in_web_process(*args, **kwargs):
        raise AssertionError("Interpretacao nao deve executar no processo web")

    monkeypatch.setattr(dados_pdf, "extract_calculation_data", forbidden_in_web_process)
    with path.open("rb") as document:
        response = auth_client_user.post("/api/extrair-pdf", data={"tipo_calculo": "substituicao"},
                                        files={"arquivos": ("substituicao.pdf", document, "application/pdf")})
    assert response.status_code == 200
    data = response.json()["resultados"][0]["dados_extraidos"]
    assert data["salario_substituta"] == 5000
    assert data["salario_propria"] == 3000
    assert data["dias_substituidos"] == 10


def test_timeout_tambem_encerra_interpretacao_do_texto(monkeypatch, tmp_path):
    path = write_pdf(tmp_path / "normal.pdf", ["Nome: Sintetico"])
    real_worker = pdf_extraction._worker
    marker = tmp_path / "interpretacao-iniciada"
    wrapper = tmp_path / "slow_parser_worker.py"
    wrapper.write_text(
        "import runpy, sys, time\n"
        f"sys.path.insert(0, {str(real_worker.parents[2])!r})\n"
        "from app.services import dados_pdf\n"
        "from pathlib import Path\n"
        "def slow(*args):\n"
        f"    Path({str(marker)!r}).write_text('iniciada')\n"
        "    time.sleep(30)\n"
        "dados_pdf.extract_calculation_data = slow\n"
        f"runpy.run_path({str(real_worker)!r}, run_name='__main__')\n", encoding="utf-8",
    )
    monkeypatch.setattr(pdf_extraction, "_worker", wrapper)
    monkeypatch.setattr(pdf_extraction, "PDF_TIMEOUT_SECONDS", 5)
    with pytest.raises(HTTPException) as exc:
        pdf_extraction.extract_pdf_data(str(path), "substituicao")
    assert marker.is_file(), "O teste deve atingir a interpretação após ler o PDF."
    assert exc.value.status_code == 422
    assert "tempo" in exc.value.detail


def test_pdf_real_com_linha_numerica_longa_tem_resposta_limitada(tmp_path):
    path = write_pdf(tmp_path / "numeros.pdf", [
        "Ficha Financeira referente a: 2026", "Rubrica|Nome Rubrica|R/D|Seq.|JAN",
        "00001|VENCIMENTO BASICO|R|1|" + "7" * 40_000,
    ])
    # O mesmo subprocesso impõe o teto de tempo à leitura e ao parser de rubricas.
    # A entrada inválida pode ser descartada pelo parser ou rejeitada explicitamente.
    try:
        data = pdf_extraction.extract_pdf_data(str(path), "substituicao")
    except HTTPException as exc:
        assert exc.status_code in (413, 422)
        assert "tempo" not in exc.detail, "A linha malformada deve ser tratada sem consumir o timeout."
    else:
        assert "vencimento_basico" not in data
