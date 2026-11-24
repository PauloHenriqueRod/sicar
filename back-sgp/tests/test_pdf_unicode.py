"""Regressoes da exportacao de nomes e pontuacao fora do Latin-1."""

from pathlib import Path

import pdfplumber
import pytest

from app.services.gerador_pdf import GeradorPDF, UnsupportedPDFCharacterError


@pytest.fixture
def pdf_directory(tmp_path, monkeypatch):
    """Isola todos os arquivos gerados, inclusive em caso de falha."""
    import tempfile

    original = tempfile.mkstemp

    def create_local(*args, **kwargs):
        kwargs["dir"] = tmp_path
        return original(*args, **kwargs)

    monkeypatch.setattr("app.services.gerador_pdf.tempfile.mkstemp", create_local)
    return tmp_path


def read_report(path):
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def test_relatorio_preserva_unicode_em_nomes_rotulos_e_valores(pdf_directory):
    name = "João Łukasz Ștefan Đặng"
    reason = "Férias — período ‘não gozado’, conforme “Portaria nº 123/2026”."
    path = GeradorPDF.gerar_relatorio(
        "rescisao",
        {"matricula": "1234567", "nome": name, "observação_—_base": reason},
        {"detalhamento": [{"descrição": reason, "total_geral": 1234.56}]},
    )
    text = read_report(path)
    assert name in text
    assert text.count(reason) == 2
    assert "Observação — base" in text
    assert "R$ 1234.56" in text
    assert "República Federativa do Brasil" in text
    assert "�" not in text


def test_relatorio_carrega_fontes_fora_do_diretorio_do_projeto(pdf_directory, monkeypatch):
    monkeypatch.chdir(pdf_directory)
    path = GeradorPDF.gerar_relatorio("abono", {"nome": "José — Łukasz"}, {})
    assert "José — Łukasz" in read_report(path)
    assert Path(path).is_file()


def test_relatorio_unicode_multipagina_nao_perde_registros(pdf_directory):
    rows = [
        {"competência": f"MÊS-{index:03}", "observação": f"REFERÊNCIA-{index:03} — ação concluída"}
        for index in range(40)
    ]
    path = GeradorPDF.gerar_relatorio("progressao", {}, {"competências": rows})
    with pdfplumber.open(path) as pdf:
        assert len(pdf.pages) > 1
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        for index in range(40):
            assert f"MÊS-{index:03}" in text
            assert f"REFERÊNCIA-{index:03} — ação concluída" in text
        assert all("Documento gerado eletronicamente" in (page.extract_text() or "") for page in pdf.pages)


def test_caractere_sem_glifo_nao_e_omitido_silenciosamente(pdf_directory):
    with pytest.raises(UnsupportedPDFCharacterError, match="U\\+738B"):
        GeradorPDF.gerar_relatorio("abono", {"nome": "João 王"}, {})
    assert not list(pdf_directory.glob("*.pdf"))


@pytest.mark.parametrize("amount, expected", [
    (2.675, "2.68"),
    (-2.675, "-2.68"),
    (2.685, "2.69"),
    (1234567890123456789012345678901234567890, "1234567890123456789012345678901234567890.00"),
])
def test_relatorio_apresenta_dinheiro_com_half_up_sem_alterar_valores(amount, expected, pdf_directory):
    result = {"valor_base": amount, "dias_proporcionais": 2.675, "confirmado": True}
    original = result.copy()
    path = GeradorPDF.gerar_relatorio("abono", {"matricula": "DEMO-123"}, result)
    text = read_report(path)
    assert f"R$ {expected}" in text
    assert "Dias proporcionais\n2.675" in text
    assert "Confirmado\nTrue" in text
    assert result == original
