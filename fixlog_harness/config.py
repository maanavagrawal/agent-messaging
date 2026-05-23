from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from fixlog_harness.local_config import load_local_config


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
    allowed_projects: list[Path] = Field(
        default_factory=list,
        alias="FIXLOG_ALLOWED_PROJECTS",
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
    settings = HarnessSettings()
    local_config = load_local_config()
    updates: dict[str, object] = {}
    if "FIXLOG_BASE_URL" not in os.environ and local_config.base_url is not None:
        updates["fixlog_base_url"] = local_config.base_url
    if "FIXLOG_API_TOKEN" not in os.environ and local_config.api_token is not None:
        updates["fixlog_api_token"] = local_config.api_token
    if (
        "FIXLOG_CLAUDE_PROJECTS_DIR" not in os.environ
        and local_config.claude_projects_dir is not None
    ):
        updates["claude_projects_dir"] = local_config.claude_projects_dir
    if (
        "FIXLOG_SESSION_MAP_PATH" not in os.environ
        and local_config.session_map_path is not None
    ):
        updates["session_map_path"] = local_config.session_map_path
    if (
        "FIXLOG_PENDING_HARVEST_DIR" not in os.environ
        and local_config.pending_harvest_dir is not None
    ):
        updates["pending_harvest_dir"] = local_config.pending_harvest_dir
    if (
        "FIXLOG_ALLOWED_PROJECTS" not in os.environ
        and local_config.allowed_projects
    ):
        updates["allowed_projects"] = local_config.allowed_projects
    settings = settings.model_copy(update=updates)
    return settings.model_copy(
        update={"fixlog_base_url": validate_fixlog_base_url(settings.fixlog_base_url)}
    )


def validate_fixlog_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            "FIXLOG_BASE_URL/base_url must start with http:// or https:// "
            f"(got {value!r})"
        )
    return base_url
