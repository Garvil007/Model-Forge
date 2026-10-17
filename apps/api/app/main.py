"""ModelForge FastAPI app. Runs on AWS Lambda via Mangum; `create_app()` also powers local dev."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from modelforge_db.records import UserRecord

from .auth import assert_local_auth_allowed, current_user
from .config import get_settings
from .errors import register_error_handlers
from .routers import catalog, jobs, models, uploads


def create_app() -> FastAPI:
    settings = get_settings()
    assert_local_auth_allowed(settings)  # fail at startup, not on the first request
    app = FastAPI(title=settings.app_name)
    register_error_handlers(app)

    if settings.environment == "local":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173", "http://localhost:4173"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/me")
    async def me(user: UserRecord = Depends(current_user)) -> dict[str, str]:  # noqa: B008
        return {"userId": user.user_id, "email": user.email}

    app.include_router(uploads.router)
    app.include_router(models.router)
    app.include_router(catalog.router)
    app.include_router(jobs.router)

    return app


app = create_app()
handler = Mangum(app)
