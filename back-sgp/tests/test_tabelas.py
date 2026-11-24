
class TestTabelasRouter:

    # ==========================
    # GET (Acesso APENAS Admin/Dev)
    # ==========================
    def test_listar_vencimentos_admin(self, auth_client_admin):
        response = auth_client_admin.get("/api/tabelas/vencimentos")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_listar_vencimentos_usuario_comum_bloqueado(self, auth_client_user):
        response = auth_client_user.get("/api/tabelas/vencimentos")
        assert response.status_code == 403

    def test_listar_titulacoes_usuario_comum_bloqueado(self, auth_client_user):
        response = auth_client_user.get("/api/tabelas/titulacoes")
        assert response.status_code == 403

    # ==========================
    # CREATE (Apenas Admin/Dev)
    # ==========================
    def test_criar_vencimento_admin(self, auth_client_admin):
        payload = {
            "classe": "Auxiliar",
            "nivel": 1,
            "ano": 2026,
            "valor": 5000.00
        }
        response = auth_client_admin.post("/api/tabelas/vencimentos", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Criado com sucesso"

    def test_criar_vencimento_usuario_comum_bloqueado(self, auth_client_user):
        payload = {
            "classe": "Auxiliar",
            "nivel": 1,
            "ano": 2026,
            "valor": 5000.00
        }
        response = auth_client_user.post("/api/tabelas/vencimentos", json=payload)
        assert response.status_code == 403

    def test_criar_titulacao_dev(self, auth_client_dev):
        payload = {
            "classe": "Adjunto",
            "nivel": 1,
            "titulacao": "Doutorado",
            "ano": 2026,
            "valor": 2500.00
        }
        response = auth_client_dev.post("/api/tabelas/titulacoes", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Criado com sucesso"

    # ==========================
    # UPDATE (Apenas Admin/Dev)
    # ==========================
    def test_atualizar_vencimento_admin(self, auth_client_admin):
        # 1. Criar
        payload = {"classe": "Assistente_Teste_Put", "nivel": 1, "ano": 2026, "valor": 6000.00}
        auth_client_admin.post("/api/tabelas/vencimentos", json=payload)
        
        # 2. Buscar o ID do recém-criado
        res_get = auth_client_admin.get("/api/tabelas/vencimentos")
        itens = res_get.json()
        criado = next((i for i in itens if i["classe"] == "Assistente_Teste_Put"), None)
        assert criado is not None
        venc_id = criado["id"]

        # 3. Atualizar
        update_payload = {"valor": 6500.00}
        update_res = auth_client_admin.put(f"/api/tabelas/vencimentos/{venc_id}", json=update_payload)
        assert update_res.status_code == 200
        assert update_res.json()["message"] == "Atualizado com sucesso"

    def test_atualizar_vencimento_usuario_comum_bloqueado(self, auth_client_user):
        update_payload = {"valor": 12000.00}
        # Tenta atualizar qualquer ID
        update_res = auth_client_user.put("/api/tabelas/vencimentos/1", json=update_payload)
        assert update_res.status_code == 403

    def test_atualizar_titulacao_dev(self, auth_client_dev):
        payload = {"classe": "Assistente_Tit", "nivel": 2, "titulacao": "Mestrado", "ano": 2026, "valor": 1500.00}
        auth_client_dev.post("/api/tabelas/titulacoes", json=payload)
        
        res_get = auth_client_dev.get("/api/tabelas/titulacoes")
        itens = res_get.json()
        criado = next((i for i in itens if i["classe"] == "Assistente_Tit"), None)
        tit_id = criado["id"]

        update_payload = {"valor": 1800.00}
        update_res = auth_client_dev.put(f"/api/tabelas/titulacoes/{tit_id}", json=update_payload)
        assert update_res.status_code == 200

    # ==========================
    # NOT FOUND
    # ==========================
    def test_atualizar_vencimento_inexistente(self, auth_client_admin):
        payload = {"valor": 1000.00}
        res = auth_client_admin.put("/api/tabelas/vencimentos/9999", json=payload)
        assert res.status_code == 404
