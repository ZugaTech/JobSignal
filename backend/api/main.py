from __future__ import annotations

import time
import uuid
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes.health import router as health_router
from backend.api.routes.verify import router as verify_router
from backend.core.config import fail_fast_startup
from backend.core.metrics import METRICS
from backend.core.structured_log import configure_logging

APP_CFG = fail_fast_startup()
configure_logging(str(APP_CFG.get("LOG_LEVEL") or "info"))


def create_app() -> FastAPI:
    app = FastAPI(
        title="JobSignal API",
        version="1.0.0",
        description="Job listing verification engine.",
    )
    app.include_router(health_router)
    app.include_router(verify_router)

    rate_window = 60.0
    per_minute_v = APP_CFG.get("RATE_LIMIT_REQUESTS_PER_MINUTE")
    burst_v = APP_CFG.get("RATE_LIMIT_BURST")
    max_upload_v = APP_CFG.get("MAX_UPLOAD_BYTES")
    per_minute = int(20 if per_minute_v is None else per_minute_v)
    burst = int(5 if burst_v is None else burst_v)
    max_upload_bytes = int((5 * 1024 * 1024) if max_upload_v is None else max_upload_v)
    rate_data: defaultdict[str, list[float]] = defaultdict(list)

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        started = time.perf_counter()
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        METRICS.record_request((time.perf_counter() - started) * 1000)
        return response

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.url.path in ("/health", "/ready", "/metrics"):
            return await call_next(request)
        xff = request.headers.get("x-forwarded-for", "")
        ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")
        now = time.time()
        history = rate_data[ip]
        while history and history[0] < now - rate_window:
            history.pop(0)
        limit = per_minute + burst
        if len(history) >= limit:
            retry_after = max(1, int(rate_window - (now - history[0])))
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limited", "message": "Too many requests. Please retry shortly."},
                headers={"Retry-After": str(retry_after)},
            )
        history.append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - len(history)))
        return response

    @app.middleware("http")
    async def upload_size_middleware(request: Request, call_next):
        if request.url.path != "/v1/verify":
            return await call_next(request)
        content_len = request.headers.get("content-length")
        if content_len:
            try:
                if int(content_len) > max_upload_bytes:
                    return JSONResponse(status_code=413, content={"error": "payload_too_large", "message": "Upload exceeds MAX_UPLOAD_BYTES"})
            except ValueError:
                pass
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": "validation_error", "request_id": getattr(request.state, "request_id", "unknown"), "detail": exc.errors()})

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "request_id": getattr(request.state, "request_id", "unknown"),
                "message": "Something went wrong. Please retry.",
            },
        )

    raw_origins = str(APP_CFG.get("ALLOWED_ORIGINS") or "*")
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()] or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _frontend = Path(__file__).resolve().parent.parent.parent / "frontend"
    if _frontend.is_dir():
        app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")

    return app


app = create_app()
