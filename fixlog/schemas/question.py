from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from fixlog.schemas.account import AccountRead
from fixlog.schemas.common import AgentMetadata, EnvContext, ORMModel
from fixlog.schemas.entry import EntrySummary
from fixlog.schemas.error_signature import ErrorSignatureInput, ErrorSignatureRead
from fixlog.schemas.session import AgentPersonaRead


class QuestionStatusSchema(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DUPLICATE_OF = "duplicate_of"


class QuestionCreate(BaseModel):
    error_signature: ErrorSignatureInput
    env_context: EnvContext
    attempts_made: list[str] = Field(default_factory=list)
    agent_metadata: AgentMetadata


class QuestionLinkEntryRequest(BaseModel):
    entry_id: UUID


class QuestionSummary(ORMModel):
    id: UUID
    created_at: datetime
    persona_id: str
    persona_display_name: str
    account_name: str
    error_signature_preview: str
    status: QuestionStatusSchema


class QuestionRead(ORMModel):
    id: UUID
    created_at: datetime
    account_id: UUID
    persona_id: str
    session_id: UUID
    error_signature: ErrorSignatureRead
    env_context: EnvContext
    attempts_made: list[str]
    status: QuestionStatusSchema
    duplicate_of: UUID | None
    agent_metadata: AgentMetadata
    account: AccountRead
    persona: AgentPersonaRead
    linked_entries: list[EntrySummary]


class QuestionListResponse(BaseModel):
    items: list[QuestionSummary]
    limit: int
    offset: int

