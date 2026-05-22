from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fixlog_harness import cli


def test_watch_command_exits_cleanly_on_keyboard_interrupt(monkeypatch) -> None:
    def raise_keyboard_interrupt(*_args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "watch", raise_keyboard_interrupt)

    assert cli.main(["watch"]) == 0


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
            assert path in {"/healthz", "/sandbox/status"}
            if path == "/sandbox/status":
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
