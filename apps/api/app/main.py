"""ModelForge FastAPI app. Runs on AWS Lambda via Mangum; `create_app()` also powers local dev."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from mangum import Mangum
from modelforge_db.records import UserRecord

from .auth import current_user
from .config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/me")
    async def me(user: UserRecord = Depends(current_user)) -> dict[str, str]:  # noqa: B008
        return {"userId": user.user_id, "email": user.email}

    return app


app = create_app()
handler = Mangum(app)
