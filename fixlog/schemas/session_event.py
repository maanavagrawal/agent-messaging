from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from fixlog.schemas.common import ORMModel


class SessionEventCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=80)
    ts: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class SessionEventCreateResponse(BaseModel):
    event_id: UUID


class SessionEventRead(ORMModel):
    id: UUID
    session_id: UUID
    ts: datetime
    kind: str
    payload: dict[str, Any]


class SessionEventListResponse(BaseModel):
    items: list[SessionEventRead]
    limit: int
    offset: int


class ActiveSessionSummary(BaseModel):
    session_id: UUID
    persona_id: str
    persona_display_name: str
    account_name: str
    source_tool: str | None
    source_tool_session_id: str | None
    project_slug: str | None
    event_count_last_hour: int
    redaction_count: int
    stuck_emitted: bool
    last_event_at: datetime


class ActiveSessionsResponse(BaseModel):
    items: list[ActiveSessionSummary]
