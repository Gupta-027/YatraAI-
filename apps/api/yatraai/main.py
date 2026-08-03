"""FastAPI application factory."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text

from yatraai import __version__
from yatraai.config import get_settings
from yatraai.core.errors import YatraError
from yatraai.logging_config import configure_logging, get_logger, request_id_ctx
from yatraai.services.status import service_status_snapshot

log = get_logger(__name__)

DESCRIPTION = """
**YatraAI** builds fair, explainable and feasible group itineraries.

Responsibility separation (the LLM never invents the plan):

| Layer | Owner |
|---|---|
| Facts | Curated catalogue + provenance |
| Selection | Deterministic fairness-aware ranking |
| Travel | Routing provider (OSRM -> haversine fallback) |
| Schedule | OR-Tools CP-SAT + constraint validator |
| Knowledge | Hybrid RAG with citations |
| Wording | LLM (template fallback) |
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    configure_logging(s.yatra_log_level, s.yatra_log_json)
    problems = s.assert_production_ready()
    if problems:
        for p in problems:
            log.error("config.production_check_failed", problem=p)
        raise RuntimeError(
            "Refusing to start with insecure production configuration: " + "; ".join(problems)
        )
    log.info(
        "api.startup",
        env=s.yatra_env,
        version=__version__,
        llm_provider=s.llm_provider,
        routing_provider=s.routing_provider,
        weather_provider=s.weather_provider,
        embedding_provider=s.embedding_provider,
    )
    yield
    log.info("api.shutdown")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="YatraAI API",
        description=DESCRIPTION,
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
        max_age=600,
    )

    # ---------------- middleware ----------------
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception(
                "request.unhandled", method=request.method, path=request.url.path, request_id=rid
            )
            raise
        finally:
            request_id_ctx.reset(token)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = rid
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path not in {"/health", "/ready", "/metrics"}:
            log.info(
                "request.completed",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(elapsed_ms, 2),
            )
        return response

    # ---------------- error handlers ----------------
    @app.exception_handler(YatraError)
    async def handle_yatra_error(request: Request, exc: YatraError):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.to_dict()})

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        # Pydantic v2 puts the original exception object in ``ctx``; strip it so
        # the response stays JSON-serialisable and leaks no internals.
        detail = [
            {
                "loc": [str(p) for p in err.get("loc", [])],
                "type": err.get("type", "value_error"),
                "message": err.get("msg", "invalid value"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_failed",
                    "message": "Request payload failed validation.",
                    "detail": detail,
                }
            },
        )

    # ---------------- health ----------------
    @app.get("/health", tags=["ops"], summary="Liveness probe")
    async def health() -> dict:
        return {"status": "ok", "version": __version__, "env": s.yatra_env}

    @app.get("/ready", tags=["ops"], summary="Readiness probe (checks database)")
    async def ready() -> JSONResponse:
        from yatraai.db.session import get_engine

        checks: dict[str, object] = {}
        healthy = True
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            healthy = False
            checks["database"] = f"error: {type(exc).__name__}"
        checks["providers"] = service_status_snapshot()
        return JSONResponse(
            status_code=200 if healthy else 503,
            content={"status": "ready" if healthy else "degraded", "checks": checks},
        )

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    async def root() -> HTMLResponse:
        """Self-contained console. No CDN, so it renders offline (unlike /docs)."""
        from yatraai.api.landing import PAGE

        return HTMLResponse(PAGE)

    @app.get("/api", include_in_schema=False)
    async def api_root() -> dict:
        return {
            "name": "YatraAI API",
            "version": __version__,
            "console": "/",
            "openapi": "/openapi.json",
            "docs": "/docs (requires internet - loads Swagger UI from a CDN)",
        }

    # ---------------- routers ----------------
    from yatraai.api.v1 import api_router

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
