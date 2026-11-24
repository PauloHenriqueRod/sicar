"""Memórias sintéticas; snapshots legados nunca são reinterpretados pelo motor."""

import importlib
import json

import pytest

from app.models.cobertura_adicionais import RevisaoCalculo
from app.models.tabelas_salariais import HistoricoCalculo
from app.models.user import User
from app.utils.crypto import encrypt_data


def save(client, value=1000, previous=None, employee="SINTETICO-123"):
    data = {"matricula": employee, "valores_anuais": {"2026": [value]}}
    if previous:
        data["substitui_historico_id"] = previous
    return client.post(
        "/api/calcular", json={"tipo_calculo": "abono", "dados_extraidos": data}
    )


@pytest.mark.parametrize(
    "kind,key,module",
    [
        ("abono", "abono", "test_abono_parcelas"),
        ("rescisao", "rescisao", "test_rescisao_periodos"),
        ("exercicio_anterior", "exercicios", "test_exercicios_parcelas"),
    ],
)
def test_structured_financial_flows_create_new_linked_snapshot(
    auth_client_user, db_session, kind, key, module
):
    data = {"matricula": "SINTETICO-123", key: importlib.import_module(module).plan()}
    first_response = auth_client_user.post(
        "/api/calcular", json={"tipo_calculo": kind, "dados_extraidos": data}
    )
    assert first_response.status_code == 200, first_response.text
    first = first_response.json()
    record = db_session.get(HistoricoCalculo, first["historico_id"])
    original = record.resultado_json
    data["substitui_historico_id"] = record.id
    second_response = auth_client_user.post(
        "/api/calcular", json={"tipo_calculo": kind, "dados_extraidos": data}
    )
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    db_session.expire_all()
    assert second["historico_id"] != first["historico_id"]
    assert (
        db_session.get(HistoricoCalculo, first["historico_id"]).resultado_json
        == original
    )
    assert second["resultado_calculo"] == first["resultado_calculo"]
    assert (
        db_session.get(RevisaoCalculo, first["historico_id"]).novo_id
        == second["historico_id"]
    )


def test_recalculation_keeps_previous_bytes_and_links_both_directions(
    auth_client_user, db_session, monkeypatch, tmp_path
):
    first = save(auth_client_user).json()
    identifier = first["historico_id"]
    original = db_session.get(HistoricoCalculo, identifier).resultado_json
    before = auth_client_user.get(f"/api/historico/{identifier}").json()
    second_response = save(auth_client_user, 2000, identifier)
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    db_session.expire_all()
    assert second["historico_id"] != identifier
    assert db_session.get(HistoricoCalculo, identifier).resultado_json == original
    assert db_session.get(RevisaoCalculo, identifier).novo_id == second["historico_id"]
    response = auth_client_user.get(f"/api/historico/{identifier}")
    assert response.headers["cache-control"] == "no-store"
    old = response.json()
    assert old["snapshot"] == before["snapshot"]
    assert old["snapshot"]["resultado_calculo"] == first["resultado_calculo"]
    new = auth_client_user.get(f"/api/historico/{second['historico_id']}").json()
    assert new["anterior_id"] == identifier
    assert old["substituido_por"] == second["historico_id"]
    assert save(auth_client_user, 3000, identifier).status_code == 409
    assert db_session.query(HistoricoCalculo).count() == 2
    captured = {}

    def export(**kwargs):
        captured.update(kwargs)
        path = tmp_path / "synthetic.pdf"
        path.write_bytes(b"%PDF-1.4\n%%EOF\n")
        return str(path)

    monkeypatch.setattr("app.routers.calculos_router.generate_pdf_report", export)
    assert (
        auth_client_user.post(
            "/api/exportar-pdf", json={"historico_id": identifier}
        ).status_code
        == 200
    )
    assert captured["resultado_calculo"] == first["resultado_calculo"]
    assert (
        "HISTÓRICA SUBSTITUÍDA"
        in captured["dados_extraidos"]["identificacao_historico"]["situacao"]
    )
    assert db_session.get(HistoricoCalculo, identifier).resultado_json == original


def test_legacy_snapshot_keeps_its_original_structure(
    auth_client_user, db_session, regular_user
):
    value = {
        "total_geral_a_receber": 123.45,
        "versao_motor_original": "SINTETICA-ANTIGA",
    }
    record = HistoricoCalculo(
        user_id=regular_user.id,
        tipo_calculo="abono",
        matricula="SINTETICO-123",
        resultado_json=encrypt_data(json.dumps(value)),
    )
    db_session.add(record)
    db_session.commit()
    original = record.resultado_json
    data = auth_client_user.get(f"/api/historico/{record.id}").json()
    assert data["snapshot"] == value and not data["pode_recalcular"]
    assert (
        json.loads(auth_client_user.get("/api/historico").json()[0]["resultado_json"])
        == value
    )
    assert record.resultado_json == original


def test_memory_is_private_and_wrong_employee_cannot_replace_it(
    auth_client_user, db_session, admin_user
):
    identifier = save(auth_client_user).json()["historico_id"]
    assert (
        save(auth_client_user, 2000, identifier, "OUTRO-SINTETICO").status_code == 409
    )
    other = User(
        username="outra_memoria",
        hashed_password=admin_user.hashed_password,
        role="user",
    )
    db_session.add(other)
    db_session.commit()
    auth_client_user.post(
        "/api/auth/login", json={"username": other.username, "password": "Admin@123"}
    )
    denied = auth_client_user.get(f"/api/historico/{identifier}")
    absent = auth_client_user.get("/api/historico/999999")
    assert (
        denied.status_code == absent.status_code == 404
        and denied.json() == absent.json()
    )
    assert save(auth_client_user, 2000, identifier).status_code == 409
    auth_client_user.post(
        "/api/auth/login", json={"username": "test_admin", "password": "Admin@123"}
    )
    assert auth_client_user.get(f"/api/historico/{identifier}").status_code == 200


def test_exact_inputs_and_final_rounding_are_preserved_in_memory_and_export(
    auth_client_user, monkeypatch, tmp_path
):
    from test_exercicios_parcelas import due, plan

    data = plan()
    data["parcelas"].append({**data["parcelas"][0], "id": "P2", "rubrica": "54321"})
    data["devidos"] = [due("D1", "0.005"), due("D2", "0.005", parcela_id="P2")]
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "exercicio_anterior",
            "dados_extraidos": {"matricula": "SINTETICO", "exercicios": data},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    identifier = result["historico_id"]
    detail = auth_client_user.get(f"/api/historico/{identifier}").json()["snapshot"]
    assert result["resultado_calculo"]["saldo_parcelas_calculadas"] == "0.01"
    assert "nota_arredondamento" in result["resultado_calculo"]
    assert detail["resultado_calculo"] == result["resultado_calculo"]
    assert [
        line["valor"] for line in detail["dados_extraidos"]["exercicios"]["devidos"]
    ] == ["0.005", "0.005"]
    assert detail["rastreabilidade"]["arredondamento"] == "decimal_half_up_final_v3"
    captured = {}

    def export(**kwargs):
        captured.update(kwargs)
        path = tmp_path / "synthetic-rounding.pdf"
        path.write_bytes(b"%PDF-1.4\n%%EOF\n")
        return str(path)

    monkeypatch.setattr("app.routers.calculos_router.generate_pdf_report", export)
    assert (
        auth_client_user.post(
            "/api/exportar-pdf", json={"historico_id": identifier}
        ).status_code
        == 200
    )
    assert captured["resultado_calculo"] == detail["resultado_calculo"]
    assert (
        captured["dados_extraidos"]["exercicios"]
        == detail["dados_extraidos"]["exercicios"]
    )
