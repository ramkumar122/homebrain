"""FastAPI application factory. The MCP endpoint is mounted here in step 4."""

from __future__ import annotations

from fastapi import FastAPI

from homebrain import __version__
from homebrain.config import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(
        title="HomeBrain",
        version=__version__,
        docs_url="/docs" if settings.is_local else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_local else None,
    )
    app.state.settings = settings

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__, "env": settings.env.value}

    return app
