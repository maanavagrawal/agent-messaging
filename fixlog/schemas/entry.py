from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from fixlog.schemas.account import AccountRead
from fixlog.schemas.common import EnvContext, ORMModel
from fixlog.schemas.edit import EditRead
from fixlog.schemas.error_signature import ErrorSignatureInput, ErrorSignatureRead
from fixlog.schemas.session import AgentPersonaRead
from fixlog.schemas.verification import VerificationRead


class SandboxKindSchema(StrEnum):
    DOCKER = "docker"
    VENV = "venv"
    NODE = "node"
    NONE = "none"


class EntryCreate(BaseModel):
    error_signature: ErrorSignatureInput
    also_matches: list[ErrorSignatureInput] = Field(default_factory=list)
    env_context: EnvContext
    diagnosis: str
    fix_diff: str
    fix_explanation: str | None = Field(default=None, max_length=500)
    reproduction_setup: str
    reproduction_trigger: str
    reproduction_verify: str
    sandbox_kind: SandboxKindSchema
    sandbox_spec: str
    tags: list[str] = Field(default_factory=list)


class EntrySummary(ORMModel):
    id: UUID
    created_at: datetime
    persona_id: str
    persona_display_name: str
    account_name: str
    error_signature_preview: str
    verification_count: int
    superseded_by: UUID | None
    tags: list[str]


class EntryRead(ORMModel):
    id: UUID
    created_at: datetime
    account_id: UUID
    persona_id: str
    session_id: UUID
    error_signature: ErrorSignatureRead
    also_matches: list[ErrorSignatureRead]
    env_context: EnvContext
    diagnosis: str
    fix_diff: str
    fix_explanation: str | None
    reproduction_setup: str
    reproduction_trigger: str
    reproduction_verify: str
    sandbox_kind: SandboxKindSchema
    sandbox_spec: str
    superseded_by: UUID | None
    tags: list[str]
    account: AccountRead
    persona: AgentPersonaRead
    verification_log: list[VerificationRead]
    edit_history: list[EditRead]


class EntryListResponse(BaseModel):
    items: list[EntrySummary]
    limit: int
    offset: int

