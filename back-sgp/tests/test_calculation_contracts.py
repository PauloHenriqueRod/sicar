import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text

from app.db.calculation_migration import migrate_calculation_schema
from app.models.tabelas_salariais import HistoricoCalculo
from app.models.user import AuditLog
from app.utils.crypto import decrypt_data, encrypt_data


def substitution(**changes):
    return {"tipo_calculo": "substituicao", "dados_extraidos": {
        "salario_substituta": 2900, "salario_propria": 0, "dias_substituidos": 29,
        "mes": 2, "ano": 2024, **changes,
    }}


@pytest.mark.parametrize("payload", [
    substitution(salario_substituta=True), substitution(dias_substituidos=True),
    substitution(salario_substituta="2900"), substitution(mes="2"), substitution(ano=False),
    substitution(dias_substituidos=30), substitution(campo_ignorado="não persistir"),
    {"tipo_calculo": "abono", "dados_extraidos": {"valores_anuais": {"2026": "123"}}},
    {"tipo_calculo": "abono", "dados_extraidos": {"valores_anuais": {"2026": [True]}}},
    {"tipo_calculo": "abono", "dados_extraidos": {"valores_anuais": {"2026": [None]}}},
    {"tipo_calculo": "abono", "dados_extraidos": {"valores_anuais": {"2026": [-1]}}},
    {"tipo_calculo": "abono", "dados_extraidos": {"valores_anuais": {"Ano a conferir": [10]}}},
    {"tipo_calculo": "insalubridade", "dados_extraidos": {"valores_mensais": {"Janeiro": -1}}},
    {"tipo_calculo": "insalubridade", "dados_extraidos": {"valores_mensais": {"Janeiro": "Infinity"}}},
    {"tipo_calculo": "exercicio_anterior", "dados_extraidos": {"fluxo": [{"periodo": "13/2026", "v_dev": 1, "v_rec": 0}]}},
    {"tipo_calculo": "exercicio_anterior", "dados_extraidos": {"fluxo": [{"periodo": "01/2026", "v_dev": True, "v_rec": 0}]}},
    {"tipo_calculo": "progressao", "dados_extraidos": {"ano_proporcao": 2026, "salario_novo": "1000"}},
    {"tipo_calculo": "rescisao", "dados_extraidos": {"data_exercicio": "31/12/2026", "data_rescisao": "01/01/2026"}},
    {"tipo_calculo": "rescisao", "dados_extraidos": {"data_rescisao": "01/01/2026", "mes_rescisao": 2}},
])
def test_invalid_contract_never_creates_history(auth_client_user, db_session, payload):
    response = auth_client_user.post("/api/calcular", json=payload)
    assert response.status_code == 400, response.text
    errors = response.json()["detail"]
    assert isinstance(errors, list) and errors
    assert all(set(error) == {"loc", "msg", "type"} for error in errors)
    assert db_session.query(HistoricoCalculo).count() == 0


def test_retry_returns_original_result_and_one_audit(auth_client_user, db_session):
    payload = {**substitution(), "idempotency_key": str(uuid4())}
    first = auth_client_user.post("/api/calcular", json=payload)
    second = auth_client_user.post("/api/calcular", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["resultado_calculo"]["valor_proporcional_devido"] == 2900
    assert db_session.query(HistoricoCalculo).count() == 1
    assert db_session.query(AuditLog).filter_by(action="CALCULO_SALVO").count() == 1
    snapshot = json.loads(decrypt_data(db_session.query(HistoricoCalculo).one().resultado_json))
    assert "nivel" not in snapshot["dados_extraidos"]
    assert db_session.query(HistoricoCalculo).one().nivel is None
    payload["dados_extraidos"]["salario_substituta"] = 5800
    assert auth_client_user.post("/api/calcular", json=payload).status_code == 409
    assert db_session.query(HistoricoCalculo).count() == 1


def test_retry_key_is_scoped_to_current_account(auth_client_user, admin_user, db_session):
    payload = {**substitution(), "idempotency_key": str(uuid4())}
    first = auth_client_user.post("/api/calcular", json=payload).json()
    auth_client_user.post("/api/auth/login", json={"username": admin_user.username, "password": "Admin@123"})
    response = auth_client_user.post("/api/calcular", json=payload)
    assert response.status_code == 200
    assert response.json()["historico_id"] != first["historico_id"]
    assert db_session.query(HistoricoCalculo).count() == 2


def test_snapshot_preserves_actual_salary_and_retry_after_table_change(auth_client_user, db_session, salary_reference):
    salary, query = salary_reference()
    db_session.commit()
    payload = {"tipo_calculo": "rescisao", "idempotency_key": str(uuid4()), "dados_extraidos": {
        "classe": "D", "nivel": 1, "titulacao": "N/A", "data_rescisao": "28/02/2026",
        "dias_trabalhados": 28, "meses_ferias": -4, "referencia_salarial": query.model_dump(mode="json"),
    }}
    first = auth_client_user.post("/api/calcular", json=payload)
    assert first.status_code == 200, first.text
    record = db_session.get(HistoricoCalculo, first.json()["historico_id"])
    snapshot = json.loads(decrypt_data(record.resultado_json))
    assert snapshot["dados_extraidos"]["data_rescisao"] == "2026-02-28"
    trace = snapshot["rastreabilidade"]
    assert trace["versao_motor"]
    assert trace["referencias_salariais"]["salario_contrato"]["referencia"]["id"] == salary.id
    assert trace["referencias_salariais"]["salario_contrato"]["referencia"]["vencimento_basico"] == "3000"
    salary.vencimento_basico = 9000
    db_session.commit()
    repeated = auth_client_user.post("/api/calcular", json=payload)
    assert repeated.json() == first.json()
    assert json.loads(decrypt_data(record.resultado_json)) == snapshot
    rubrics = first.json()["resultado_calculo"]["detalhamento_rubricas"]
    assert rubrics["772_ferias"]["devido"] == 0
    assert rubrics["82696_terco_ferias"]["devido"] == -333.33


def test_history_search_and_pages_include_old_records_without_leaking_owners(auth_client_user, regular_user, admin_user, db_session):
    for index in range(65):
        db_session.add(HistoricoCalculo(
            user_id=regular_user.id, data_calculo=datetime(2026, 1, 1) + timedelta(days=index),
            tipo_calculo="abono", matricula=f"TESTE-{index:03}", classe="D", nivel=1,
            titulacao="Mestrado", resultado_json=encrypt_data(json.dumps({"resultado": index})),
        ))
    db_session.add(HistoricoCalculo(user_id=admin_user.id, tipo_calculo="abono", matricula="SEGREDO",
                                  classe="D", nivel=1, titulacao="Mestrado", resultado_json=encrypt_data("{}")))
    db_session.commit()
    page = auth_client_user.get("/api/historico", params={"pagina": 7, "tamanho_pagina": 10}).json()
    assert page["total"] == 65
    assert len(page["itens"]) == 5
    assert page["itens"][-1]["matricula"] == "TESTE-000"
    found = auth_client_user.get("/api/historico", params={"pagina": 1, "busca": "TESTE-000", "classe": "D"}).json()
    assert found["total"] == 1 and found["itens"][0]["matricula"] == "TESTE-000"
    sorted_page = auth_client_user.get("/api/historico", params={"pagina": 1, "ordenar_por": "matricula", "ordem": "asc"}).json()
    assert sorted_page["itens"][0]["matricula"] == "TESTE-000"
    assert auth_client_user.get("/api/historico", params={"pagina": 1, "busca": "SEGREDO"}).json()["total"] == 0
    assert auth_client_user.get("/api/historico", params={"pagina": 1, "busca": "Mestrado"}).json()["total"] == 0


def test_additive_migration_is_repeatable_and_preserves_legacy_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE historico_calculo (id INTEGER PRIMARY KEY, user_id INTEGER, resultado_json TEXT)"))
        conn.execute(text("INSERT INTO historico_calculo (id, user_id, resultado_json) VALUES (1, 1, 'legado')"))
    migrate_calculation_schema(engine)
    migrate_calculation_schema(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT resultado_json, idempotency_key FROM historico_calculo")).one() == ("legado", None)
        assert any(index["name"] == "uq_historico_requisicao" and index["unique"] for index in inspect(conn).get_indexes("historico_calculo"))
    engine.dispose()


@pytest.mark.parametrize("sort", ["matricula", "classe"])
def test_history_sorts_nullable_legacy_metadata(auth_client_user, regular_user, db_session, sort):
    for matricula, classe in ((None, None), ("TESTE", "D")):
        db_session.add(HistoricoCalculo(user_id=regular_user.id, tipo_calculo="abono", matricula=matricula,
                                      classe=classe, nivel=1, resultado_json=encrypt_data("{}")))
    db_session.commit()
    response = auth_client_user.get("/api/historico", params={"pagina": 1, "ordenar_por": sort, "ordem": "asc"})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2
    assert response.json()["itens"][0][sort] is None
