from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fixlog_harness.config import HarnessSettings
from fixlog_harness.harvester import Harvester, load_pending_harvests
from fixlog_harness.models import NormalizedEvent, ToolCall, ToolResult


class FakePromptClient:
    def complete(self, prompt: str) -> str:
        if "Shell commands to set up" in prompt:
            return "python -m venv .venv\npython -m pip install -e ."
        return "The handler read a missing key before validating the payload."


def _git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    (path / "app.py").write_text("def run(payload):\n    return payload['username']\n")
    subprocess.run(["git", "add", "app.py"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True)
    (path / "app.py").write_text(
        "def run(payload):\n"
        "    if 'username' not in payload:\n"
        "        return None\n"
        "    return payload['username']\n"
    )


def _event(
    index: int,
    cwd: Path,
    *,
    tool_call: ToolCall | None = None,
    tool_result: ToolResult | None = None,
) -> NormalizedEvent:
    return NormalizedEvent(
        source_tool="claude_code",
        source_session_id="source-session",
        source_event_id=f"evt-{index}",
        ts=datetime(2026, 4, 27, 1, 0, tzinfo=UTC) + timedelta(seconds=index),
        kind="tool_call" if tool_call else "tool_result",
        cwd=str(cwd),
        git_branch="main",
        project_slug=cwd.name,
        tool_call=tool_call,
        tool_result=tool_result,
        redacted=False,
    )


def test_harvester_writes_pending_candidate_from_error_and_diff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_repo(repo)
    pending = tmp_path / "pending"
    settings = HarnessSettings(
        FIXLOG_PENDING_HARVEST_DIR=pending,
        FIXLOG_API_TOKEN="token",
    )
    events = [
        _event(
            1,
            repo,
            tool_call=ToolCall(
                tool_name="Bash",
                tool_call_id="toolu_fail",
                args={"command": "pytest tests/test_app.py -q"},
            ),
        ),
        _event(
            2,
            repo,
            tool_result=ToolResult(
                tool_call_id="toolu_fail",
                content="FAILED tests/test_app.py::test_run - KeyError: 'username'",
                is_error=True,
                error_signature="abc123def4567890",
                exit_code=1,
            ),
        ),
        _event(
            3,
            repo,
            tool_call=ToolCall(
                tool_name="Bash",
                tool_call_id="toolu_pass",
                args={"command": "pytest tests/test_app.py -q"},
            ),
        ),
        _event(
            4,
            repo,
            tool_result=ToolResult(
                tool_call_id="toolu_pass",
                content="1 passed in 0.10s",
                is_error=False,
                error_signature=None,
                exit_code=None,
            ),
        ),
    ]
    candidate = Harvester(settings, FakePromptClient()).harvest(events, "fixlog-session")
    assert candidate is not None
    assert candidate.fixlog_session_id == "fixlog-session"
    assert candidate.failing_command == "pytest tests/test_app.py -q"
    assert candidate.reproduction_verify == "pytest tests/test_app.py -q"
    assert "payload" in candidate.fix_diff
    loaded = load_pending_harvests(pending)
    assert len(loaded) == 1
    assert loaded[0].id == candidate.id


def test_harvester_returns_none_without_diff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_repo(repo)
    subprocess.run(["git", "checkout", "--", "app.py"], cwd=repo, check=True)
    settings = HarnessSettings(FIXLOG_PENDING_HARVEST_DIR=tmp_path / "pending")
    events = [
        _event(
            1,
            repo,
            tool_result=ToolResult(
                tool_call_id="toolu_fail",
                content="Traceback (most recent call last):\nValueError: broken",
                is_error=True,
                error_signature="abc123def4567890",
                exit_code=1,
            ),
        )
    ]
    assert Harvester(settings, FakePromptClient()).harvest(events) is None


def test_harvester_does_not_write_pending_when_auto_submit_enabled(
    tmp_path: Path,
) -> None:
    pending = tmp_path / "pending"
    cwd = tmp_path / "repo"
    cwd.mkdir()
    _git_repo(cwd)
    settings = HarnessSettings(
        FIXLOG_PENDING_HARVEST_DIR=pending,
        FIXLOG_API_TOKEN="token",
        FIXLOG_AUTO_SUBMIT_HARVESTS=True,
    )

    events = [
        _event(
            1,
            cwd,
            tool_call=ToolCall(
                tool_name="Bash",
                tool_call_id="toolu_fail",
                args={"command": "pytest tests/test_app.py -q"},
            ),
        ),
        _event(
            2,
            cwd,
            tool_result=ToolResult(
                tool_call_id="toolu_fail",
                content="FAILED tests/test_app.py::test_run - KeyError: 'username'",
                is_error=True,
                error_signature="abc123def4567890",
                exit_code=1,
            ),
        ),
    ]
    candidate = Harvester(settings, FakePromptClient()).harvest(events, "fixlog-session")

    assert candidate is not None
    assert candidate.pending_path is None
    assert not pending.exists()
