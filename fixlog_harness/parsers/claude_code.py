from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fixlog.normalizer.python import normalize_python_error
from fixlog_harness.models import EventKind, NormalizedEvent, ToolCall, ToolResult
from fixlog_harness.parsers.base import LogParser
from fixlog_harness.redaction import (
    redact_event,
    redact_sensitive_tool_result,
    tool_call_reads_sensitive_path,
)

logger = logging.getLogger(__name__)

SKIPPED_EVENT_TYPES = {
    "queue-operation",
    "attachment",
    "file-history-snapshot",
    "ai-title",
    "last-prompt",
}

# Matches line-start error labels in command output without matching inline words.
LINE_START_ERROR_RE = re.compile(r"(?mi)^\s*(error|ERROR|Error):")

# Matches common shell wrappers that report a non-zero process exit.
EXIT_CODE_RE = re.compile(
    r"(?i)(?:exit code|exit status|return code|status)\s*[:=]?\s*(?P<code>[1-9][0-9]*)"
)

# Matches TypeScript compiler errors like "error TS2322:".
TYPESCRIPT_ERROR_RE = re.compile(r"error TS\d+:", re.IGNORECASE)

# Matches pytest's concise failure lines.
PYTEST_FAILURE_RE = re.compile(r"FAILED\s+tests/", re.IGNORECASE)


class ClaudeCodeLogParser(LogParser):
    def __init__(self) -> None:
        self._cwd: str | None = None
        self._git_branch: str | None = None
        self._git_commit: str | None = None
        self._project_slug: str | None = None
        self._session_id: str | None = None
        self._sensitive_tool_call_ids: set[str] = set()

    def parse_line(self, line: str) -> list[NormalizedEvent]:
        raw = _loads_event(line)
        if raw is None or raw.get("type") in SKIPPED_EVENT_TYPES:
            return []
        if raw.get("type") not in {"user", "assistant"}:
            return []

        self._update_context(raw)
        content = raw.get("message", {}).get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list):
            return []

        events: list[NormalizedEvent] = []
        for index, item in enumerate(content):
            if not isinstance(item, dict):
                continue
            event = self._event_from_content(raw, item, index)
            if event is not None:
                events.append(event)
        return events

    def initial_events_from_file_header(self, file_path: Path) -> list[NormalizedEvent]:
        for line in file_path.read_text().splitlines():
            raw = _loads_event(line)
            if raw is None or raw.get("type") in SKIPPED_EVENT_TYPES:
                continue
            if raw.get("type") not in {"user", "assistant"}:
                continue
            self._update_context(raw)
            session_id = self._session_id
            if session_id is None:
                return []
            ts = _parse_ts(raw.get("timestamp"))
            event = self._base_event(
                raw,
                kind="session_start",
                source_event_id=f"{session_id}:session_start",
                ts=ts,
            )
            return [redact_event(event)]
        return []

    def _event_from_content(
        self, raw: dict[str, Any], item: dict[str, Any], index: int
    ) -> NormalizedEvent | None:
        content_type = item.get("type")
        if content_type == "text":
            text = item.get("text")
            if not isinstance(text, str) or not text:
                return None
            role = raw.get("message", {}).get("role") or raw.get("type")
            kind = "user_message" if role == "user" else "agent_message"
            return redact_event(
                self._base_event(raw, kind=kind, source_event_id=_event_id(raw, index), text=text)
            )

        if content_type == "tool_use":
            tool_id = item.get("id")
            tool_name = item.get("name")
            args = item.get("input") if isinstance(item.get("input"), dict) else {}
            if not isinstance(tool_id, str) or not isinstance(tool_name, str):
                return None
            tool_call = ToolCall(tool_name=tool_name, args=args, tool_call_id=tool_id)
            if tool_call_reads_sensitive_path(tool_call):
                self._sensitive_tool_call_ids.add(tool_id)
            event = self._base_event(
                raw,
                kind="tool_call",
                source_event_id=tool_id,
                tool_call=tool_call,
            )
            return redact_event(event)

        if content_type == "tool_result":
            tool_call_id = item.get("tool_use_id")
            if not isinstance(tool_call_id, str):
                return None
            content = _tool_result_content(item.get("content"))
            tool_result = _build_tool_result(tool_call_id, content)
            event = self._base_event(
                raw,
                kind="tool_result",
                source_event_id=f"{tool_call_id}:result",
                tool_result=tool_result,
            )
            if tool_call_id in self._sensitive_tool_call_ids:
                return redact_sensitive_tool_result(event)
            return redact_event(event)

        return None

    def _update_context(self, raw: dict[str, Any]) -> None:
        session_id = raw.get("sessionId")
        if isinstance(session_id, str):
            self._session_id = session_id
        cwd = raw.get("cwd")
        if isinstance(cwd, str):
            if cwd != self._cwd:
                self._cwd = cwd
                self._project_slug = Path(cwd).name or None
                self._git_commit = _git_commit_for_cwd(cwd)
        branch = raw.get("gitBranch")
        if isinstance(branch, str):
            self._git_branch = branch

    def _base_event(
        self,
        raw: dict[str, Any],
        *,
        kind: EventKind,
        source_event_id: str,
        ts: datetime | None = None,
        text: str | None = None,
        tool_call: ToolCall | None = None,
        tool_result: ToolResult | None = None,
    ) -> NormalizedEvent:
        session_id = self._session_id or str(raw.get("sessionId") or "unknown")
        return NormalizedEvent(
            source_tool="claude_code",
            source_session_id=session_id,
            source_event_id=source_event_id,
            ts=ts or _parse_ts(raw.get("timestamp")),
            kind=kind,
            cwd=self._cwd,
            git_branch=self._git_branch,
            git_commit=self._git_commit,
            project_slug=self._project_slug,
            text=text,
            tool_call=tool_call,
            tool_result=tool_result,
            redacted=False,
        )


def _loads_event(line: str) -> dict[str, Any] | None:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _parse_ts(value: object) -> datetime:
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return datetime.now(UTC)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return datetime.now(UTC)


def _event_id(raw: dict[str, Any], index: int) -> str:
    base = raw.get("uuid")
    return f"{base}:{index}" if isinstance(base, str) else f"unknown:{index}"


def _tool_result_content(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def _build_tool_result(tool_call_id: str, content: str) -> ToolResult:
    exit_code = _extract_exit_code(content)
    is_error = _is_error_content(content, exit_code)
    error_signature: str | None = None
    if is_error and _is_python_error_content(content):
        error_signature = normalize_python_error(content).hash
    return ToolResult(
        tool_call_id=tool_call_id,
        content=content,
        is_error=is_error,
        error_signature=error_signature,
        exit_code=exit_code,
    )


def _extract_exit_code(content: str) -> int | None:
    match = EXIT_CODE_RE.search(content)
    return int(match.group("code")) if match else None


def _is_error_content(content: str, exit_code: int | None) -> bool:
    return (
        "Traceback (most recent call last):" in content
        or bool(LINE_START_ERROR_RE.search(content))
        or exit_code is not None
        or bool(PYTEST_FAILURE_RE.search(content))
        or bool(TYPESCRIPT_ERROR_RE.search(content))
    )


def _is_python_error_content(content: str) -> bool:
    return "Traceback (most recent call last):" in content or bool(
        PYTEST_FAILURE_RE.search(content)
    )


def _git_commit_for_cwd(cwd: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None
