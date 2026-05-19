from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


SourceTool = Literal["claude_code"]
EventKind = Literal[
    "session_start",
    "user_message",
    "agent_message",
    "tool_call",
    "tool_result",
    "session_end",
]


class ToolCall(BaseModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    tool_call_id: str


class ToolResult(BaseModel):
    tool_call_id: str
    content: str
    is_error: bool
    error_signature: str | None = None
    exit_code: int | None = None


class NormalizedEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_tool: SourceTool
    source_session_id: str
    source_event_id: str
    ts: datetime
    kind: EventKind
    cwd: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    project_slug: str | None = None
    text: str | None = None
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    redacted: bool = False


class StuckSignalKind(StrEnum):
    REPEATED_ERROR = "repeated_error"
    THRASHING = "thrashing"


class StuckSignal(BaseModel):
    kind: StuckSignalKind
    ts: datetime
    source_tool: SourceTool
    source_session_id: str
    error_signature: str | None = None
    reason: str
    event_ids: list[str] = Field(default_factory=list)


class CandidateEntry(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    source_tool: SourceTool
    source_session_id: str
    fixlog_session_id: str | None = None
    cwd: str
    project_slug: str | None = None
    git_commit: str | None = None
    error_signature: str
    raw_error_text: str
    failing_command: str
    verification_command: str | None = None
    fix_diff: str
    diagnosis: str
    reproduction_setup: str
    reproduction_trigger: str
    reproduction_verify: str
    pending_path: Path | None = None


class SessionMapping(BaseModel):
    fixlog_session_id: str
    fixlog_persona_id: str
    started_at: datetime
