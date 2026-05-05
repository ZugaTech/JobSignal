from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.health import router as health_router
from backend.api.routes.verify import router as verify_router


def create_app() -> FastAPI:
    app = FastAPI(title="JobSignal API", version="0.1.0")

    # Demo-friendly: allow local static file frontend and Railway preview origins.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(verify_router)
    return app


app = create_app()

