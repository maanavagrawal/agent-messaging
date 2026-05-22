from __future__ import annotations

import plistlib
from pathlib import Path

from fixlog_harness import cli
from fixlog_harness.service import LAUNCH_AGENT_LABEL, build_launch_agent_plist


def test_launch_agent_plist_runs_fixlog_watch(tmp_path: Path) -> None:
    fixlog_bin = tmp_path / "bin" / "fixlog"
    log_dir = tmp_path / "logs"

    payload = plistlib.loads(
        build_launch_agent_plist(fixlog_bin=fixlog_bin, log_dir=log_dir)
    )

    assert payload["Label"] == LAUNCH_AGENT_LABEL
    assert payload["ProgramArguments"] == [str(fixlog_bin), "watch"]
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] is True
    assert payload["StandardOutPath"] == str(log_dir / "collector.out.log")
    assert payload["StandardErrorPath"] == str(log_dir / "collector.err.log")


def test_service_install_dry_run_prints_plist(tmp_path: Path, capsys) -> None:
    fixlog_bin = tmp_path / "fixlog"
    log_dir = tmp_path / "logs"

    exit_code = cli.main(
        [
            "service",
            "install",
            "--dry-run",
            "--fixlog-bin",
            str(fixlog_bin),
            "--log-dir",
            str(log_dir),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "<key>Label</key>" in output
    assert LAUNCH_AGENT_LABEL in output
    assert str(fixlog_bin) in output
