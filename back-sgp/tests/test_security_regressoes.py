"""Regressões de segurança para autenticação, autorização e entrada de arquivos."""

import re
from io import BytesIO

from app.models.tabelas_salariais import HistoricoCalculo
from app.models.user import TokenBlacklist


def test_conta_inativa_nao_consegue_fazer_login(client, regular_user, db_session):
    regular_user.is_active = False
    db_session.commit()

    response = client.post(
        "/api/auth/login",
        json={"username": regular_user.username, "password": "User@123"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Usuário ou senha incorretos"


def test_token_de_conta_desativada_deixa_de_ser_aceito(auth_client_user, regular_user, db_session):
    regular_user.is_active = False
    db_session.commit()

    response = auth_client_user.get("/api/dashboard/stats")

    assert response.status_code == 401


def test_logout_persiste_apenas_o_hash_do_token(auth_client_user, db_session):
    token = auth_client_user.cookies.get("access_token")
    assert token
    raw_token = token.removeprefix("Bearer ")

    response = auth_client_user.post("/api/auth/logout")

    assert response.status_code == 200
    registro = db_session.query(TokenBlacklist).order_by(TokenBlacklist.id.desc()).first()
    assert registro is not None
    assert re.fullmatch(r"[0-9a-f]{64}", registro.token)
    assert registro.token != raw_token


def test_admin_comum_nao_cria_perfil_privilegiado(auth_client_admin):
    response = auth_client_admin.post(
        "/api/auth/usuarios",
        json={"username": "novo_admin", "password": "Novo@1234", "role": "admin"},
    )

    assert response.status_code == 403


def test_papel_de_usuario_fora_da_lista_e_rejeitado(auth_client_admin):
    response = auth_client_admin.post(
        "/api/auth/usuarios",
        json={"username": "papel_invalido", "password": "Senha@1234", "role": "superuser"},
    )

    assert response.status_code == 422


def test_dashboard_de_usuario_comum_fica_isolado(auth_client_user, regular_user, admin_user, db_session):
    db_session.add_all(
        [
            HistoricoCalculo(
                user_id=regular_user.id,
                tipo_calculo="substituicao",
                matricula="MINHA-001",
                classe="A",
                nivel=1,
                titulacao="N/A",
                resultado_json="{}",
            ),
            HistoricoCalculo(
                user_id=admin_user.id,
                tipo_calculo="rescisao",
                matricula="OUTRA-999",
                classe="B",
                nivel=2,
                titulacao="N/A",
                resultado_json="{}",
            ),
        ]
    )
    db_session.commit()

    response = auth_client_user.get("/api/dashboard/stats")
    data = response.json()

    assert response.status_code == 200
    assert data["total_calculos"] == 1
    assert data["ultimos_calculos"][0]["matricula"] == "MINHA-001"


def test_upload_rejeita_lote_acima_do_limite(auth_client_user):
    files = [
        ("arquivos", (f"arquivo-{index}.pdf", BytesIO(b"%PDF-1.7"), "application/pdf"))
        for index in range(11)
    ]

    response = auth_client_user.post(
        "/api/extrair-pdf",
        data={"tipo_calculo": "substituicao"},
        files=files,
    )

    assert response.status_code == 413


def test_erro_de_calculo_nao_expõe_detalhe_da_excecao(auth_client_user):
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "substituicao",
            "dados_extraidos": {"salario_substituta": "valor-invalido"},
        },
    )

    assert response.status_code == 400
    assert any(error["loc"] == ["dados_extraidos", "salario_substituta"] for error in response.json()["detail"])
    assert "valor-invalido" not in response.text
    assert "could not convert" not in response.text.lower()


def test_respostas_incluem_headers_de_protecao(client):
    response = client.get("/", headers={"x-forwarded-proto": "https"})

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_falha_interna_de_calculo_nao_expoe_detalhes(auth_client_user, monkeypatch, caplog):
    def failed(*args, **kwargs):
        raise ValueError("MARCADOR-SENSIVEL-DO-CALCULO")

    monkeypatch.setattr("app.routers.calculos_router.execute_calculation", failed)
    response = auth_client_user.post(
        "/api/calcular",
        json={"tipo_calculo": "abono", "dados_extraidos": {"valores_anuais": {"2026": [100]}}},
    )
    assert response.status_code == 400
    assert "Não foi possível" in response.json()["detail"]
    assert "MARCADOR-SENSIVEL" not in response.text
    assert "MARCADOR-SENSIVEL" not in caplog.text
