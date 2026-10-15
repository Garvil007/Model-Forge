"""App settings, loaded from env vars / .env with safe local defaults."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MF_", env_file=".env", extra="ignore")

    app_name: str = "ModelForge API"
    environment: str = "local"

    # Cognito — values come from the AuthStack's CfnOutputs (see infra/stacks/auth_stack.py).
    cognito_user_pool_id: str = ""
    cognito_region: str = "us-east-1"
    cognito_client_id: str = ""


def get_settings() -> Settings:
    return Settings()
