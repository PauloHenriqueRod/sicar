"""Precisão no contrato HTTP, idempotência, histórico e exportação."""
import io
import json
from uuid import uuid4

import pdfplumber
import pytest
from fastapi.encoders import jsonable_encoder

from app.models.tabelas_salariais import HistoricoCalculo
from app.schemas.calculos import SubstituicaoDados
from app.utils.crypto import decrypt_data, encrypt_data


@pytest.mark.parametrize("valor,esperado", [("1.00499999999999999", 1.00), ("1.005", 1.01)])
def test_api_preserva_decimal_original_e_rejeita_retry_com_valor_diferente(auth_client_user, db_session, valor, esperado):
    key = str(uuid4())
    raw = '{"tipo_calculo":"substituicao","idempotency_key":"' + key + '","dados_extraidos":{"salario_substituta":' + valor + ',"dias_substituidos":31,"mes":1,"ano":2026}}'
    response = auth_client_user.post("/api/calcular", content=raw, headers={"Content-Type": "application/json"})
    assert response.status_code == 200, response.text
    assert response.json()["resultado_calculo"]["valor_proporcional_devido"] == esperado
    record = db_session.get(HistoricoCalculo, response.json()["historico_id"])
    saved = json.loads(decrypt_data(record.resultado_json))
    assert saved["rastreabilidade"]["entradas_decimais"]["salario_substituta"] == valor
    assert saved["rastreabilidade"]["arredondamento"] == "decimal_half_up_final_v3"
    repeated = auth_client_user.post("/api/calcular", content=raw, headers={"Content-Type": "application/json"})
    assert repeated.json() == response.json()
    different_value = "1.005" if valor != "1.005" else "1.00499999999999999"
    different = auth_client_user.post("/api/calcular", content=raw.replace(valor, different_value), headers={"Content-Type": "application/json"})
    assert different.status_code == 409
    assert db_session.query(HistoricoCalculo).count() == 1


@pytest.mark.parametrize("tipo,dados_a,dados_b", [
    ("substituicao", {"salario_substituta": 1, "dias_substituidos": 31, "mes": 1, "ano": 2026},
     {"salario_substituta": 1.0, "salario_propria": 0.0, "dias_substituidos": 31, "mes": 1, "ano": 2026}),
    ("abono", {"valores_anuais": {"2026": [1, 2.50]}}, {"valores_anuais": {"2026": [1.0, 2.5]}}),
    ("exercicio_anterior", {"fluxo": [{"periodo": "01/2026", "v_dev": 1, "v_rec": 0}]},
     {"fluxo_mensal": [{"periodo": "01/2026", "v_dev": 1.0, "v_rec": 0.0, "ab_ferias": 0, "13_sal": 0}]}),
])
def test_retry_de_numeros_equivalentes_reutiliza_historico(auth_client_user, db_session, tipo, dados_a, dados_b):
    key = str(uuid4())
    responses = [auth_client_user.post("/api/calcular", json={"tipo_calculo": tipo, "dados_extraidos": dados, "idempotency_key": key}) for dados in (dados_a, dados_b)]
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert responses[0].json() == responses[1].json()
    assert db_session.query(HistoricoCalculo).count() == 1


def test_retry_escala_diferente_nao_normaliza_textos_identificadores(auth_client_user):
    key = str(uuid4())
    raw = '{"tipo_calculo":"abono","idempotency_key":"' + key + '","dados_extraidos":{"matricula":"001","valores_anuais":{"2026":[1.00]}}}'
    first = auth_client_user.post("/api/calcular", content=raw, headers={"Content-Type": "application/json"})
    repeated = auth_client_user.post("/api/calcular", content=raw.replace("1.00", "1e0"), headers={"Content-Type": "application/json"})
    assert first.status_code == repeated.status_code == 200
    assert first.json() == repeated.json()
    changed_id = auth_client_user.post("/api/calcular", content=raw.replace('"001"', '"1"'), headers={"Content-Type": "application/json"})
    assert changed_id.status_code == 409


def test_retry_legado_mantem_resultado_e_versao_antigos(auth_client_user, regular_user, db_session):
    key = str(uuid4())
    entrada = {"salario_substituta": 1.005, "dias_substituidos": 15, "mes": 4, "ano": 2026}
    dados = jsonable_encoder(SubstituicaoDados.model_validate(entrada).model_dump(by_alias=True, exclude_none=True))
    # Política anterior: 1,005 -> 1,01 antes de aplicar 15/30 -> 0,51.
    legado = {"versao": 2, "dados_extraidos": dados, "resultado_calculo": {"valor_proporcional_devido": 0.51},
              "rastreabilidade": {"versao_motor": "2026-10-21.2", "arredondamento": "decimal_half_up_por_operacao_v2"}}
    original = json.dumps(legado)
    record = HistoricoCalculo(user_id=regular_user.id, tipo_calculo="substituicao", idempotency_key=key, resultado_json=encrypt_data(original))
    db_session.add(record)
    db_session.commit()
    response = auth_client_user.post("/api/calcular", json={"tipo_calculo": "substituicao", "dados_extraidos": entrada, "idempotency_key": key})
    assert response.status_code == 200, response.text
    assert response.json()["resultado_calculo"] == {"valor_proporcional_devido": 0.51}
    assert decrypt_data(record.resultado_json) == original
    novo = auth_client_user.post("/api/calcular", json={"tipo_calculo": "substituicao", "dados_extraidos": entrada})
    assert novo.status_code == 200, novo.text
    assert novo.json()["resultado_calculo"]["valor_proporcional_devido"] == 0.50
    assert novo.json()["historico_id"] != record.id
    assert decrypt_data(record.resultado_json) == original


def test_exportacao_e_historico_usam_total_e_politica_salvos(auth_client_user):
    response = auth_client_user.post("/api/calcular", json={"tipo_calculo": "insalubridade", "dados_extraidos": {
        "valores_mensais": {"2026-01": 0.015, "2026-02": 0.015},
    }})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["resultado_calculo"]["total_acumulado"] == 0.03
    history = auth_client_user.get("/api/historico").json()
    assert json.loads(history[0]["resultado_json"]) == result["resultado_calculo"]
    pdf_response = auth_client_user.post("/api/exportar-pdf", json={"historico_id": result["historico_id"]})
    assert pdf_response.status_code == 200, pdf_response.text
    with pdfplumber.open(io.BytesIO(pdf_response.content)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "R$ 0.03" in text
    assert "decimal_half_up_final_v3" in text
    assert "a soma dos valores exibidos pode diferir do total" in text.replace("\n", " ")
