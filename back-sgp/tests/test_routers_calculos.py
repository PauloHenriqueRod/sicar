from app.services.dados_pdf import extract_calculation_data
import os
from unittest.mock import MagicMock, patch

import pytest

# Vamos usar os PDFs gerados pelo script na pasta scripts/
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")

@pytest.fixture
def pdf_substituicao(gerador_pdfs_teste):
    path = os.path.join(gerador_pdfs_teste, "pdf_substituicao.pdf")
    with open(path, "rb") as f:
        yield f

@pytest.fixture
def pdf_abono(gerador_pdfs_teste):
    path = os.path.join(gerador_pdfs_teste, "pdf_abono_permanencia.pdf")
    with open(path, "rb") as f:
        yield f

@pytest.fixture
def fake_pdf_bytes():
    """Bytes inválidos para testar validação de magic numbers."""
    return b"%PDF-1.4\nFAKE FILE"

@pytest.fixture
def pdf_progressao(gerador_pdfs_teste):
    path = os.path.join(gerador_pdfs_teste, "progressao_teste_01.pdf")
    with open(path, "rb") as f:
        yield f

class TestCalculosRouter:

    def test_extrair_pdf_substituicao(self, auth_client_user, pdf_substituicao):
        files = {"arquivos": ("teste.pdf", pdf_substituicao, "application/pdf")}
        data = {"tipo_calculo": "substituicao"}
        
        r = auth_client_user.post("/api/extrair-pdf", data=data, files=files)
        assert r.status_code == 200
        json_data = r.json()
        dados = json_data["resultados"][0]["dados_extraidos"]
        assert "salario_substituta" in dados
        assert dados["salario_substituta"] == 8543.21

    def test_extrair_pdf_abono(self, auth_client_user, pdf_abono):
        files = {"arquivos": ("abono.pdf", pdf_abono, "application/pdf")}
        data = {"tipo_calculo": "abono"}
        
        r = auth_client_user.post("/api/extrair-pdf", data=data, files=files)
        assert r.status_code == 200
        json_data = r.json()
        dados = json_data["resultados"][0]["dados_extraidos"]
        assert "valores_anuais" in dados
        assert "2023" in dados["valores_anuais"]
        assert dados["valores_anuais"]["2023"] == [100.50, 200.75, 150.00]

    @patch("app.routers.calculos_router.extract_pdf_data")
    def test_abono_ficha_financeira(self, mock_pdfplumber, auth_client_user, pdf_abono):
        page = MagicMock()
        page.extract_text.return_value = (
            "Ficha Financeira referente a: 2023 - 1º Semestre\n"
            "Rubrica|Nome Rubrica|R/D|Seq.|JAN|FEV\n"
            "98002|CONT. PLANO SEGURIDADE SOCIAL|D|0|751,97|1.000,00\n"
            "Ficha Financeira referente a: 2023 - 2º Semestre\n"
            "Rubrica|Nome Rubrica|R/D|Seq.|JUL\n"
            "98002|CONT. PLANO SEGURIDADE SOCIAL|D|0|800,00\n"
            "Ficha Financeira referente a: 2024 - 1º Semestre\n"
            "Rubrica|Nome Rubrica|R/D|Seq.|JAN\n"
            "98002|CONT. PLANO SEGURIDADE SOCIAL|D|0|900,00"
        )
        mock_pdfplumber.side_effect = lambda path, tipo: extract_calculation_data(page.extract_text.return_value, tipo)
        response = auth_client_user.post(
            "/api/extrair-pdf", data={"tipo_calculo": "abono"},
            files={"arquivos": ("abono.pdf", pdf_abono, "application/pdf")},
        )
        assert response.status_code == 200
        assert response.json()["resultados"][0]["dados_extraidos"]["valores_anuais"] == {
            "2023": [751.97, 1000.0, 800.0], "2024": [900.0],
        }

    def test_extrair_pdf_sem_autenticacao(self, client, pdf_substituicao):
        files = {"arquivos": ("teste.pdf", pdf_substituicao, "application/pdf")}
        r = client.post("/api/extrair-pdf", data={"tipo_calculo": "substituicao"}, files=files)
        assert r.status_code == 401

    def test_extrair_pdf_formato_invalido_extensao(self, auth_client_user):
        files = {"arquivos": ("teste.txt", b"conteudo fake", "text/plain")}
        r = auth_client_user.post("/api/extrair-pdf", data={"tipo_calculo": "substituicao"}, files=files)
        assert r.status_code == 400
        assert "deve ser um PDF" in r.json()["detail"]

    def test_extrair_pdf_magic_numbers_invalidos(self, auth_client_user):
        """Testa se rejeita arquivos que fingem ser PDF (pela extensão) mas não têm magic bytes."""
        files = {"arquivos": ("teste.pdf", b"nao sou um pdf de verdade", "application/pdf")}
        r = auth_client_user.post("/api/extrair-pdf", data={"tipo_calculo": "substituicao"}, files=files)
        assert r.status_code == 400
        assert "não é um PDF autêntico" in r.json()["detail"]

    def test_calcular_substituicao_endpoint(self, auth_client_user):
        payload = {
            "tipo_calculo": "substituicao",
            "dados_extraidos": {
                "salario_substituta": 5000.0,
                "salario_propria": 3000.0,
                "dias_substituidos": 15,
                "mes": 10,
                "ano": 2024
            }
        }
        r = auth_client_user.post("/api/calcular", json=payload)
        assert r.status_code == 200
        assert r.json()["resultado_calculo"]["valor_proporcional_devido"] >= 0

    def test_exportar_pdf_endpoint(self, auth_client_user):
        payload = {
            "tipo_calculo": "substituicao",
            "dados_extraidos": {
                "salario_substituta": 5000.0,
                "salario_propria": 3000.0,
                "dias_substituidos": 15
            }
        }
        payload["dados_extraidos"].update({"mes": 1, "ano": 2026})
        saved = auth_client_user.post("/api/calcular", json=payload)
        assert saved.status_code == 200
        assert saved.json()["resultado_calculo"]["valor_proporcional_devido"] == 967.74
        r = auth_client_user.post("/api/exportar-pdf", json={"historico_id": saved.json()["historico_id"]})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        # Verifica se o PDF retornado começa com o magic number %PDF
        assert r.content.startswith(b"%PDF")

    def test_extrair_pdf_progressao(self, auth_client_user, pdf_progressao):
        files = {"arquivos": ("progressao.pdf", pdf_progressao, "application/pdf")}
        data = {"tipo_calculo": "progressao"}
        
        r = auth_client_user.post("/api/extrair-pdf", data=data, files=files)
        assert r.status_code == 200
        json_data = r.json()
        dados = json_data["resultados"][0]["dados_extraidos"]
        assert "classe_atual" in dados

    def test_listar_historico_acesso_roles(self, auth_client_user, auth_client_admin, auth_client_dev):
        r_admin = auth_client_admin.get("/api/historico")
        assert r_admin.status_code == 200
        assert isinstance(r_admin.json(), list)
        
        r_dev = auth_client_dev.get("/api/historico")
        assert r_dev.status_code == 200
        assert isinstance(r_dev.json(), list)

        r_user = auth_client_user.get("/api/historico")
        assert r_user.status_code == 200
        assert isinstance(r_user.json(), list)

    @patch("app.routers.calculos_router.extract_pdf_data")
    def test_extrair_pdf_mock_insalubridade(self, mock_pdfplumber, auth_client_user, pdf_substituicao):
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Mes: Janeiro | Valor Base: R$ 1000,00"
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.side_effect = lambda path, tipo: extract_calculation_data("".join(page.extract_text() or "" for page in mock_pdf.pages), tipo)

        files = {"arquivos": ("teste.pdf", pdf_substituicao, "application/pdf")}
        data = {"tipo_calculo": "insalubridade"}
        r = auth_client_user.post("/api/extrair-pdf", data=data, files=files)
        
        assert r.status_code == 200
        dados = r.json()["resultados"][0]["dados_extraidos"]
        assert "valores_mensais" in dados
        assert dados["valores_mensais"]["Janeiro"] == 1000.0

    @patch("app.routers.calculos_router.extract_pdf_data")
    def test_extrair_pdf_mock_rescisao(self, mock_pdfplumber, auth_client_user, pdf_substituicao):
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Classe: Adjunto\nNível: 3\nTitulação: Doutorado\nMeses de Férias: 1.5\nMeses 13º: 5\nDias Trabalhados: 10\nRecebido Férias: R$ 500,00"
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.side_effect = lambda path, tipo: extract_calculation_data("".join(page.extract_text() or "" for page in mock_pdf.pages), tipo)

        files = {"arquivos": ("teste.pdf", pdf_substituicao, "application/pdf")}
        data = {"tipo_calculo": "rescisao"}
        r = auth_client_user.post("/api/extrair-pdf", data=data, files=files)
        
        assert r.status_code == 200
        dados = r.json()["resultados"][0]["dados_extraidos"]
        assert dados["classe"] == "Adjunto"
        assert dados["nivel"] == 3
        assert dados["titulacao"] == "Doutorado"
        assert dados["meses_ferias"] == 1.5
        assert dados["meses_13"] == 5
        assert dados["dias_trabalhados"] == 10
        assert dados["valores_recebidos"]["Férias"] == 500.0

    @patch("app.routers.calculos_router.extract_pdf_data")
    def test_extrair_pdf_mock_exercicio_anterior(self, mock_pdfplumber, auth_client_user, pdf_substituicao):
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Periodo: 2022-01 | Devido: R$ 2000,00 | Recebido: R$ 1000,00 | Abono: R$ 0,00 | 13o: R$ 0,00"
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.side_effect = lambda path, tipo: extract_calculation_data("".join(page.extract_text() or "" for page in mock_pdf.pages), tipo)

        files = {"arquivos": ("teste.pdf", pdf_substituicao, "application/pdf")}
        data = {"tipo_calculo": "exercicio_anterior"}
        r = auth_client_user.post("/api/extrair-pdf", data=data, files=files)
        
        assert r.status_code == 200
        dados = r.json()["resultados"][0]["dados_extraidos"]
        assert "fluxo_mensal" in dados
        assert len(dados["fluxo_mensal"]) == 1
        assert dados["fluxo_mensal"][0]["v_dev"] == 2000.0

    @patch("app.routers.calculos_router.extract_pdf_data")
    def test_extrair_pdf_mock_desconhecido(self, mock_pdfplumber, auth_client_user, pdf_substituicao):
        mock_pdf = MagicMock()
        mock_pdfplumber.side_effect = lambda path, tipo: extract_calculation_data("".join(page.extract_text() or "" for page in mock_pdf.pages), tipo)

        files = {"arquivos": ("teste.pdf", pdf_substituicao, "application/pdf")}
        data = {"tipo_calculo": "invalido_xpto"}
        r = auth_client_user.post("/api/extrair-pdf", data=data, files=files)
        
        assert r.status_code == 400
        assert "desconhecido" in r.json()["detail"]

    @patch("app.routers.calculos_router.extract_pdf_data")
    def test_extrair_pdf_erro_leitura(self, mock_pdfplumber, auth_client_user, pdf_substituicao):
        mock_pdfplumber.side_effect = Exception("Erro forçado")

        files = {"arquivos": ("teste.pdf", pdf_substituicao, "application/pdf")}
        data = {"tipo_calculo": "substituicao"}
        r = auth_client_user.post("/api/extrair-pdf", data=data, files=files)
        
        assert r.status_code == 500
        assert "Erro ao processar PDF" in r.json()["detail"]

    def test_extrair_pdf_arquivo_muito_grande(self, auth_client_user, pdf_substituicao):
        import io
        big_content = b"%PDF-1.4\n" + (b"A" * (6 * 1024 * 1024))
        files = {"arquivos": ("teste_grande.pdf", io.BytesIO(big_content), "application/pdf")}
        data = {"tipo_calculo": "substituicao"}
        r = auth_client_user.post("/api/extrair-pdf", data=data, files=files)
        assert r.status_code == 413
        assert "muito grande" in r.json()["detail"]

    def test_calcular_endpoint_insalubridade(self, auth_client_user):
        payload = {
            "tipo_calculo": "insalubridade",
            "dados_extraidos": {
                "valores_mensais": {"Janeiro": 1000.0}
            }
        }
        r = auth_client_user.post("/api/calcular", json=payload)
        assert r.status_code == 200
        assert "resultado_calculo" in r.json()

    def test_calcular_endpoint_rescisao(self, auth_client_user, db_session, salary_reference):
        _, query = salary_reference(inicio_vigencia="2024-04-01", vencimento_basico="4000", retribuicoes=[{"titulacao": "Mestrado", "valor": "1000"}])
        db_session.commit()
        payload = {
            "tipo_calculo": "rescisao",
            "dados_extraidos": {
                "classe": "Adjunto", "nivel": 1, "titulacao": "Mestrado",
                "meses_ferias": 1, "meses_13": 5, "dias_trabalhados": 20,
                "valores_recebidos": {}, "mes_rescisao": 12, "ano_rescisao": 2024, "referencia_salarial": query.model_dump(mode="json"),
            }
        }
        r = auth_client_user.post("/api/calcular", json=payload)
        assert r.status_code == 200, f"ERRO: {r.json()}"

    def test_calcular_endpoint_progressao(self, auth_client_user, db_session, salary_reference):
        _, old = salary_reference(inicio_vigencia="2024-04-01", vencimento_basico="4100", retribuicoes=[{"titulacao": "Doutorado", "valor": "1000"}])
        _, new = salary_reference(inicio_vigencia="2024-04-01", nivel_docente=2, vencimento_basico="4200", retribuicoes=[{"titulacao": "Doutorado", "valor": "1000"}])
        db_session.commit()
        payload = {
            "tipo_calculo": "progressao",
            "dados_extraidos": {
                "classe_atual": "Adjunto", "nivel_atual": 2, "titulacao": "Doutorado",
                "classe_antiga": "Adjunto", "nivel_antigo": 1, "referencia_antiga": old.model_dump(mode="json"), "referencia_nova": new.model_dump(mode="json"),
                "anuenio": 5.0, "insalubridade": 0, "meses_diferenca": 12, "ano_proporcao": 2024,
            }
        }
        r = auth_client_user.post("/api/calcular", json=payload)
        assert r.status_code == 200

    def test_calcular_progressao_tae_repassa_iq_dias_e_reflexos(self, auth_client_user):
        payload = {
            "tipo_calculo": "progressao",
            "dados_extraidos": {
                "classe_atual": "D", "nivel_atual": 7, "titulacao": "N/A",
                "classe_antiga": "D", "nivel_antigo": 6,
                "salario_antigo": 3686.33, "salario_novo": 3833.79,
                "anuenio": 0, "insalubridade": 0, "incentivo": 30,
                "meses_diferenca": 0, "dias_proporcionais": 14,
                "mes_proporcao": 1, "ano_proporcao": 2026,
                "quantidade_reflexos_ferias": 1,
                "quantidade_reflexos_13": 1,
            },
        }
        r = auth_client_user.post("/api/calcular", json=payload)
        assert r.status_code == 200
        resultado = r.json()["resultado_calculo"]
        assert resultado["total_geral_devido"] == 86.57
        assert resultado["reflexo_ferias"] == 63.90
        assert resultado["reflexo_decimo_terceiro"] == 191.70

    def test_calcular_endpoint_exercicio_anterior(self, auth_client_user):
        payload = {
            "tipo_calculo": "exercicio_anterior",
            "dados_extraidos": {
                "fluxo_mensal": [
                    {"periodo": "2023-01", "v_dev": 2000, "v_rec": 1000, "ab_ferias": 0, "13_sal": 0}
                ]
            }
        }
        r = auth_client_user.post("/api/calcular", json=payload)
        assert r.status_code == 200

    def test_calcular_endpoint_desconhecido(self, auth_client_user):
        payload = {
            "tipo_calculo": "invalido_xpto",
            "dados_extraidos": {}
        }
        r = auth_client_user.post("/api/calcular", json=payload)
        assert r.status_code == 400
        assert "desconhecido" in r.json()["detail"]

    def test_calcular_erro_generico(self, auth_client_user):
        payload = {
            "tipo_calculo": "substituicao",
            "dados_extraidos": {
                "salario_substituta": "isso_nao_pode_virar_float"
            }
        }
        r = auth_client_user.post("/api/calcular", json=payload)
        assert r.status_code == 400
        erros = r.json()["detail"]
        assert any(erro["loc"] == ["dados_extraidos", "salario_substituta"] for erro in erros)
        assert all("input" not in erro for erro in erros)
        assert "isso_nao_pode_virar_float" not in r.text

    @patch("app.routers.calculos_router.HistoricoCalculo")
    def test_calcular_erro_salvar_historico(self, mock_historico, auth_client_user):
        mock_historico.side_effect = Exception("BD_Mock_Error")
        payload = {
            "tipo_calculo": "substituicao",
            "dados_extraidos": {
                "salario_substituta": 5000.0, "salario_propria": 3000.0,
                "dias_substituidos": 15, "mes": 10, "ano": 2024
            }
        }
        r = auth_client_user.post("/api/calcular", json=payload)
        assert r.status_code == 500
        assert "histórico" in r.json()["detail"]
