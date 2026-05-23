from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fixlog_harness import cli


def test_watch_command_exits_cleanly_on_keyboard_interrupt(monkeypatch) -> None:
    def raise_keyboard_interrupt(*_args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setenv("FIXLOG_BASE_URL", "https://fixlog.example")
    cli.get_harness_settings.cache_clear()
    monkeypatch.setattr(cli, "watch", raise_keyboard_interrupt)

    assert cli.main(["watch"]) == 0
    cli.get_harness_settings.cache_clear()


def test_doctor_reports_success(monkeypatch, tmp_path: Path, capsys) -> None:
    class FakeClient:
        def __init__(self, base_url: str, timeout: int) -> None:
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, path: str, headers: dict[str, str] | None = None) -> object:
            assert path in {"/healthz", "/collector/status"}
            if path == "/collector/status":
                assert headers == {"Authorization": "Bearer token-one"}
            return SimpleNamespace(status_code=200)

    settings = SimpleNamespace(
        fixlog_base_url="https://fixlog.example",
        fixlog_api_token="token-one",
        claude_projects_dir=tmp_path,
    )
    monkeypatch.setattr(cli.httpx, "Client", FakeClient)

    assert cli._doctor(settings) == 0
    output = capsys.readouterr().out
    assert "healthz=200" in output
    assert "auth_check=200" in output


def test_connect_writes_local_config(monkeypatch, tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    project = tmp_path / "repo"
    project.mkdir()
    monkeypatch.setenv("FIXLOG_CONFIG_PATH", str(config_path))

    assert cli._connect("https://fixlog.example/", "flxdt_test", project) == 0

    output = capsys.readouterr().out
    assert "connected base_url=https://fixlog.example" in output
    assert config_path.exists()
    assert 'base_url = "https://fixlog.example"' in config_path.read_text()
    assert 'api_token = "flxdt_test"' in config_path.read_text()


def test_connect_rejects_base_url_without_scheme(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    config_path = tmp_path / "config.toml"
    project = tmp_path / "repo"
    project.mkdir()
    monkeypatch.setenv("FIXLOG_CONFIG_PATH", str(config_path))

    assert (
        cli._connect("agent-messaging-production.up.railway.app", "flxdt_test", project)
        == 2
    )

    assert "must start with http:// or https://" in capsys.readouterr().err
    assert not config_path.exists()


def test_doctor_reports_invalid_base_url_before_network(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("FIXLOG_BASE_URL", "agent-messaging-production.up.railway.app")
    cli.get_harness_settings.cache_clear()

    assert cli.main(["doctor"]) == 2

    assert "must start with http:// or https://" in capsys.readouterr().err
    cli.get_harness_settings.cache_clear()
