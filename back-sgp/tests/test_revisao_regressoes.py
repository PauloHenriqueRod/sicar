import os
import tempfile
from unittest.mock import MagicMock, patch

import pdfplumber
import pytest

from app.models.tabelas_salariais import (
    HistoricoCalculo,
)
from app.services.dados_pdf import extract_calculation_data
from app.services.gerador_pdf import GeradorPDF, RelatorioOficialPDF
from app.services.motor_calculos_rh import MotorCalculosRH


def test_exercicio_anterior_extracao_calculo_e_historico(auth_client_user):
    page = MagicMock()
    page.extract_text.return_value = "Periodo: 01/2025 | Devido: R$ 2.000,00 | Recebido: R$ 1.000,00 | Abono: R$ 200,00 | 13o: R$ 300,00"
    with patch("app.routers.calculos_router.extract_pdf_data") as mock_open:
        mock_open.side_effect = lambda path, tipo: extract_calculation_data(page.extract_text.return_value, tipo)
        extracted = auth_client_user.post("/api/extrair-pdf", data={"tipo_calculo": "exercicio_anterior"}, files={"arquivos": ("demo.pdf", b"%PDF-1.4\n", "application/pdf")})
    assert extracted.status_code == 200
    dados = extracted.json()["resultados"][0]["dados_extraidos"]
    assert dados["fluxo_mensal"][0]["ab_ferias"] == 200
    assert dados["fluxo_mensal"][0]["13_sal"] == 300
    response = auth_client_user.post("/api/calcular", json={"tipo_calculo": "exercicio_anterior", "dados_extraidos": dados})
    assert response.status_code == 200
    resultado = response.json()["resultado_calculo"]
    assert resultado["resumo_consolidado"]["total_geral_a_receber"] == 1500
    assert resultado["detalhamento_por_competencia"][0]["total_mes"] == 1500
    history = auth_client_user.get("/api/historico").json()
    import json
    assert json.loads(history[0]["resultado_json"]) == resultado


def test_exercicio_anterior_aceita_rascunho_com_chaves_antigas(auth_client_user):
    response = auth_client_user.post("/api/calcular", json={"tipo_calculo": "exercicio_anterior", "dados_extraidos": {"fluxo": [{"periodo": "01/2025", "v_dev": 2000, "v_rec": 1000, "v_abono": 200, "v_13": 300}]}})
    assert response.status_code == 200
    assert response.json()["resultado_calculo"]["resumo_consolidado"]["total_geral_a_receber"] == 1500


@pytest.mark.parametrize("dados", [{}, {"fluxo_mensal": []}, {"fluxo_mensal": [{"periodo": "01/2025", "v_dev": "inválido", "v_rec": 0}]}])
def test_exercicio_anterior_rejeita_fluxo_invalido(auth_client_user, dados):
    assert auth_client_user.post("/api/calcular", json={"tipo_calculo": "exercicio_anterior", "dados_extraidos": dados}).status_code == 400


@pytest.mark.parametrize("cadastrada, solicitada", [("Especialização", "especializacao"), ("Especializacao", "ESPECIALIZAÇÃO")])
def test_titulacao_normaliza_banco_e_entrada_e_preserva_vigencia(db_session, salary_reference, cadastrada, solicitada):
    salary_reference(inicio_vigencia="2025-01-15", fim_vigencia="2026-01-14", vencimento_basico="4000", retribuicoes=[{"titulacao": cadastrada, "valor": "500"}])
    _, query = salary_reference(fim_vigencia="2027-01-14", vencimento_basico="4000", retribuicoes=[{"titulacao": cadastrada, "valor": "1000"}, {"titulacao": "Mestrado", "valor": "3000"}])
    salary_reference(inicio_vigencia="2027-01-15", vencimento_basico="4000", retribuicoes=[{"titulacao": cadastrada, "valor": "2000"}])
    assert MotorCalculosRH._obter_salario_tabela("Adjunto", 1, solicitada, 2026, referencia=query) == 5000


@pytest.mark.parametrize("invalidos", [
    {"dias_interrupcao": -5}, {"dias_substituidos": -1}, {"dias_interrupcao": 11},
    {"dias_substituidos": 1.5}, {"dias_substituidos": 32}, {"salario_substituta": -1},
    {"salario_propria": "NaN"}, {"salario_substituta": "Infinity"},
])
def test_substituicao_rejeita_valores_invalidos(auth_client_user, invalidos):
    dados = {"salario_substituta": 3100, "salario_propria": 0, "dias_substituidos": 10, "dias_interrupcao": 0, "mes": 1, "ano": 2026, **invalidos}
    assert auth_client_user.post("/api/calcular", json={"tipo_calculo": "substituicao", "dados_extraidos": dados}).status_code == 400


def test_motor_rejeita_interrupcao_negativa_e_respeita_ano_bissexto():
    with pytest.raises(ValueError):
        MotorCalculosRH.calcular_substituicao(3100, 0, 10, -5, 1, 2026)
    assert MotorCalculosRH.calcular_substituicao(2900, 0, 29, 0, 2, 2024)["valor_proporcional_devido"] == 2900
    with pytest.raises(ValueError):
        MotorCalculosRH.calcular_substituicao(2900, 0, 29, 0, 2, 2026)


@pytest.mark.parametrize("falha", ["criptografia", "commit"])
def test_falha_historico_retorna_erro_e_proxima_operacao_funciona(auth_client_user, db_session, falha):
    payload = {"tipo_calculo": "substituicao", "dados_extraidos": {"salario_substituta": 3100, "dias_substituidos": 10, "mes": 1, "ano": 2026}}
    original_commit = db_session.commit
    def commit_with_failure():
        from app.models.user import AuditLog
        if any(isinstance(obj, AuditLog) and obj.action == "CALCULO_SALVO" for obj in db_session.new):
            raise RuntimeError("falha simulada")
        return original_commit()
    target = patch("app.utils.crypto.encrypt_data", side_effect=RuntimeError("falha simulada")) if falha == "criptografia" else patch.object(db_session, "commit", side_effect=commit_with_failure)
    with target:
        response = auth_client_user.post("/api/calcular", json=payload)
    assert response.status_code == 500
    assert "histórico" in response.json()["detail"]
    assert db_session.query(HistoricoCalculo).count() == 0
    assert auth_client_user.post("/api/calcular", json=payload).status_code == 200
    assert db_session.query(HistoricoCalculo).count() == 1


@pytest.fixture
def temporarios_pdf(tmp_path, monkeypatch):
    original = tempfile.mkstemp
    captured = []

    def capture(**kwargs):
        fd, path = original(dir=tmp_path, **kwargs)
        captured.append((fd, path))
        return fd, path

    monkeypatch.setattr("app.services.gerador_pdf.tempfile.mkstemp", capture)
    return captured


def test_pdf_inclui_competencias_e_entradas_aninhadas_e_fecha_descritor(temporarios_pdf):
    path = GeradorPDF.gerar_relatorio("exercicio_anterior", {"fluxo_mensal": [{"periodo": "ENTRADA_01", "v_dev": 2000.0}]}, {"resultado_calculo": {"detalhamento_por_competencia": [{"periodo": "COMPETENCIA_01", "total_mes": 1500.0}], "resumo_consolidado": {"total_geral_a_receber": 1500.0}}})
    try:
        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        assert "ENTRADA_01" in text and "COMPETENCIA_01" in text
        assert "1500.00" in text
        with pytest.raises(OSError):
            os.fstat(temporarios_pdf[0][0])
    finally:
        os.unlink(path)


def test_pdf_falha_geracao_remove_temporario(temporarios_pdf):
    with patch.object(RelatorioOficialPDF, "output", side_effect=RuntimeError("falha simulada")), pytest.raises(RuntimeError):
        GeradorPDF.gerar_relatorio("abono", {}, {})
    assert not os.path.exists(temporarios_pdf[0][1])


def test_pdf_nao_separa_rotulo_do_valor_na_paginacao(temporarios_pdf):
    path = GeradorPDF.gerar_relatorio("abono", {}, {f"marcador_{indice}": f"VALOR-{indice}" for indice in range(50)})
    try:
        with pdfplumber.open(path) as pdf:
            assert len(pdf.pages) > 1
            for pagina in pdf.pages:
                text = pagina.extract_text() or ""
                assert "República Federativa do Brasil" in text
                linhas = text.splitlines()
                for indice in range(50):
                    if f"Marcador {indice}" in linhas:
                        assert f"VALOR-{indice}" in linhas
    finally:
        os.unlink(path)


def test_exportacao_remove_pdf_apos_envio(auth_client_user, temporarios_pdf):
    saved = auth_client_user.post("/api/calcular", json={"tipo_calculo": "abono", "dados_extraidos": {"valores_anuais": {"2026": [1000]}}}).json()
    response = auth_client_user.post("/api/exportar-pdf", json={"historico_id": saved["historico_id"]})
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")
    assert not os.path.exists(temporarios_pdf[0][1])


def test_exportacao_falha_apos_geracao_remove_pdf(auth_client_user, temporarios_pdf):
    saved = auth_client_user.post("/api/calcular", json={"tipo_calculo": "abono", "dados_extraidos": {"valores_anuais": {"2026": [1000]}}}).json()
    with patch("app.routers.auth_router.log_audit", side_effect=RuntimeError("falha simulada")):
        response = auth_client_user.post("/api/exportar-pdf", json={"historico_id": saved["historico_id"]})
    assert response.status_code == 500
    assert not os.path.exists(temporarios_pdf[0][1])
