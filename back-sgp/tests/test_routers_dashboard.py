import json
from app.models.tabelas_salariais import HistoricoCalculo
from datetime import datetime, timezone

def test_get_dashboard_stats_sem_autenticacao(client):
    response = client.get("/api/dashboard/stats")
    assert response.status_code == 401

def test_get_dashboard_stats_vazio(auth_client_admin):
    response = auth_client_admin.get("/api/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_calculos"] == 0
    # O total de usuarios depende dos testes rodando, já que o auth_client cria o usuario admin
    assert data["total_usuarios"] >= 1
    assert data["calculos_por_tipo"] == {}
    assert data["ultimos_calculos"] == []

def test_get_dashboard_stats_com_dados(auth_client_admin, db_session):
    # Insere alguns dados de historico
    h1 = HistoricoCalculo(
        user_id=1,
        tipo_calculo="substituicao",
        matricula="111",
        classe="C",
        nivel=1,
        titulacao="Doutorado",
        resultado_json=json.dumps({"total": 100}),
        data_calculo=datetime.now(timezone.utc)
    )
    h2 = HistoricoCalculo(
        user_id=1,
        tipo_calculo="substituicao",
        matricula="222",
        classe="C",
        nivel=1,
        titulacao="Mestrado",
        resultado_json=json.dumps({"total": 200}),
        data_calculo=datetime.now(timezone.utc)
    )
    h3 = HistoricoCalculo(
        user_id=1,
        tipo_calculo="insalubridade",
        matricula="333",
        classe="C",
        nivel=2,
        titulacao="Graduacao",
        resultado_json=json.dumps({"total": 300}),
        data_calculo=datetime.now(timezone.utc)
    )
    
    db_session.add(h1)
    db_session.add(h2)
    db_session.add(h3)
    db_session.commit()

    response = auth_client_admin.get("/api/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total_calculos"] == 3
    assert data["calculos_por_tipo"]["substituicao"] == 2
    assert data["calculos_por_tipo"]["insalubridade"] == 1
    assert len(data["ultimos_calculos"]) == 3
    
    # Verifica a estrutura dos ultimos calculos
    ultimo = data["ultimos_calculos"][0]
    assert "id" in ultimo
    assert "tipo_calculo" in ultimo
    assert "matricula" in ultimo
    assert "classe" in ultimo
    assert "nivel" in ultimo
    assert "titulacao" in ultimo
