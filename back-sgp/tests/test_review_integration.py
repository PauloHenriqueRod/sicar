import io

import pdfplumber

from app.models.user import AuditLog


def save_calculation(client, name):
    response = client.post("/api/calcular", json={
        "tipo_calculo": "abono",
        "dados_extraidos": {"nome": name, "valores_anuais": {"2026": [1000]}},
    })
    assert response.status_code == 200
    return response.json()["historico_id"]


def test_exportacao_preserva_unicode_do_snapshot(auth_client_user, db_session):
    name = "João Łukasz Ștefan Đặng — ‘Portaria nº 123’"
    history_id = save_calculation(auth_client_user, name)
    response = auth_client_user.post("/api/exportar-pdf", json={"historico_id": history_id})
    assert response.status_code == 200
    with pdfplumber.open(io.BytesIO(response.content)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert name in text
    assert db_session.query(AuditLog).filter_by(action="PDF_EXPORTADO").count() == 1


def test_exportacao_informa_glifo_ausente_sem_erro_interno(auth_client_user, db_session):
    history_id = save_calculation(auth_client_user, "João 王")
    response = auth_client_user.post("/api/exportar-pdf", json={"historico_id": history_id})
    assert response.status_code == 422
    assert "U+738B" in response.json()["detail"]
    assert db_session.query(AuditLog).filter_by(action="PDF_EXPORTADO").count() == 0
    assert auth_client_user.get("/api/historico").status_code == 200
