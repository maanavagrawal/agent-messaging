from __future__ import annotations

import os
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_CONFIG_PATH = Path.home() / ".fixlog" / "config.toml"


@dataclass(frozen=True)
class LocalHarnessConfig:
    base_url: str | None = None
    api_token: str | None = None
    claude_projects_dir: Path | None = None
    session_map_path: Path | None = None
    pending_harvest_dir: Path | None = None
    allowed_projects: list[Path] = field(default_factory=list)


def default_config_path() -> Path:
    override = os.environ.get("FIXLOG_CONFIG_PATH")
    return Path(override).expanduser() if override else DEFAULT_CONFIG_PATH


def load_local_config(path: Path | None = None) -> LocalHarnessConfig:
    config_path = path or default_config_path()
    if not config_path.exists():
        return LocalHarnessConfig()
    data = tomllib.loads(config_path.read_text())
    return LocalHarnessConfig(
        base_url=_string_or_none(data.get("base_url")),
        api_token=_string_or_none(data.get("api_token")),
        claude_projects_dir=_path_or_none(data.get("claude_projects_dir")),
        session_map_path=_path_or_none(data.get("session_map_path")),
        pending_harvest_dir=_path_or_none(data.get("pending_harvest_dir")),
        allowed_projects=[
            Path(item).expanduser()
            for item in data.get("allowed_projects", [])
            if isinstance(item, str) and item
        ],
    )


def write_local_config(
    *,
    base_url: str,
    api_token: str,
    project: Path,
    path: Path | None = None,
) -> Path:
    config_path = path or default_config_path()
    existing = load_local_config(config_path)
    project_path = project.expanduser().resolve(strict=False)
    allowed_projects = _dedupe_paths([*existing.allowed_projects, project_path])
    claude_projects_dir = existing.claude_projects_dir or Path.home() / ".claude" / "projects"
    session_map_path = existing.session_map_path or Path.home() / ".fixlog" / "session_map.json"
    pending_harvest_dir = (
        existing.pending_harvest_dir or Path.home() / ".fixlog" / "pending_harvests"
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            [
                f'base_url = "{_escape_toml_string(base_url)}"',
                f'api_token = "{_escape_toml_string(api_token)}"',
                f'claude_projects_dir = "{_escape_toml_string(str(claude_projects_dir))}"',
                f'session_map_path = "{_escape_toml_string(str(session_map_path))}"',
                f'pending_harvest_dir = "{_escape_toml_string(str(pending_harvest_dir))}"',
                "allowed_projects = [",
                *[
                    f'  "{_escape_toml_string(str(item))}",'
                    for item in allowed_projects
                ],
                "]",
                "",
            ]
        )
    )
    return config_path


def detect_project_root(cwd: Path | None = None) -> Path:
    root = cwd or Path.cwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return root.resolve(strict=False)
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve(strict=False)
    return root.resolve(strict=False)


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _path_or_none(value: object) -> Path | None:
    return Path(value).expanduser() if isinstance(value, str) and value else None


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    deduped: list[Path] = []
    for path in paths:
        resolved = path.expanduser().resolve(strict=False)
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            deduped.append(resolved)
    return deduped


def _escape_toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
