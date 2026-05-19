from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from fixlog.schemas.common import ORMModel


class LanguageSchema(StrEnum):
    PYTHON = "python"


class ErrorKindSchema(StrEnum):
    TRACEBACK = "traceback"
    PYTEST = "pytest"
    PIP = "pip"
    GENERIC = "generic"


class ErrorSignatureInput(BaseModel):
    raw_text: str = Field(min_length=1)
    raw_examples: list[str] = Field(default_factory=list)
    language: str = Field(min_length=1)
    framework: str | None = None


class ErrorSignatureRead(ORMModel):
    id: UUID
    canonical_string: str
    hash: str
    raw_examples: list[str]
    language: LanguageSchema
    framework: str | None
    exception_type: str | None
    exception_message: str | None
    last_frame_module: str | None
    last_frame_function: str | None
    traceback_shape: list[tuple[str, str]] | None
    error_kind: ErrorKindSchema | None
    was_chained: bool | None
