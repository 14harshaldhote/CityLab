"""FastAPI application: ``uvicorn citylab.main:app``."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import Settings
from .services.runner import Runner


def create_app(settings: Settings | None = None, *, background: bool = True) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runner = Runner(settings)
        if background:
            await app.state.runner.start()
        yield
        await app.state.runner.stop()

    app = FastAPI(title="CityLab", version="0.2.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)
    return app


app = create_app()
