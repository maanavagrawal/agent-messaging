from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from fixlog.sandbox.config import DEFAULT_ALLOWED_IMAGES


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./fixlog.sqlite3"
    fixlog_public_url: str = Field(default="", alias="FIXLOG_PUBLIC_URL")
    fixlog_account_1_token: str = Field(default="", alias="FIXLOG_ACCOUNT_1_TOKEN")
    fixlog_account_1_name: str = Field(default="", alias="FIXLOG_ACCOUNT_1_NAME")
    fixlog_account_2_token: str = Field(default="", alias="FIXLOG_ACCOUNT_2_TOKEN")
    fixlog_account_2_name: str = Field(default="", alias="FIXLOG_ACCOUNT_2_NAME")
    fixlog_auth_required: bool = Field(default=False, alias="FIXLOG_AUTH_REQUIRED")
    fixlog_web_secret_key: str = Field(default="", alias="FIXLOG_WEB_SECRET_KEY")
    fixlog_web_cookie_secure: bool = Field(
        default=False, alias="FIXLOG_WEB_COOKIE_SECURE"
    )
    fixlog_web_session_ttl_seconds: int = Field(
        default=60 * 60 * 24 * 7,
        alias="FIXLOG_WEB_SESSION_TTL_SECONDS",
    )
    fixlog_collector_package_url: str = Field(
        default="git+https://github.com/maanavagrawal/agent-messaging.git@main",
        alias="FIXLOG_COLLECTOR_PACKAGE_URL",
    )
    fixlog_sandbox_allowed_images: str = Field(
        default=",".join(DEFAULT_ALLOWED_IMAGES),
        alias="FIXLOG_SANDBOX_ALLOWED_IMAGES",
    )
    fixlog_sandbox_queue_size: int = Field(default=100, alias="FIXLOG_SANDBOX_QUEUE_SIZE")
    fixlog_sandbox_timeout_s: int = Field(default=60, alias="FIXLOG_SANDBOX_TIMEOUT_S")
    fixlog_sandbox_memory_mb: int = Field(default=512, alias="FIXLOG_SANDBOX_MEMORY_MB")
    fixlog_verifier_enabled: bool = Field(default=True, alias="FIXLOG_VERIFIER_ENABLED")

    @property
    def sandbox_allowed_images(self) -> frozenset[str]:
        return frozenset(
            item.strip()
            for item in self.fixlog_sandbox_allowed_images.split(",")
            if item.strip()
        )

    @property
    def web_cookie_secure(self) -> bool:
        return self.fixlog_web_cookie_secure or self.fixlog_public_url.startswith(
            "https://"
        )

    def validate_runtime(self) -> None:
        if self.fixlog_auth_required and not self.fixlog_web_secret_key:
            raise RuntimeError(
                "FIXLOG_WEB_SECRET_KEY is required when FIXLOG_AUTH_REQUIRED=true"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
