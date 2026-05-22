from __future__ import annotations

from pathlib import Path

from fixlog_harness.config import get_harness_settings
from fixlog_harness.local_config import load_local_config, write_local_config


def test_write_and_load_local_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    project = tmp_path / "repo"

    write_local_config(
        base_url="https://fixlog.example",
        api_token="flxdt_test",
        project=project,
        path=config_path,
    )
    loaded = load_local_config(config_path)

    assert loaded.base_url == "https://fixlog.example"
    assert loaded.api_token == "flxdt_test"
    assert loaded.claude_projects_dir == Path.home() / ".claude" / "projects"
    assert loaded.allowed_projects == [project.resolve(strict=False)]


def test_get_harness_settings_loads_local_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.toml"
    project = tmp_path / "repo"
    write_local_config(
        base_url="https://fixlog.example",
        api_token="flxdt_test",
        project=project,
        path=config_path,
    )
    monkeypatch.setenv("FIXLOG_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("FIXLOG_BASE_URL", raising=False)
    monkeypatch.delenv("FIXLOG_API_TOKEN", raising=False)
    monkeypatch.delenv("FIXLOG_ALLOWED_PROJECTS", raising=False)
    get_harness_settings.cache_clear()

    settings = get_harness_settings()

    assert settings.fixlog_base_url == "https://fixlog.example"
    assert settings.fixlog_api_token == "flxdt_test"
    assert settings.allowed_projects == [project.resolve(strict=False)]
    get_harness_settings.cache_clear()


def test_env_overrides_local_config(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    write_local_config(
        base_url="https://config.example",
        api_token="flxdt_config",
        project=tmp_path / "repo",
        path=config_path,
    )
    monkeypatch.setenv("FIXLOG_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("FIXLOG_BASE_URL", "https://env.example")
    monkeypatch.setenv("FIXLOG_API_TOKEN", "env-token")
    get_harness_settings.cache_clear()

    settings = get_harness_settings()

    assert settings.fixlog_base_url == "https://env.example"
    assert settings.fixlog_api_token == "env-token"
    get_harness_settings.cache_clear()
