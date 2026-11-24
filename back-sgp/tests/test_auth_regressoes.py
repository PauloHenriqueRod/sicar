from app.services.auth_service import create_access_token, create_user_session


def test_admin_nao_redefine_senha_dev(auth_client_admin, dev_user, db_session):
    senha = dev_user.hashed_password
    response = auth_client_admin.put(
        f"/api/auth/usuarios/{dev_user.id}/reset-password",
        json={"new_password": "Outra@1234"},
    )
    assert response.status_code == 403
    db_session.refresh(dev_user)
    assert dev_user.hashed_password == senha


def test_admin_nao_exclui_dev(auth_client_admin, dev_user, db_session):
    assert auth_client_admin.delete(f"/api/auth/usuarios/{dev_user.id}").status_code == 403
    db_session.refresh(dev_user)


def test_reset_invalida_sessao_anterior(auth_client_admin, regular_user, db_session):
    token = create_user_session(db_session, regular_user)
    db_session.commit()
    assert auth_client_admin.put(
        f"/api/auth/usuarios/{regular_user.id}/reset-password",
        json={"new_password": "Outra@1234"},
    ).status_code == 200
    auth_client_admin.cookies.clear()
    auth_client_admin.cookies.set("access_token", f"Bearer {token}")
    assert auth_client_admin.get("/api/dashboard/stats").status_code == 401
    assert auth_client_admin.post("/api/auth/login", json={
        "username": regular_user.username, "password": "Outra@1234",
    }).status_code == 200


def test_troca_renova_cookie_e_invalida_token_anterior(auth_client_user):
    antigo = auth_client_user.cookies.get("access_token")
    assert auth_client_user.put("/api/auth/me/alterar-senha", json={
        "current_password": "User@123", "new_password": "Outra@1234",
    }).status_code == 200
    assert auth_client_user.cookies.get("access_token") != antigo
    assert auth_client_user.get("/api/dashboard/stats").status_code == 200
    auth_client_user.cookies.clear()
    auth_client_user.cookies.set("access_token", antigo)
    assert auth_client_user.get("/api/dashboard/stats").status_code == 401


def test_token_sem_versao_rejeitado(client, regular_user):
    token = create_access_token({"sub": regular_user.username})
    client.cookies.set("access_token", f"Bearer {token}")
    assert client.get("/api/dashboard/stats").status_code == 401
