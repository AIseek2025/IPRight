from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "IPRight"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    DB_TYPE: str = "sqlite"

    DATABASE_URL: str = "sqlite+aiosqlite:///./ipright.db"
    DATABASE_SYNC_URL: str = "sqlite:///./ipright.db"

    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "ipright"
    MINIO_SECURE: bool = False

    WORKSPACE_ROOT: str = "/tmp/ipright-workspace"
    MAX_RETRY_PER_STAGE: int = 2
    TASK_TIMEOUT_SECONDS: int = 3600
    AUTO_DISPATCH_TASKS: bool = True

    model_config = {"env_prefix": "IPRIGHT_", "env_file": ".env"}


settings = Settings()

if settings.DB_TYPE == "sqlite":
    db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    if db_path.startswith("./"):
        db_path = str(Path(__file__).parent.parent.parent / db_path[2:])
    settings.DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"
    settings.DATABASE_SYNC_URL = f"sqlite:///{db_path}"
