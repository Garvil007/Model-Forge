"""ModelForge FastAPI app. Runs on AWS Lambda via Mangum; `create_app()` also powers local dev."""

from __future__ import annotations

from fastapi import FastAPI
from mangum import Mangum

from .config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
handler = Mangum(app)
