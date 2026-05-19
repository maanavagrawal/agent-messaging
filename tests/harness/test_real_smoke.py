from __future__ import annotations

import os
from pathlib import Path

import pytest

from fixlog_harness.parsers.claude_code import ClaudeCodeLogParser


@pytest.mark.skipif(
    os.environ.get("FIXLOG_E2E") != "1",
    reason="set FIXLOG_E2E=1 and FIXLOG_E2E_CLAUDE_LOG to run live Claude Code smoke",
)
def test_real_claude_code_log_can_be_parsed() -> None:
    log_path = os.environ.get("FIXLOG_E2E_CLAUDE_LOG")
    if not log_path:
        pytest.skip("FIXLOG_E2E_CLAUDE_LOG is required for the live smoke test")
    path = Path(log_path)
    parser = ClaudeCodeLogParser()
    events = parser.initial_events_from_file_header(path)
    for line in path.read_text().splitlines()[-50:]:
        events.extend(parser.parse_line(line))
    assert events
    assert all(event.redacted or event.model_dump_json() for event in events)
