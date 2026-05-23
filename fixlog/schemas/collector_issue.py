from __future__ import annotations

from pydantic import BaseModel, Field

from fixlog.schemas.common import AgentMetadata, EnvContext
from fixlog.schemas.error_signature import ErrorSignatureInput


class CollectorIssueCreate(BaseModel):
    error_signature: ErrorSignatureInput
    env_context: EnvContext
    attempts_made: list[str] = Field(default_factory=list)
    agent_metadata: AgentMetadata
