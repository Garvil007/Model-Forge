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

    # Day 9: direct-to-S3 uploads, Hugging Face import, detect_format worker job.
    auth_mode: str = "cognito"  # "local" bypasses Cognito — see auth.py's hard-fail guard.
    local_dev_user_id: str = "local-dev-user"
    local_dev_user_email: str = "dev@localhost"
    local_dev_plan: str = "free"
    aws_region: str = "us-east-1"
    aws_endpoint_url: str = ""  # LocalStack, e.g. http://localhost:4566
    s3_public_endpoint_url: str = ""  # host used when presigning URLs for the browser
    uploads_bucket: str = "mf-uploads"
    results_bucket: str = "mf-results"
    system_jobs_queue_url: str = ""
    cpu_jobs_queue_url: str = ""
    gpu_jobs_queue_url: str = ""
    presign_expiry_seconds: int = 6 * 3600
    download_presign_expiry_seconds: int = 300
    upload_part_size_bytes: int = 100 * 1024 * 1024
    hf_timeout_seconds: float = 15.0
    hf_token_kms_key_id: str = "alias/modelforge-hf-tokens"


def get_settings() -> Settings:
    return Settings()
