from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from fixlog.schemas.common import ORMModel


class LanguageSchema(StrEnum):
    PYTHON = "python"


class ErrorSignatureInput(BaseModel):
    canonical_string: str
    raw_examples: list[str] = Field(default_factory=list)
    language: LanguageSchema
    framework: str | None = None


class ErrorSignatureRead(ORMModel):
    id: UUID
    canonical_string: str
    hash: str
    raw_examples: list[str]
    language: LanguageSchema
    framework: str | None

