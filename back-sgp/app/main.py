import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.database import Base, SessionLocal, engine
from app.routers import auth_router, calculos_router, dashboard_router
from app.services.auth_service import create_initial_admin
from app.security import RequestProtection, RequestRateBudget, allowed_hosts, validate_production_config
from app.utils.limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded


from contextlib import asynccontextmanager
from datetime import timedelta
from app.utils.clock import utcnow


@asynccontextmanager
async def lifespan(app):
    validate_production_config()
    from app.db.security_migration import migrate_security_schema
    migrate_security_schema(engine)
    Base.metadata.create_all(bind=engine)
    from app.db.salary_security_migration import migrate_salary_security
    migrate_salary_security(engine)
    from app.db.calculation_migration import migrate_calculation_schema
    migrate_calculation_schema(engine)
    from app.db.salary_reference_migration import migrate_salary_references
    migrate_salary_references(engine)
    from app.models.fontes_oficiais import migrate_official_sources
    migrate_official_sources(engine)
    db = SessionLocal()
    try:
        create_initial_admin(db)
        # Limpeza automática de tokens expirados da blacklist
        # Remove tokens com mais de 24h (já estariam expirados pelo JWT)
        from app.models.user import TokenBlacklist, UserSession
        cutoff = utcnow() - timedelta(hours=24)
        deleted = db.query(TokenBlacklist).filter(TokenBlacklist.blacklisted_on < cutoff).delete()
        db.query(UserSession).filter(UserSession.expires_at <= utcnow()).delete()
        db.commit()
        if deleted > 0:
            print(f"[Segurança] {deleted} tokens expirados removidos da blacklist.")
    finally:
        db.close()
    yield

app = FastAPI(title="SICAR — API de cálculos", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]

request_budget = RequestRateBudget()

@app.middleware("http")
async def global_rate_limiter(request: Request, call_next):
    if os.getenv("TESTING", "false").lower() == "true":
        return await call_next(request)
    ip = request.client.host if request.client else "127.0.0.1"
    if not request_budget.allow(ip):
        return JSONResponse({"detail": "Global Rate Limit Exceeded"}, status_code=429)
    return await call_next(request)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    is_prod = os.getenv("ENVIRONMENT") == "production"
    
    if is_prod:
        # HSTS Redirect: se vier via HTTP, força HTTPS
        scheme = request.url.scheme
        if scheme != "https":
            from fastapi.responses import RedirectResponse
            url = request.url.replace(scheme="https")
            return RedirectResponse(url, status_code=301)

    response = await call_next(request)
    
    if is_prod:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/") or "text/html" in response.headers.get("content-type", ""):
        response.headers["Cache-Control"] = "no-store"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)
app.add_middleware(RequestProtection, origins=ALLOWED_ORIGINS)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts(ALLOWED_ORIGINS), www_redirect=False)

from app.routers import tabelas_router
from app.routers import referencias_salariais_router
from app.routers import fontes_oficiais_router

app.include_router(calculos_router.router, prefix="/api", tags=["Calculos"])
app.include_router(auth_router.router)
app.include_router(tabelas_router.router, prefix="/api")
app.include_router(referencias_salariais_router.router, prefix="/api")
app.include_router(fontes_oficiais_router.router, prefix="/api")
app.include_router(dashboard_router.router, prefix="/api/dashboard", tags=["Dashboard"])

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Não devolve senhas, documentos ou valores NaN/Infinity contidos na entrada.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()[:100]
    ]})

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Impede que stack traces internos vazem para o cliente."""
    import logging
    logging.getLogger("uvicorn.error").error("Falha interna: %s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor. Contate o administrador do sistema."}
    )

if os.getenv("SERVE_FRONTEND", "false").lower() == "true":
    from app.frontend import mount_frontend
    mount_frontend(app, Path(__file__).resolve().parents[2] / "front-sgp" / "dist")
else:
    @app.get("/")
    def read_root():
        return {"message": "API do SICAR em execução"}
