"""Configuration management for the demo application."""

import os
import json
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    name: str = "park_management"
    user: str = "admin"
    password: str = ""
    pool_size: int = 10
    pool_timeout: int = 30
    ssl_enabled: bool = False

    def connection_string(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    def async_connection_string(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class RedisConfig:
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str = ""
    max_connections: int = 20
    timeout: int = 10

    def connection_url(self) -> str:
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


@dataclass
class SecurityConfig:
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60
    refresh_token_expiration_days: int = 7
    password_hash_algorithm: str = "bcrypt"
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 30
    session_timeout_minutes: int = 30
    cors_allowed_origins: list = field(default_factory=lambda: ["http://localhost:3000"])


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    file_path: str = "/var/log/park_management/app.log"
    max_file_size_mb: int = 100
    backup_count: int = 5
    console_enabled: bool = True
    file_enabled: bool = True
    json_format: bool = False


@dataclass
class EmailConfig:
    smtp_host: str = "smtp.example.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    sender_name: str = "智慧园区管理平台"
    sender_email: str = "noreply@park.com"
    use_tls: bool = True
    template_dir: str = "/app/templates/email"


@dataclass
class AppConfig:
    app_name: str = "智慧园区管理平台"
    version: str = "V1.0"
    debug: bool = False
    environment: str = "production"
    timezone: str = "Asia/Shanghai"
    language: str = "zh-CN"
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    email: EmailConfig = field(default_factory=EmailConfig)

    def is_production(self) -> bool:
        return self.environment == "production"

    def is_development(self) -> bool:
        return self.environment == "development"

    def is_testing(self) -> bool:
        return self.environment == "testing"

    @classmethod
    def from_env(cls) -> "AppConfig":
        config = cls()
        config.debug = os.getenv("APP_DEBUG", "false").lower() == "true"
        config.environment = os.getenv("APP_ENV", "production")
        config.database.host = os.getenv("DB_HOST", "localhost")
        config.database.port = int(os.getenv("DB_PORT", "5432"))
        config.database.name = os.getenv("DB_NAME", "park_management")
        config.database.user = os.getenv("DB_USER", "admin")
        config.database.password = os.getenv("DB_PASSWORD", "")
        config.redis.host = os.getenv("REDIS_HOST", "localhost")
        config.redis.port = int(os.getenv("REDIS_PORT", "6379"))
        config.security.jwt_secret_key = os.getenv("JWT_SECRET_KEY", "")
        config.security.jwt_expiration_minutes = int(os.getenv("JWT_EXPIRATION", "60"))
        return config

    @classmethod
    def from_file(cls, path: str) -> "AppConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        config = cls()
        config.app_name = data.get("app_name", config.app_name)
        config.version = data.get("version", config.version)
        config.environment = data.get("environment", config.environment)
        db = data.get("database", {})
        config.database.host = db.get("host", config.database.host)
        config.database.port = db.get("port", config.database.port)
        config.database.name = db.get("name", config.database.name)
        config.database.user = db.get("user", config.database.user)
        config.database.password = db.get("password", config.database.password)
        redis = data.get("redis", {})
        config.redis.host = redis.get("host", config.redis.host)
        config.redis.port = redis.get("port", config.redis.port)
        return config

    def to_dict(self) -> dict:
        return {
            "app_name": self.app_name, "version": self.version,
            "environment": self.environment, "debug": self.debug,
            "database": asdict(self.database),
            "redis": asdict(self.redis),
            "security": {
                "jwt_algorithm": self.security.jwt_algorithm,
                "jwt_expiration_minutes": self.security.jwt_expiration_minutes,
            },
        }

    def validate(self) -> list[str]:
        errors = []
        if not self.app_name:
            errors.append("应用名称不能为空")
        if self.environment not in ("development", "testing", "production"):
            errors.append(f"无效的环境类型: {self.environment}")
        if self.database.port < 1 or self.database.port > 65535:
            errors.append("数据库端口无效")
        if self.redis.port < 1 or self.redis.port > 65535:
            errors.append("Redis端口无效")
        if self.is_production():
            if not self.security.jwt_secret_key:
                errors.append("生产环境必须配置 JWT_SECRET_KEY")
            if self.debug:
                errors.append("生产环境不应启用 DEBUG 模式")
        return errors


def get_config() -> AppConfig:
    config_path = os.getenv("APP_CONFIG_PATH", "")
    if config_path and os.path.exists(config_path):
        return AppConfig.from_file(config_path)
    return AppConfig.from_env()


_config_cache: Optional[AppConfig] = None


def get_cached_config() -> AppConfig:
    global _config_cache
    if _config_cache is None:
        _config_cache = get_config()
    return _config_cache


def reset_config_cache() -> None:
    global _config_cache
    _config_cache = None
