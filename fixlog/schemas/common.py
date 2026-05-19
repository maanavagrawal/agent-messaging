from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EnvContext(BaseModel):
    language_version: str
    framework_version: str | None = None
    key_deps: dict[str, str] = Field(default_factory=dict)
    os: str | None = None


class AgentMetadata(BaseModel):
    model: str
    harness: str
    tools_available: list[str] = Field(default_factory=list)


class OkResponse(BaseModel):
    ok: Literal[True] = True


class Pagination(BaseModel):
    limit: int
    offset: int
    total: int | None = None

