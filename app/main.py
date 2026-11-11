import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import Base, engine
from .deps import current_user
from .models import User
from .routers import agent_runtime, auth, documents, legacy, organizations, tasks, workforce
from .routers.auth import user_out
from .schemas import UserOut

log = logging.getLogger("pep_ai")

# Development/test convenience only. Production must use `alembic upgrade head` (enforced in config.py).
if settings.auto_create_tables:
    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name, version="0.2.0",
    description="PEP AI enterprise platform API - Milestone 1: tenancy, RBAC, staff management, audit, auth hardening",
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    if settings.enable_docs is False or not request.url.path.startswith(("/docs", "/openapi")):
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    if settings.environment == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health():
    return {"status": "ok", "service": "pep-ai-api", "environment": settings.environment}


@app.get("/api/v1/users/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user_out(user)


app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(legacy.router)
app.include_router(workforce.router)
app.include_router(documents.router)
app.include_router(tasks.router)
app.include_router(agent_runtime.router)
app.include_router(tasks.user_router)
