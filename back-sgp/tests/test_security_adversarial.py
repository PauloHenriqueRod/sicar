import asyncio
import subprocess
import sys

import pytest
from fastapi import FastAPI, HTTPException, Request

from app.security import RequestProtection, RequestRateBudget, validate_production_config
from app.services import pdf_extraction

from app.models.tabelas_salariais import HistoricoCalculo
from app.utils.limiter import limiter


def test_csrf_origem_nao_autorizada_nao_encerra_sessao(auth_client_user):
    response = auth_client_user.post("/api/auth/logout",
                                    headers={"origin": "https://evil.example", "sec-fetch-site": "same-site"})
    assert response.status_code == 403
    assert auth_client_user.get("/api/dashboard/stats").status_code == 200


def test_host_arbitrario_nao_e_usado_no_redirecionamento(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    response = client.get("/", headers={"host": "evil.example"}, follow_redirects=False)
    assert response.status_code == 400
    assert "location" not in response.headers


def test_tamanho_rejeitado_antes_da_leitura_do_corpo(client):
    response = client.post("/api/calcular", headers={"content-length": str(2 * 1024 * 1024)})
    assert response.status_code == 413


def test_login_limitado_retorna_429(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    try:
        for _ in range(5):
            assert client.post("/api/auth/login", json={"username": "inexistente", "password": "Errada@123"}).status_code == 401
        assert client.post("/api/auth/login", json={"username": "inexistente", "password": "Errada@123"}).status_code == 429
    finally:
        limiter.reset()


def test_abono_com_overflow_nao_grava_historico(auth_client_user, db_session):
    response = auth_client_user.post("/api/calcular", json={
        "tipo_calculo": "abono", "dados_extraidos": {"valores_anuais": {"2026": ["1e999"]}},
    })
    assert response.status_code == 400
    assert db_session.query(HistoricoCalculo).count() == 0


@pytest.mark.parametrize("declared", [None, "1"])
def test_limite_corpo_em_stream_sem_confiar_content_length(declared):
    app = FastAPI()
    app.add_middleware(RequestProtection, origins=[])

    @app.post("/consumir")
    async def consume(request: Request):
        await request.body()
        return {"ok": True}

    headers = [(b"host", b"testserver")]
    if declared is not None:
        headers.append((b"content-length", declared.encode()))
    chunks = iter([b"x" * (600 * 1024), b"x" * (600 * 1024)])
    responses = []

    async def receive():
        return {"type": "http.request", "body": next(chunks), "more_body": True}

    async def send(message):
        responses.append(message)

    asyncio.run(app({"type": "http", "method": "POST", "path": "/consumir", "raw_path": b"/consumir",
                     "root_path": "", "scheme": "http", "query_string": b"", "headers": headers,
                     "server": ("testserver", 80), "client": ("127.0.0.1", 1234), "http_version": "1.1"}, receive, send))
    assert responses[0]["status"] == 413


def test_logout_origem_autorizada_funciona(auth_client_user):
    response = auth_client_user.post("/api/auth/logout", headers={"origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert auth_client_user.get("/api/dashboard/stats").status_code == 401


def test_rate_budget_nao_cresce_sem_limite_e_recupera_apos_expirar():
    budget = RequestRateBudget(maximum=2, capacity=2, window=60)
    assert budget.allow("a", now=0)
    assert budget.allow("a", now=1)
    assert not budget.allow("a", now=2)
    assert budget.allow("b", now=3)
    assert not budget.allow("c", now=4)
    assert len(budget.clients) == 2
    assert budget.allow("c", now=64)
    assert budget.allow("a", now=65)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_tabelas_rejeitam_valores_invalidos_sem_eco_da_entrada(auth_client_admin, value):
    response = auth_client_admin.post("/api/tabelas/vencimentos", content=(
        '{"classe":"E","nivel":1,"ano":2026,"valor":' + str(value).replace("nan", "NaN").replace("inf", "Infinity") + '}'
    ), headers={"content-type": "application/json"})
    assert response.status_code == 422
    assert "input" not in response.json()["detail"][0]


def test_configuracao_producao_rejeita_chave_curta_e_modo_teste(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    # Apenas valida configuração; nenhuma conexão PostgreSQL é aberta neste teste.
    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic:synthetic@localhost/sgp_test")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://rh.example.edu")
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setenv("SECRET_KEY", "curta")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_production_config()
    monkeypatch.setenv("SECRET_KEY", "somente-para-teste-" * 4)
    monkeypatch.setenv("TESTING", "true")
    with pytest.raises(RuntimeError, match="TESTING"):
        validate_production_config()
    monkeypatch.setenv("TESTING", "false")
    validate_production_config()


def test_pdf_timeout_libera_vaga_e_nao_repassa_segredos(monkeypatch, tmp_path):
    worker = tmp_path / "slow_worker.py"
    worker.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    monkeypatch.setattr(pdf_extraction, "_worker", worker)
    monkeypatch.setattr(pdf_extraction, "PDF_TIMEOUT_SECONDS", 0.2)
    original_run = subprocess.run
    calls = []

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return original_run(*args, **kwargs)

    monkeypatch.setattr(pdf_extraction.subprocess, "run", spy)
    for _ in range(3):
        with pytest.raises(HTTPException) as exc:
            pdf_extraction.extract_pdf_text("arquivo-sintetico.pdf")
        assert exc.value.status_code == 422
    assert all("SECRET_KEY" not in call["env"] and "DATABASE_URL" not in call["env"] for call in calls)


def test_pdf_concorrencia_excedida_falha_sem_iniciar_processo():
    assert pdf_extraction._slots.acquire(blocking=False)
    assert pdf_extraction._slots.acquire(blocking=False)
    try:
        with pytest.raises(HTTPException) as exc:
            pdf_extraction.extract_pdf_text("arquivo-sintetico.pdf")
        assert exc.value.status_code == 503
    finally:
        pdf_extraction._slots.release()
        pdf_extraction._slots.release()


def test_limite_real_de_memoria_no_processo_descartavel():
    script = (
        "import runpy; worker = runpy.run_path(" + repr(str(pdf_extraction._worker)) + "); "
        "worker['limit_memory'](); "
        "\ntry: bytearray(worker['MEMORY_LIMIT'] + 1024)"
        "\nexcept MemoryError: print('limitado')"
    )
    result = subprocess.run([sys.executable, "-I", "-X", "utf8", "-c", script], capture_output=True, timeout=10)
    assert result.returncode == 0
    assert result.stdout.strip() == b"limitado"


def test_pdf_real_acima_do_limite_de_paginas(tmp_path):
    from fpdf import FPDF
    pdf = FPDF()
    for _ in range(101):
        pdf.add_page()
    path = tmp_path / "muitas-paginas.pdf"
    pdf.output(str(path))
    with pytest.raises(HTTPException) as exc:
        pdf_extraction.extract_pdf_text(str(path))
    assert exc.value.status_code == 413
