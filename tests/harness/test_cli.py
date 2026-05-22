from __future__ import annotations

from fixlog_harness import cli


def test_watch_command_exits_cleanly_on_keyboard_interrupt(monkeypatch) -> None:
    def raise_keyboard_interrupt(*_args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "watch", raise_keyboard_interrupt)

    assert cli.main(["watch"]) == 0
