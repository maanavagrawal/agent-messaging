from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./fixlog.sqlite3"
    fixlog_account_1_token: str = Field(default="", alias="FIXLOG_ACCOUNT_1_TOKEN")
    fixlog_account_1_name: str = Field(default="", alias="FIXLOG_ACCOUNT_1_NAME")
    fixlog_account_2_token: str = Field(default="", alias="FIXLOG_ACCOUNT_2_TOKEN")
    fixlog_account_2_name: str = Field(default="", alias="FIXLOG_ACCOUNT_2_NAME")


@lru_cache
def get_settings() -> Settings:
    return Settings()

