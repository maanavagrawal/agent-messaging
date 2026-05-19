from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from fixlog.schemas.common import ORMModel


class SessionStartRequest(BaseModel):
    model_name: str
    harness_name: str
    source_tool: str | None = None
    source_tool_session_id: str | None = None


class SessionStartResponse(BaseModel):
    session_id: UUID
    persona_id: str
    persona_display_name: str
    account_reputation: float = 0.0
    persona_reputation: float = 0.0


class SessionHeartbeatResponse(BaseModel):
    ok: bool = True


class AgentPersonaRead(ORMModel):
    id: str
    account_id: UUID
    display_name: str
    model_name: str
    harness_name: str
    first_seen: datetime
    last_seen: datetime


class SessionRead(ORMModel):
    id: UUID
    persona_id: str
    started_at: datetime
    ended_at: datetime | None
    last_heartbeat: datetime
    source_tool: str | None = None
    source_tool_session_id: str | None = None
