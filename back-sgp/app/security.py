import os
import time
from collections import OrderedDict, deque
from threading import Lock
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

MAX_JSON_BODY = 1024 * 1024
MAX_UPLOAD_BODY = 51 * 1024 * 1024


def configured_database_url() -> str:
    environment = os.getenv("ENVIRONMENT", "development")
    if environment not in {"development", "testing", "production"}:
        raise RuntimeError("ENVIRONMENT deve ser development, testing ou production.")
    configured = os.getenv("DATABASE_URL", "").strip()
    if environment == "production":
        if not configured:
            raise RuntimeError("DATABASE_URL deve ser configurada explicitamente em produção.")
        try:
            url = make_url(configured)
            supported = url.get_backend_name() == "postgresql" and bool(url.database)
        except Exception:
            supported = False
        if not supported:
            # Não inclua a URL: ela pode conter a credencial do banco.
            raise RuntimeError("DATABASE_URL deve indicar um banco PostgreSQL em produção.")
    return configured or "sqlite:///./sgp_dados.db"


def validate_production_config():
    # Valida também ambientes escritos incorretamente, que poderiam desativar proteções.
    configured_database_url()
    if os.getenv("ENVIRONMENT") != "production":
        return
    secret = os.getenv("SECRET_KEY", "")
    if len(secret.encode("utf-8")) < 32 or secret.startswith("<"):
        raise RuntimeError("Em produção, SECRET_KEY deve conter pelo menos 32 bytes gerados aleatoriamente.")
    origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "").split(",") if origin.strip()]
    if not origins or any(urlsplit(origin).scheme != "https" or not urlsplit(origin).hostname or urlsplit(origin).path for origin in origins):
        raise RuntimeError("Configure ALLOWED_ORIGINS com origens HTTPS explícitas para produção.")
    if os.getenv("TESTING", "false").lower() == "true":
        raise RuntimeError("TESTING não pode desativar os limites em produção.")


def allowed_hosts(origins: list[str]) -> list[str]:
    configured = os.getenv("ALLOWED_HOSTS")
    if configured:
        hosts = [host.strip() for host in configured.split(",") if host.strip()]
    elif os.getenv("ENVIRONMENT") == "production":
        hosts = sorted({host for origin in origins if (host := urlsplit(origin).hostname)})
    else:
        hosts = ["localhost", "127.0.0.1", "testserver"]
    if not hosts or "*" in hosts:
        raise RuntimeError("Configure os hosts autorizados explicitamente.")
    return hosts


class RequestProtection:
    """Valida a origem e limita o corpo antes de o parser multipart alocar arquivos."""

    def __init__(self, app: ASGIApp, origins: list[str]):
        self.app = app
        self.origins = set(origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        if scope["method"] not in ("GET", "HEAD", "OPTIONS"):
            origin = headers.get("origin")
            same_origin = f'{scope["scheme"]}://{headers.get("host", "")}'
            if (origin is not None and origin not in self.origins | {same_origin}) or (origin is None and headers.get("sec-fetch-site") == "cross-site"):
                return await JSONResponse({"detail": "Origem da solicitação não autorizada."}, status_code=403)(scope, receive, send)
        path = scope["path"].rstrip("/")
        limit = MAX_UPLOAD_BODY if path == "/api/extrair-pdf" else (6 * 1024 * 1024 if path == "/api/tabelas/fontes/previa" else MAX_JSON_BODY)
        content_length = headers.get("content-length")
        if content_length is not None:
            if not content_length.isascii() or not content_length.isdecimal():
                return await JSONResponse({"detail": "Tamanho de solicitação inválido."}, status_code=400)(scope, receive, send)
            # Evita conversão de inteiros arbitrariamente grandes fornecidos pelo cliente.
            if len(content_length) > 10 or int(content_length) > limit:
                return await JSONResponse({"detail": "Solicitação acima do limite permitido."}, status_code=413)(scope, receive, send)
        consumed = 0

        async def limited_receive():
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > limit:
                    raise HTTPException(status_code=413, detail="Solicitação acima do limite permitido.")
            return message

        await self.app(scope, limited_receive, send)


class RequestRateBudget:
    def __init__(self, maximum=200, window=60, capacity=8192):
        self.maximum, self.window, self.capacity = maximum, window, capacity
        self.clients = OrderedDict()
        self.lock = Lock()

    def allow(self, ip: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self.lock:
            while self.clients and next(iter(self.clients.values()))[0] <= now - self.window:
                self.clients.popitem(last=False)
            if ip not in self.clients and len(self.clients) >= self.capacity:
                return False
            _, requests = self.clients.pop(ip, (now, deque()))
            while requests and requests[0] <= now - self.window:
                requests.popleft()
            self.clients[ip] = (now, requests)
            if len(requests) >= self.maximum:
                return False
            requests.append(now)
            return True
