"""
test_auth.py — Testes de integração para auth_router.py

Cobre: login, logout, lockout, criação de usuário, reset de senha,
alteração de senha própria, exclusão, audit logs e listagem.
"""


# ─────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────

class TestLogin:

    def test_login_sucesso(self, client, regular_user):
        r = client.post("/api/auth/login", json={
            "username": "test_user", "password": "User@123"
        })
        assert r.status_code == 200
        assert r.json()["role"] == "user"
        assert "access_token" in r.cookies

    def test_login_senha_errada(self, client, regular_user):
        r = client.post("/api/auth/login", json={
            "username": "test_user", "password": "senha_errada"
        })
        assert r.status_code == 401

    def test_login_usuario_inexistente(self, client):
        r = client.post("/api/auth/login", json={
            "username": "fantasma", "password": "qualquer"
        })
        assert r.status_code == 401

    def test_login_incrementa_tentativas_falhas(self, client, regular_user, db_session):
        for _ in range(2):
            client.post("/api/auth/login", json={
                "username": "test_user", "password": "errada"
            })
        db_session.refresh(regular_user)
        assert regular_user.failed_login_attempts == 2

    def test_login_bloqueia_apos_5_tentativas(self, client, regular_user, db_session):
        for _ in range(5):
            client.post("/api/auth/login", json={
                "username": "test_user", "password": "errada"
            })
        db_session.refresh(regular_user)
        assert regular_user.lockout_until is not None

        r = client.post("/api/auth/login", json={
            "username": "test_user", "password": "User@123"
        })
        assert r.status_code == 401

    def test_login_sucesso_reseta_tentativas(self, client, db_session, regular_user):
        client.post("/api/auth/login", json={"username": "test_user", "password": "errada"})
        client.post("/api/auth/login", json={"username": "test_user", "password": "User@123"})
        db_session.refresh(regular_user)
        assert regular_user.failed_login_attempts == 0


# ─────────────────────────────────────────────────────────────
# Logout
# ─────────────────────────────────────────────────────────────

class TestLogout:

    def test_logout_remove_cookie(self, auth_client_user):
        r = auth_client_user.post("/api/auth/logout")
        assert r.status_code == 200
        assert r.json()["message"] == "Logout realizado com sucesso"

    def test_logout_invalida_token(self, auth_client_user):
        auth_client_user.post("/api/auth/logout")
        r = auth_client_user.get("/api/auth/usuarios")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────
# Criação de Usuário (admin only)
# ─────────────────────────────────────────────────────────────

class TestCriarUsuario:

    def test_admin_cria_usuario(self, auth_client_admin):
        r = auth_client_admin.post("/api/auth/usuarios", json={
            "username": "novo_func",
            "password": "Novo@1234",
            "role": "user",
        })
        assert r.status_code == 200
        assert r.json()["username"] == "novo_func"

    def test_usuario_comum_nao_pode_criar(self, auth_client_user):
        r = auth_client_user.post("/api/auth/usuarios", json={
            "username": "intruso",
            "password": "Intruso@123",
            "role": "user",
        })
        assert r.status_code == 403

    def test_nao_autenticado_nao_cria(self, client):
        r = client.post("/api/auth/usuarios", json={
            "username": "x", "password": "X@12345", "role": "user"
        })
        assert r.status_code == 401

    def test_senha_fraca_rejeitada(self, auth_client_admin):
        r = auth_client_admin.post("/api/auth/usuarios", json={
            "username": "fraco", "password": "12345678", "role": "user"
        })
        assert r.status_code == 400
        assert "maiúscula" in r.json()["detail"] or "especial" in r.json()["detail"]

    def test_usuario_duplicado_rejeitado(self, auth_client_admin, regular_user):
        r = auth_client_admin.post("/api/auth/usuarios", json={
            "username": "test_user",
            "password": "Dup@1234",
            "role": "user",
        })
        assert r.status_code == 400


# ─────────────────────────────────────────────────────────────
# Listagem de Usuários (admin only)
# ─────────────────────────────────────────────────────────────

class TestListarUsuarios:

    def test_admin_lista_usuarios(self, auth_client_admin, regular_user):
        r = auth_client_admin.get("/api/auth/usuarios")
        assert r.status_code == 200
        usernames = [u["username"] for u in r.json()]
        assert "test_admin" in usernames

    def test_usuario_comum_nao_lista(self, auth_client_user):
        r = auth_client_user.get("/api/auth/usuarios")
        assert r.status_code == 403


# ─────────────────────────────────────────────────────────────
# Reset de Senha (admin only)
# ─────────────────────────────────────────────────────────────

class TestResetSenha:

    def test_admin_reseta_senha(self, auth_client_admin, regular_user):
        r = auth_client_admin.put(
            f"/api/auth/usuarios/{regular_user.id}/reset-password",
            json={"new_password": "Nova@1234"},
        )
        assert r.status_code == 200

    def test_reset_senha_fraca_rejeitada(self, auth_client_admin, regular_user):
        r = auth_client_admin.put(
            f"/api/auth/usuarios/{regular_user.id}/reset-password",
            json={"new_password": "fraca"},
        )
        assert r.status_code == 400

    def test_reset_usuario_inexistente(self, auth_client_admin):
        r = auth_client_admin.put(
            "/api/auth/usuarios/99999/reset-password",
            json={"new_password": "Nova@1234"},
        )
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────
# Alterar Própria Senha
# ─────────────────────────────────────────────────────────────

class TestAlterarPropriaSenha:

    def test_usuario_altera_propria_senha(self, auth_client_user):
        r = auth_client_user.put("/api/auth/me/alterar-senha", json={
            "current_password": "User@123",
            "new_password": "Nova@5678",
        })
        assert r.status_code == 200

    def test_senha_atual_incorreta(self, auth_client_user):
        r = auth_client_user.put("/api/auth/me/alterar-senha", json={
            "current_password": "senha_errada",
            "new_password": "Nova@5678",
        })
        assert r.status_code == 400
        assert "incorreta" in r.json()["detail"]

    def test_nova_senha_fraca_rejeitada(self, auth_client_user):
        r = auth_client_user.put("/api/auth/me/alterar-senha", json={
            "current_password": "User@123",
            "new_password": "12345678",
        })
        assert r.status_code == 400

    def test_nao_autenticado_nao_altera(self, client):
        r = client.put("/api/auth/me/alterar-senha", json={
            "current_password": "User@123",
            "new_password": "Nova@5678",
        })
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────
# Exclusão de Usuário (admin only)
# ─────────────────────────────────────────────────────────────

class TestExcluirUsuario:

    def test_admin_exclui_usuario(self, auth_client_admin, regular_user):
        r = auth_client_admin.delete(f"/api/auth/usuarios/{regular_user.id}")
        assert r.status_code == 200

    def test_admin_nao_exclui_si_mesmo(self, auth_client_admin, admin_user):
        r = auth_client_admin.delete(f"/api/auth/usuarios/{admin_user.id}")
        assert r.status_code == 400

    def test_usuario_comum_nao_exclui(self, auth_client_user, admin_user):
        r = auth_client_user.delete(f"/api/auth/usuarios/{admin_user.id}")
        assert r.status_code == 403


# ─────────────────────────────────────────────────────────────
# Audit Logs (admin only)
# ─────────────────────────────────────────────────────────────

class TestAuditLogs:

    def test_dev_acessa_audit_logs(self, auth_client_dev):
        r = auth_client_dev.get("/api/auth/audit-logs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_nao_acessa_logs(self, auth_client_admin):
        r = auth_client_admin.get("/api/auth/audit-logs")
        assert r.status_code == 403

    def test_usuario_comum_nao_acessa_logs(self, auth_client_user):
        r = auth_client_user.get("/api/auth/audit-logs")
        assert r.status_code == 403

    def test_login_gera_audit_log(self, auth_client_dev):
        # O próprio login do fixture auth_client_dev já gerou um LOGIN_SUCCESS
        logs = auth_client_dev.get("/api/auth/audit-logs").json()
        actions = [l["action"] for l in logs]
        assert "LOGIN_SUCCESS" in actions
