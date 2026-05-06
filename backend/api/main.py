from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.health import router as health_router
from backend.api.routes.verify import router as verify_router


import os


def create_app() -> FastAPI:
    app = FastAPI(
        title="JobSignal API",
        version="1.0.0",
        description="Job listing verification engine — Accuracy-First doctrine.",
    )

    app.include_router(health_router)
    app.include_router(verify_router)

    # Simple in-memory rate limit for hackathon hardening (T3/T4)
    from fastapi import Request
    from fastapi.responses import JSONResponse
    import time
    from collections import defaultdict

    # (IP -> [timestamps])
    _rate_limit_data: defaultdict[str, list[float]] = defaultdict(list)
    _LIMIT_WINDOW = 60
    _MAX_REQUESTS = 20

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.url.path == "/health" or request.url.path == "/ready":
            return await call_next(request)
            
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        # Clean up old timestamps
        history = _rate_limit_data[ip]
        while history and history[0] < now - _LIMIT_WINDOW:
            history.pop(0)
            
        if len(history) >= _MAX_REQUESTS:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again in a minute."},
            )
            
        history.append(now)
        return await call_next(request)

    # CORSMiddleware must be added LAST to be the OUTERMOST middleware
    # (FastAPI executes them in reverse order of addition).
    _raw_origins = os.environ.get("ALLOWED_ORIGINS", "*")
    _origins = [o.strip() for o in _raw_origins.split(",") if o.strip()] or ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


app = create_app()

