"""Regressões com dados sintéticos e bancos temporários, sem acessar .env real."""
import logging
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.db.salary_security_migration import migrate_salary_security
from app.models.tabelas_salariais import (
    HistoricoCalculo,
    TabelaRetribuicaoTitulacao,
    TabelaVencimentoBasico,
)
from app.models.user import AuditLog
from app.services.dados_pdf import extract_calculation_data
from app.services.motor_calculos_rh import MotorCalculosRH
from app.utils.crypto import DataIntegrityError, decrypt_data


@pytest.mark.parametrize("invalid", [999, -1, 1.5, True, "2"])
def test_rescisao_rejeita_dias_invalidos_sem_historico(auth_client_user, db_session, invalid):
    response = auth_client_user.post("/api/calcular", json={"tipo_calculo": "rescisao", "dados_extraidos": {
        "dias_trabalhados": invalid, "mes_rescisao": 4, "ano_rescisao": 2026,
    }})
    assert response.status_code == 400
    assert db_session.query(HistoricoCalculo).count() == 0


def test_limites_calendario_e_devolucao_legitima():
    result = MotorCalculosRH.calcular_rescisao_substituto(
        salario_mensal=3000, dias_trabalhados_ultimo_mes=30,
        meses_ferias_indenizadas=-4, mes_rescisao=4, ano_rescisao=2026,
    )
    assert result["detalhamento_rubricas"]["742_salario"]["devido"] == 3000
    assert result["detalhamento_rubricas"]["772_ferias"]["devido"] == 0
    assert result["detalhamento_rubricas"]["82696_terco_ferias"]["devido"] == -333.33
    with pytest.raises(ValueError):
        MotorCalculosRH.calcular_rescisao_substituto(salario_mensal=3000, dias_trabalhados_ultimo_mes=29, mes_rescisao=2, ano_rescisao=2026)
    result = MotorCalculosRH.calcular_rescisao_substituto(salario_mensal=2900, dias_trabalhados_ultimo_mes=29, mes_rescisao=2, ano_rescisao=2024)
    assert result["detalhamento_rubricas"]["742_salario"]["devido"] == 2900


@pytest.mark.parametrize("invalid", [999, -1, 1.5, True])
def test_progressao_rejeita_dias_invalidos(auth_client_user, db_session, invalid):
    response = auth_client_user.post("/api/calcular", json={"tipo_calculo": "progressao", "dados_extraidos": {
        "dias_proporcionais": invalid, "mes_proporcao": 4, "ano_proporcao": 2026,
        "salario_antigo": 3000, "salario_novo": 4000,
    }})
    assert response.status_code == 400
    assert db_session.query(HistoricoCalculo).count() == 0


@pytest.mark.parametrize("classe", ["%", "_", "", "Adjun", "inexistente"])
def test_classe_nao_seleciona_salario_por_padrao(db_session, classe):
    db_session.add(TabelaVencimentoBasico(classe="Adjunto", nivel=1, ano=2026, valor=3000))
    db_session.commit()
    with pytest.raises(ValueError):
        MotorCalculosRH._obter_salario_tabela(classe, 1, "N/A", 2026)
    with pytest.raises(ValueError, match="data salarial"):
        MotorCalculosRH._obter_salario_tabela(" adjunto ", 1, "N/A", 2026)


@pytest.mark.parametrize("endpoint,model,title", [
    ("vencimentos", TabelaVencimentoBasico, {}),
    ("titulacoes", TabelaRetribuicaoTitulacao, {"titulacao": "Especialização"}),
])
def test_repetir_nova_vigencia_retorna_conflito(auth_client_admin, db_session, endpoint, model, title):
    row = model(classe="Sintética", nivel=1, ano=2025, valor=1000, **title)
    db_session.add(row)
    db_session.commit()
    url = f"/api/tabelas/{endpoint}/{row.id}"
    assert auth_client_admin.put(url, json={"valor": 2000, "ano_vigente": 2026}).status_code == 200
    assert auth_client_admin.put(url, json={"valor": 3000, "ano_vigente": 2026}).status_code == 409
    assert db_session.query(model).filter_by(ano=2026).one().valor == 2000
    assert auth_client_admin.put(url, json={"valor": 1000, "ano_vigente": 0}).status_code == 422


def test_unicidade_no_banco_independe_da_api(db_session):
    db_session.add(TabelaVencimentoBasico(classe="Sintética", nivel=1, ano=2026, valor=1000))
    db_session.commit()
    db_session.add(TabelaVencimentoBasico(classe="SINTETICA", nivel=1, ano=2026, valor=2000))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_criacao_equivalente_retorna_409(auth_client_admin):
    payload = {"classe": "Sintética", "nivel": 1, "ano": 2026, "valor": 1000}
    assert auth_client_admin.post("/api/tabelas/vencimentos", json=payload).status_code == 200
    assert auth_client_admin.post("/api/tabelas/vencimentos", json={**payload, "classe": "SINTETICA"}).status_code == 409


def save_calculation(client):
    response = client.post("/api/calcular", json={"tipo_calculo": "abono", "dados_extraidos": {
        "matricula": "MATRICULA-SINTETICA", "classe": "CLASSE-SINTETICA", "titulacao": "TITULO-SINTETICO",
        "valores_anuais": {"2026": [100]},
    }})
    assert response.status_code == 200
    return response.json()["historico_id"]


def test_metadados_criptografados_preservam_interface(auth_client_user, db_session):
    row_id = save_calculation(auth_client_user)
    raw = db_session.execute(text("SELECT matricula, classe, titulacao FROM historico_calculo WHERE id=:id"), {"id": row_id}).one()
    assert all(value.startswith("gAAAAA") for value in raw)
    assert decrypt_data(raw[0]) == "MATRICULA-SINTETICA"
    assert auth_client_user.get("/api/historico").json()[0]["matricula"] == "MATRICULA-SINTETICA"
    assert auth_client_user.get("/api/dashboard/stats").json()["ultimos_calculos"][0]["matricula"] == "MATRICULA-SINTETICA"


@pytest.mark.parametrize("corrupted", ["gAAAAA-invalido", '{"versao": 2, "dados_extraidos": {}, "resultado_calculo": {"total": 999999}}'])
def test_historico_corrompido_nao_retorna_sucesso_vazio(auth_client_user, db_session, corrupted):
    row_id = save_calculation(auth_client_user)
    db_session.get(HistoricoCalculo, row_id).resultado_json = corrupted
    db_session.commit()
    assert auth_client_user.get("/api/historico").status_code == 500
    assert auth_client_user.post("/api/exportar-pdf", json={"historico_id": row_id}).status_code == 500
    token = Fernet(Fernet.generate_key()).encrypt(b"sintetico").decode()
    with pytest.raises(DataIntegrityError):
        decrypt_data(token)


def test_metadado_corrompido_nao_e_tratado_como_texto_legado(auth_client_user, db_session):
    row_id = save_calculation(auth_client_user)
    db_session.execute(text("UPDATE historico_calculo SET matricula = 'token-corrompido' WHERE id=:id"), {"id": row_id})
    db_session.commit()
    assert auth_client_user.get("/api/historico").status_code == 500
    assert auth_client_user.get("/api/dashboard/stats").status_code == 500


def test_troca_senha_limita_tentativas_e_preserva_credencial(auth_client_user, regular_user, db_session, monkeypatch):
    from app.utils.limiter import limiter
    limiter.reset()
    monkeypatch.setattr(limiter, "enabled", True)
    original_hash = regular_user.hashed_password
    try:
        responses = [auth_client_user.put("/api/auth/me/alterar-senha", json={
            "current_password": "Errada-Sintetica", "new_password": "Nova@12345",
        }) for _ in range(6)]
        assert [r.status_code for r in responses] == [400] * 5 + [429]
        db_session.refresh(regular_user)
        assert regular_user.hashed_password == original_hash
    finally:
        limiter.reset()


@pytest.mark.parametrize("success", [True, False])
def test_extracao_auditada_sem_dados_do_documento(auth_client_user, db_session, success):
    with patch("app.routers.calculos_router.extract_pdf_data", return_value=extract_calculation_data("Nome: MARCADOR-PESSOAL\nAno: 2026", "substituicao")):
        response = auth_client_user.post("/api/extrair-pdf", data={"tipo_calculo": "substituicao"}, files={
            "arquivos": ("NOME-PESSOAL.pdf", b"%PDF-1.4\n" if success else b"invalido", "application/pdf"),
        })
    assert response.status_code == (200 if success else 400)
    action = "PDF_EXTRAIDO" if success else "PDF_EXTRACAO_FALHOU"
    audit = db_session.query(AuditLog).filter_by(action=action).one()
    assert audit.user_id is not None and audit.ip_address is not None
    assert "MARCADOR-PESSOAL" not in audit.target and "NOME-PESSOAL" not in audit.target


def test_falha_auditoria_extracao_nao_entrega_dados(auth_client_user, monkeypatch, db_session):
    original = db_session.commit
    def fail_audit():
        if any(isinstance(obj, AuditLog) and obj.action == "PDF_EXTRAIDO" for obj in db_session.new):
            raise RuntimeError("falha sintetica")
        original()
    monkeypatch.setattr(db_session, "commit", fail_audit)
    with patch("app.routers.calculos_router.extract_pdf_data", return_value=extract_calculation_data("Nome: MARCADOR-PESSOAL", "substituicao")):
        response = auth_client_user.post("/api/extrair-pdf", data={"tipo_calculo": "substituicao"}, files={"arquivos": ("demo.pdf", b"%PDF-1.4\n", "application/pdf")})
    assert response.status_code == 503
    assert "MARCADOR-PESSOAL" not in response.text


def test_excecao_com_dados_pessoais_nao_chega_ao_log(auth_client_user, db_session, caplog):
    with caplog.at_level(logging.ERROR), patch("app.utils.crypto.encrypt_data", side_effect=RuntimeError("MARCADOR-SENSIVEL")):
        response = auth_client_user.post("/api/calcular", json={"tipo_calculo": "abono", "dados_extraidos": {"valores_anuais": {"2026": [100]}}})
    assert response.status_code == 500
    assert "MARCADOR-SENSIVEL" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_falha_auditoria_nao_vaza_excecao(auth_client_admin, db_session, monkeypatch, caplog):
    original = db_session.commit
    def fail():
        if any(isinstance(obj, AuditLog) and obj.action == "USER_CREATED" for obj in db_session.new):
            raise RuntimeError("MARCADOR-SENSIVEL")
        original()
    monkeypatch.setattr(db_session, "commit", fail)
    with caplog.at_level(logging.ERROR):
        response = auth_client_admin.post("/api/auth/usuarios", json={"username": "sintetico", "password": "Teste@12345"})
    assert response.status_code == 503
    assert "MARCADOR-SENSIVEL" not in caplog.text


def test_handler_generico_nao_vaza_excecao(caplog):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.main import generic_exception_handler
    app = FastAPI()
    app.add_exception_handler(Exception, generic_exception_handler)
    @app.get("/falha")
    def fail():
        raise RuntimeError("MARCADOR-SENSIVEL")
    with caplog.at_level(logging.ERROR), TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/falha")
    assert response.status_code == 500
    assert "MARCADOR-SENSIVEL" not in caplog.text and "MARCADOR-SENSIVEL" not in response.text


def legacy_engine():
    engine = create_engine("sqlite://", hide_parameters=True)
    with engine.begin() as c:
        c.execute(text("CREATE TABLE tabela_vencimento_basico (id INTEGER PRIMARY KEY, classe VARCHAR, nivel INTEGER, ano INTEGER, valor FLOAT)"))
        c.execute(text("INSERT INTO tabela_vencimento_basico VALUES (1, 'Sintética', 1, 2026, 1000)"))
        c.execute(text("CREATE TABLE historico_calculo (id INTEGER PRIMARY KEY, matricula VARCHAR, classe VARCHAR, titulacao VARCHAR, resultado_json VARCHAR)"))
        c.execute(text("INSERT INTO historico_calculo VALUES (1, 'MATRICULA-SINTETICA', 'Sintética', 'N/A', '{}')"))
    return engine


def test_migracao_legada_protege_dados_e_e_idempotente():
    engine = legacy_engine()
    try:
        migrate_salary_security(engine)
        with engine.connect() as c:
            before = c.execute(text("SELECT matricula, classe, titulacao, resultado_json FROM historico_calculo")).one()
            assert all(value.startswith("gAAAAA") for value in before)
            assert decrypt_data(before[0]) == "MATRICULA-SINTETICA"
        migrate_salary_security(engine)
        with engine.connect() as c:
            assert c.execute(text("SELECT matricula, classe, titulacao, resultado_json FROM historico_calculo")).one() == before
        with pytest.raises(IntegrityError), engine.begin() as c:
            c.execute(text("INSERT INTO tabela_vencimento_basico VALUES (2, 'Sintetica', 1, 2026, 2000, 'sintetica')"))
    finally:
        engine.dispose()


def test_migracao_nao_escolhe_valor_entre_duplicatas():
    engine = legacy_engine()
    try:
        with engine.begin() as c:
            c.execute(text("INSERT INTO tabela_vencimento_basico VALUES (2, 'SINTETICA', 1, 2026, 2000)"))
        with pytest.raises(RuntimeError, match="duplicadas"):
            migrate_salary_security(engine)
        with engine.connect() as c:
            assert c.execute(text("SELECT valor FROM tabela_vencimento_basico ORDER BY id")).scalars().all() == [1000, 2000]
            assert c.execute(text("SELECT matricula FROM historico_calculo")).scalar_one() == "MATRICULA-SINTETICA"
    finally:
        engine.dispose()


def test_migracao_titulacoes_respeita_normalizacao_e_unicidade():
    engine = legacy_engine()
    try:
        with engine.begin() as c:
            c.execute(text("CREATE TABLE tabela_retribuicao_titulacao (id INTEGER PRIMARY KEY, classe VARCHAR, nivel INTEGER, titulacao VARCHAR, ano INTEGER, valor FLOAT)"))
            c.execute(text("INSERT INTO tabela_retribuicao_titulacao VALUES (1, 'Sintética', 1, 'Especialização', 2026, 1000)"))
        migrate_salary_security(engine)
        with engine.connect() as c:
            keys = c.execute(text("SELECT classe_chave, titulacao_chave FROM tabela_retribuicao_titulacao")).one()
            assert keys == ("sintetica", "especializacao")
        with pytest.raises(IntegrityError), engine.begin() as c:
            c.execute(text("INSERT INTO tabela_retribuicao_titulacao VALUES (2, 'Sintetica', 1, 'Especializacao', 2026, 2000, 'sintetica', 'especializacao')"))
    finally:
        engine.dispose()


def test_migracao_chave_incorreta_nao_reescreve_historico():
    engine = legacy_engine()
    token = Fernet(Fernet.generate_key()).encrypt(b"sintetico").decode()
    try:
        with engine.begin() as c:
            c.execute(text("UPDATE historico_calculo SET resultado_json=:token"), {"token": token})
        with pytest.raises(DataIntegrityError):
            migrate_salary_security(engine)
        with engine.connect() as c:
            assert c.execute(text("SELECT matricula, resultado_json FROM historico_calculo")).one() == ("MATRICULA-SINTETICA", token)
    finally:
        engine.dispose()
