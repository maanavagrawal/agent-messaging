from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HarnessSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    fixlog_base_url: str = Field(default="http://localhost:8000", alias="FIXLOG_BASE_URL")
    fixlog_api_token: str = Field(default="", alias="FIXLOG_API_TOKEN")
    fixlog_harness_model_name: str = Field(
        default="claude-code", alias="FIXLOG_HARNESS_MODEL_NAME"
    )
    fixlog_harness_name: str = Field(
        default="claude-code-log-watcher", alias="FIXLOG_HARNESS_NAME"
    )
    claude_projects_dir: Path = Field(
        default=Path.home() / ".claude" / "projects",
        alias="FIXLOG_CLAUDE_PROJECTS_DIR",
    )
    session_map_path: Path = Field(
        default=Path.home() / ".fixlog" / "session_map.json",
        alias="FIXLOG_SESSION_MAP_PATH",
    )
    pending_harvest_dir: Path = Field(
        default=Path.home() / ".fixlog" / "pending_harvests",
        alias="FIXLOG_PENDING_HARVEST_DIR",
    )
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-4-5", alias="FIXLOG_ANTHROPIC_MODEL")
    auto_submit_harvests: bool = Field(
        default=False, alias="FIXLOG_AUTO_SUBMIT_HARVESTS"
    )
    quiet_seconds: int = Field(default=300, alias="FIXLOG_SESSION_QUIET_SECONDS")
    recent_seconds: int = Field(default=600, alias="FIXLOG_RECENT_SESSION_SECONDS")


@lru_cache
def get_harness_settings() -> HarnessSettings:
    return HarnessSettings()
