from __future__ import annotations

import json
import re
from typing import Any

from pydantic import TypeAdapter

from fixlog_harness.models import NormalizedEvent, ToolCall, ToolResult

REDACTED_API_KEY = "<REDACTED_API_KEY>"
REDACTED_GITHUB_TOKEN = "<REDACTED_GITHUB_TOKEN>"
REDACTED_SLACK_TOKEN = "<REDACTED_SLACK_TOKEN>"
REDACTED_AWS_KEY = "<REDACTED_AWS_KEY>"
REDACTED_JWT = "<REDACTED_JWT>"
REDACTED_ENV_VALUE = "<REDACTED_ENV_VALUE>"
REDACTED_HIGH_ENTROPY_STRING = "<REDACTED_HIGH_ENTROPY_STRING>"
REDACTED_SENSITIVE_FILE_CONTENTS = "<REDACTED_SENSITIVE_FILE_CONTENTS>"


class RedactionResult:
    def __init__(self, value: Any, redacted: bool) -> None:
        self.value = value
        self.redacted = redacted


# Matches OpenAI project-scoped API keys. Keep before the generic sk- rule.
OPENAI_PROJECT_KEY_RE = re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}")

# Matches OpenAI-style API keys that start with sk- but are not project scoped.
OPENAI_KEY_RE = re.compile(r"sk-[A-Za-z0-9_-]{20,}")

# Matches GitHub classic and OAuth tokens with the documented ghp_/gho_ prefixes.
GITHUB_TOKEN_RE = re.compile(r"gh[po]_[A-Za-z0-9]{20,}")

# Matches Slack bot tokens. It intentionally does not match user/oauth variants yet.
SLACK_TOKEN_RE = re.compile(r"xoxb-[A-Za-z0-9-]{20,}")

# Matches AWS access key ids. Secret access keys are caught by entropy fallback.
AWS_KEY_RE = re.compile(r"AKIA[0-9A-Z]{16}")

# Matches three-segment JWTs beginning with a JSON header segment.
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

# Matches env-file assignment lines with uppercase keys and long non-space values.
ENV_VALUE_RE = re.compile(
    r"(?m)^(?P<key>[A-Z_][A-Z0-9_]*\s*=\s*)"
    r"(?P<quote>['\"]?)"
    r"(?P<value>[^'\"\s]{8,})"
)

# Matches candidate high-entropy strings made of token-like characters.
HIGH_ENTROPY_RE = re.compile(r"\b[A-Za-z0-9_+/=-]{40,}\b")

# Matches paths or path fragments that usually contain secrets.
SENSITIVE_PATH_RE = re.compile(
    r"(^|/|\\)(\.env[^/\\]*|.*secrets?.*|.*credentials?.*|id_rsa|.*\.pem)$",
    re.IGNORECASE,
)

_STRING_DICT_MARKERS = (
    "traceback",
    "exception",
    "python",
    "package",
    "version",
    "command",
    "session",
    "request",
    "function",
)


def tool_call_reads_sensitive_path(tool_call: ToolCall) -> bool:
    """Return true when a tool call references a known sensitive file path."""
    if tool_call.tool_name.lower() != "read":
        return False
    for value in _flatten_values(tool_call.args):
        if isinstance(value, str) and SENSITIVE_PATH_RE.search(value):
            return True
    return False


def redact_sensitive_tool_result(event: NormalizedEvent) -> NormalizedEvent:
    """Replace a sensitive file read result with a fixed placeholder."""
    if event.tool_result is None:
        return event
    result = event.tool_result.model_copy(
        update={"content": REDACTED_SENSITIVE_FILE_CONTENTS}
    )
    return event.model_copy(update={"tool_result": result, "redacted": True})


def redact_event(event: NormalizedEvent) -> NormalizedEvent:
    """Redact text, tool call args, and tool result content in a normalized event."""
    redacted = event.redacted
    updates: dict[str, Any] = {}

    if event.text is not None:
        result = redact_value(event.text)
        updates["text"] = result.value
        redacted = redacted or result.redacted

    if event.tool_call is not None:
        result = redact_value(event.tool_call.args)
        updates["tool_call"] = event.tool_call.model_copy(update={"args": result.value})
        redacted = redacted or result.redacted

    if event.tool_result is not None:
        result = redact_value(event.tool_result.content)
        updates["tool_result"] = event.tool_result.model_copy(
            update={"content": result.value}
        )
        redacted = redacted or result.redacted

    updates["redacted"] = redacted
    return event.model_copy(update=updates)


def redact_value(value: Any) -> RedactionResult:
    """Recursively redact strings inside JSON-like data."""
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, list):
        redacted = False
        items = []
        for item in value:
            result = redact_value(item)
            redacted = redacted or result.redacted
            items.append(result.value)
        return RedactionResult(items, redacted)
    if isinstance(value, dict):
        redacted = False
        items: dict[str, Any] = {}
        for key, item in value.items():
            result = redact_value(item)
            redacted = redacted or result.redacted
            items[str(key)] = result.value
        return RedactionResult(items, redacted)
    return RedactionResult(value, False)


def _redact_string(value: str) -> RedactionResult:
    redacted = False
    replacements = [
        (OPENAI_PROJECT_KEY_RE, REDACTED_API_KEY),
        (OPENAI_KEY_RE, REDACTED_API_KEY),
        (GITHUB_TOKEN_RE, REDACTED_GITHUB_TOKEN),
        (SLACK_TOKEN_RE, REDACTED_SLACK_TOKEN),
        (AWS_KEY_RE, REDACTED_AWS_KEY),
        (JWT_RE, REDACTED_JWT),
    ]
    output = value
    for pattern, replacement in replacements:
        output, count = pattern.subn(replacement, output)
        redacted = redacted or count > 0

    output, env_count = ENV_VALUE_RE.subn(
        lambda match: f"{match.group('key')}{match.group('quote')}{REDACTED_ENV_VALUE}",
        output,
    )
    redacted = redacted or env_count > 0

    output, entropy_redacted = _redact_high_entropy(output)
    return RedactionResult(output, redacted or entropy_redacted)


def _redact_high_entropy(value: str) -> tuple[str, bool]:
    redacted = False

    def replace(match: re.Match[str]) -> str:
        nonlocal redacted
        candidate = match.group(0)
        if _is_allowed_hash(candidate) or not _looks_high_entropy(candidate):
            return candidate
        redacted = True
        return REDACTED_HIGH_ENTROPY_STRING

    return HIGH_ENTROPY_RE.sub(replace, value), redacted


def _looks_high_entropy(value: str) -> bool:
    if "/" in value or "\\" in value:
        return False
    lowered = value.lower()
    if any(marker in lowered for marker in _STRING_DICT_MARKERS):
        return False
    classes = 0
    classes += any(char.islower() for char in value)
    classes += any(char.isupper() for char in value)
    classes += any(char.isdigit() for char in value)
    classes += any(not char.isalnum() for char in value)
    return classes >= 3


def _is_allowed_hash(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{40}", value) or re.fullmatch(r"[0-9a-f]{64}", value))


def _flatten_values(value: Any) -> list[Any]:
    if isinstance(value, dict):
        flattened: list[Any] = []
        for item in value.values():
            flattened.extend(_flatten_values(item))
        return flattened
    if isinstance(value, list):
        flattened = []
        for item in value:
            flattened.extend(_flatten_values(item))
        return flattened
    return [value]


def redact_jsonable(value: Any) -> tuple[Any, bool]:
    """Redact a JSON-like value and verify it remains JSON serializable."""
    result = redact_value(value)
    json.dumps(result.value)
    return TypeAdapter(Any).validate_python(result.value), result.redacted
