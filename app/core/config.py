"""Environment-backed application settings."""

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEVELOPMENT_SECRET = "development-only-change-this-key-before-deployment"


class Settings(BaseSettings):
    app_name: str = "MEDUSA Backend"
    app_env: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    submission_request_limit: int = Field(default=60, ge=1, le=10000)
    incorrect_submission_limit: int = Field(default=10, ge=1, le=10000)
    submission_rate_window_seconds: int = Field(default=60, ge=1, le=86400)
    registration_request_limit: int = Field(default=5, ge=1, le=1000)
    registration_rate_window_seconds: int = Field(default=600, ge=1, le=86400)
    token_request_limit_per_ip: int = Field(default=20, ge=1, le=10000)
    token_request_limit_per_account: int = Field(default=5, ge=1, le=1000)
    token_rate_window_seconds: int = Field(default=60, ge=1, le=86400)
    password_reset_request_limit_per_ip: int = Field(default=10, ge=1, le=1000)
    password_reset_request_limit_per_email: int = Field(default=3, ge=1, le=1000)
    password_reset_confirm_limit_per_ip: int = Field(default=10, ge=1, le=1000)
    password_reset_rate_window_seconds: int = Field(default=600, ge=1, le=86400)
    password_reset_token_expire_minutes: int = Field(default=30, ge=5, le=120)
    password_reset_url: str = "http://localhost:3000/reset-password"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True
    auth_secret_key: str = _DEVELOPMENT_SECRET
    access_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    token_issuer: str = "medusa-backend"
    sandbox_provider: str = "unavailable"
    sandbox_max_active_per_owner: int = Field(default=2, ge=1, le=100)
    sandbox_max_active_per_competition: int = Field(default=20, ge=1, le=10000)
    sandbox_max_lifetime_minutes: int = Field(default=120, ge=5, le=720)
    ops_cpu_warning_percent: float = Field(default=80, ge=0, le=100)
    ops_cpu_critical_percent: float = Field(default=95, ge=0, le=100)
    ops_memory_warning_percent: float = Field(default=80, ge=0, le=100)
    ops_memory_critical_percent: float = Field(default=95, ge=0, le=100)
    ops_disk_warning_percent: float = Field(default=80, ge=0, le=100)
    ops_disk_critical_percent: float = Field(default=95, ge=0, le=100)
    ops_cleanup_warning_count: int = Field(default=5, ge=0, le=100000)
    ops_cleanup_critical_count: int = Field(default=20, ge=0, le=100000)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("sandbox_provider")
    @classmethod
    def validate_sandbox_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "unavailable":
            raise ValueError(
                "SANDBOX_PROVIDER currently supports only 'unavailable'; "
                "real providers are not implemented"
            )
        return normalized

    @field_validator("auth_secret_key")
    @classmethod
    def validate_secret_length(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("AUTH_SECRET_KEY must be at least 32 characters")
        return value

    @model_validator(mode="after")
    def validate_production_secret(self) -> "Settings":
        is_production = self.app_env.lower() in {"production", "prod"}
        uses_development_secret = self.auth_secret_key == _DEVELOPMENT_SECRET
        if is_production and uses_development_secret:
            raise ValueError("Set a unique AUTH_SECRET_KEY before running in production")
        if is_production and (not self.smtp_host or not self.smtp_from_email):
            raise ValueError("Configure SMTP_HOST and SMTP_FROM_EMAIL before running in production")
        for warning, critical, name in (
            (self.ops_cpu_warning_percent, self.ops_cpu_critical_percent, "CPU"),
            (self.ops_memory_warning_percent, self.ops_memory_critical_percent, "memory"),
            (self.ops_disk_warning_percent, self.ops_disk_critical_percent, "disk"),
            (self.ops_cleanup_warning_count, self.ops_cleanup_critical_count, "cleanup"),
        ):
            if warning > critical:
                raise ValueError(f"OPS_{name.upper()}_WARNING must not exceed critical threshold")
        return self


@lru_cache
def get_settings() -> Settings:
    """Load and cache settings, failing fast when required configuration is missing."""
    return Settings()
