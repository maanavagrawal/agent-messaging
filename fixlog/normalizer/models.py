from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ErrorKind(StrEnum):
    TRACEBACK = "traceback"
    PYTEST = "pytest"
    PIP = "pip"
    GENERIC = "generic"


class PythonErrorSignature(BaseModel):
    model_config = ConfigDict(frozen=True)

    exception_type: str = Field(min_length=1)
    exception_message: str
    last_frame_function: str | None = None
    last_frame_module: str | None = None
    traceback_shape: list[tuple[str, str]] = Field(default_factory=list, max_length=3)
    canonical_string: str = Field(min_length=1)
    hash: str = Field(pattern=r"^[0-9a-f]{16}$")
    error_kind: ErrorKind
    was_chained: bool = False


@dataclass(frozen=True)
class ParsedError:
    exception_type: str
    exception_message: str
    error_kind: ErrorKind
    last_frame_function: str | None = None
    last_frame_module: str | None = None
    traceback_shape: list[tuple[str, str]] = field(default_factory=list)
    was_chained: bool = False
    canonical_string_override: str | None = None
