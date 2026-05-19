from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from fixlog.schemas.common import EnvContext, ORMModel


class VerifierKindSchema(StrEnum):
    AUTO_SANDBOX = "auto_sandbox"
    AGENT_IN_CONTEXT = "agent_in_context"
    AGENT_OUT_OF_CONTEXT = "agent_out_of_context"
    HUMAN_CLI = "human_cli"


class VerificationResultSchema(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


class VerificationCreate(BaseModel):
    verifier_kind: VerifierKindSchema
    result: VerificationResultSchema
    env_snapshot: EnvContext
    notes: str | None = None


class ConfirmRequest(BaseModel):
    entry_id: UUID


class RejectRequest(BaseModel):
    entry_id: UUID
    reason: str


class VerificationRead(ORMModel):
    id: UUID
    entry_id: UUID
    ts: datetime
    verifier_kind: VerifierKindSchema
    verifier_id: str
    result: VerificationResultSchema
    env_snapshot: EnvContext
    notes: str | None

