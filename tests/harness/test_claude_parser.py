from __future__ import annotations

from pathlib import Path

from fixlog_harness.parsers.claude_code import ClaudeCodeLogParser
from fixlog_harness.redaction import REDACTED_SENSITIVE_FILE_CONTENTS

FIXTURES = Path(__file__).parent / "fixtures" / "claude_code"


def _parse_fixture(name: str):
    parser = ClaudeCodeLogParser()
    events = parser.initial_events_from_file_header(FIXTURES / name)
    for line in (FIXTURES / name).read_text().splitlines():
        events.extend(parser.parse_line(line))
    return events


def test_parses_text_tool_call_and_tool_result() -> None:
    events = _parse_fixture("simple_session.jsonl")
    assert [event.kind for event in events] == [
        "session_start",
        "user_message",
        "agent_message",
        "tool_call",
        "tool_result",
    ]
    assert events[0].source_tool == "claude_code"
    assert events[0].source_session_id == "claude-session-simple"
    assert events[0].project_slug == "simple-project"
    assert events[3].tool_call is not None
    assert events[3].tool_call.tool_name == "Read"
    assert events[4].tool_result is not None
    assert events[4].tool_result.is_error is False


def test_bash_success_result_is_not_error() -> None:
    events = _parse_fixture("tool_use_with_bash.jsonl")
    result = events[-1].tool_result
    assert result is not None
    assert result.is_error is False
    assert result.exit_code is None


def test_python_traceback_result_gets_error_signature_hash() -> None:
    events = _parse_fixture("tool_use_with_error.jsonl")
    result = events[-1].tool_result
    assert result is not None
    assert result.is_error is True
    assert result.exit_code == 1
    assert result.error_signature is not None
    assert len(result.error_signature) == 16


def test_sidechain_events_are_normalized_not_special_cased_downstream() -> None:
    events = _parse_fixture("sidechain_session.jsonl")
    assert [event.kind for event in events] == ["session_start", "agent_message"]
    assert events[-1].text == "Sidechain analysis result."


def test_env_read_result_is_fully_redacted_before_return() -> None:
    events = _parse_fixture("env_leak_redaction.jsonl")
    result_event = events[-1]
    assert result_event.redacted is True
    assert result_event.tool_result is not None
    assert result_event.tool_result.content == REDACTED_SENSITIVE_FILE_CONTENTS
    assert "sk-proj" not in result_event.model_dump_json()


def test_skips_non_relevant_event_types() -> None:
    parser = ClaudeCodeLogParser()
    events = parser.parse_line('{"type":"ai-title","title":"skip me"}')
    assert events == []
