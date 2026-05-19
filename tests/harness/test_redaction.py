from __future__ import annotations

from datetime import UTC, datetime

from fixlog_harness.models import NormalizedEvent, ToolCall, ToolResult
from fixlog_harness.redaction import (
    REDACTED_API_KEY,
    REDACTED_AWS_KEY,
    REDACTED_ENV_VALUE,
    REDACTED_GITHUB_TOKEN,
    REDACTED_HIGH_ENTROPY_STRING,
    REDACTED_JWT,
    REDACTED_SENSITIVE_FILE_CONTENTS,
    REDACTED_SLACK_TOKEN,
    redact_event,
    redact_sensitive_tool_result,
    tool_call_reads_sensitive_path,
)


def _event(**updates: object) -> NormalizedEvent:
    base: dict[str, object] = {
        "source_tool": "claude_code",
        "source_session_id": "session-1",
        "source_event_id": "event-1",
        "ts": datetime.now(UTC),
        "kind": "agent_message",
        "redacted": False,
    }
    base.update(updates)
    return NormalizedEvent.model_validate(base)


def test_redacts_known_api_key_shapes() -> None:
    text = (
        "sk-proj-abcdefghijklmnopqrstuvwxyz123456 "
        "sk-abcdefghijklmnopqrstuvwxyz123456 "
        "ghp_abcdefghijklmnopqrstuvwxyz123456 "
        "gho_abcdefghijklmnopqrstuvwxyz123456 "
        "xoxb-abcdefghijklmnopqrstuvwx-123456 "
        "AKIA1234567890ABCDEF "
        "eyJabc.eyJdef.signature_part"
    )
    redacted = redact_event(_event(text=text))
    assert redacted.redacted is True
    assert redacted.text is not None
    assert REDACTED_API_KEY in redacted.text
    assert REDACTED_GITHUB_TOKEN in redacted.text
    assert REDACTED_SLACK_TOKEN in redacted.text
    assert REDACTED_AWS_KEY in redacted.text
    assert REDACTED_JWT in redacted.text


def test_redacts_env_file_values_at_line_boundaries() -> None:
    redacted = redact_event(
        _event(text="DATABASE_URL=postgres://example\nTOKEN='abcdefghijklmno'\n")
    )
    assert redacted.redacted is True
    assert redacted.text == (
        f"DATABASE_URL={REDACTED_ENV_VALUE}\n"
        f"TOKEN='{REDACTED_ENV_VALUE}'\n"
    )


def test_redacts_tool_call_args_recursively() -> None:
    event = _event(
        kind="tool_call",
        tool_call=ToolCall(
            tool_name="Bash",
            tool_call_id="toolu_1",
            args={"env": {"OPENAI_API_KEY": "sk-abcdefghijklmnopqrstuvwxyz123456"}},
        ),
    )
    redacted = redact_event(event)
    assert redacted.redacted is True
    assert redacted.tool_call is not None
    assert redacted.tool_call.args["env"]["OPENAI_API_KEY"] == REDACTED_API_KEY


def test_sensitive_read_tool_result_is_replaced_whole() -> None:
    call = ToolCall(tool_name="Read", tool_call_id="toolu_1", args={"file_path": ".env"})
    assert tool_call_reads_sensitive_path(call) is True
    event = _event(
        kind="tool_result",
        tool_result=ToolResult(
            tool_call_id="toolu_1",
            content="DATABASE_URL=postgres://example",
            is_error=False,
        ),
    )
    redacted = redact_sensitive_tool_result(event)
    assert redacted.redacted is True
    assert redacted.tool_result is not None
    assert redacted.tool_result.content == REDACTED_SENSITIVE_FILE_CONTENTS


def test_high_entropy_fallback_spares_common_hashes() -> None:
    git_sha = "a" * 40
    sha256 = "b" * 64
    secret = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_+/=-ABCDE"
    redacted = redact_event(_event(text=f"{git_sha} {sha256} {secret}"))
    assert redacted.redacted is True
    assert git_sha in (redacted.text or "")
    assert sha256 in (redacted.text or "")
    assert REDACTED_HIGH_ENTROPY_STRING in (redacted.text or "")


def test_non_sensitive_read_path_is_not_flagged() -> None:
    call = ToolCall(tool_name="Read", tool_call_id="toolu_1", args={"file_path": "app.py"})
    assert tool_call_reads_sensitive_path(call) is False
