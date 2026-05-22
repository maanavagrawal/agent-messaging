from __future__ import annotations

import json
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SandboxKind = Literal["docker", "venv", "node", "none"]

DEFAULT_BASE_IMAGES: dict[str, str | None] = {
    "docker": "python:3.11-slim",
    "venv": "python:3.11-slim",
    "node": "node:20-slim",
    "none": None,
}

MAX_SPEC_FILE_BYTES = 512 * 1024
MAX_SPEC_FILE_COUNT = 100
MAX_SPEC_TOTAL_FILE_BYTES = 2 * 1024 * 1024


class SandboxSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SandboxKind
    base_image: str | None = None
    setup_commands: list[str] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)

    @field_validator("setup_commands")
    @classmethod
    def clean_setup_commands(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @field_validator("files")
    @classmethod
    def validate_files(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > MAX_SPEC_FILE_COUNT:
            raise ValueError(f"sandbox file count too large: {len(value)}")
        clean: dict[str, str] = {}
        total_bytes = 0
        for path, content in value.items():
            parts = path.split("/")
            if (
                not path
                or path.startswith("/")
                or ".." in parts
                or "\x00" in path
                or path.endswith("/")
            ):
                raise ValueError(f"unsafe sandbox file path: {path}")
            if len(content.encode("utf-8", errors="replace")) > MAX_SPEC_FILE_BYTES:
                raise ValueError(f"sandbox file content too large: {path}")
            total_bytes += len(content.encode("utf-8", errors="replace"))
            if total_bytes > MAX_SPEC_TOTAL_FILE_BYTES:
                raise ValueError("sandbox total file content too large")
            clean[path] = content
        return clean

    @model_validator(mode="after")
    def validate_base_image(self) -> SandboxSpec:
        if self.kind in {"docker", "venv", "node"} and not self.base_image:
            raise ValueError(f"base_image is required for sandbox kind {self.kind}")
        if self.kind == "none" and self.base_image is not None:
            raise ValueError("base_image must be omitted for sandbox kind none")
        return self


def build_sandbox_spec(sandbox_kind: str, sandbox_spec: str) -> SandboxSpec:
    kind = sandbox_kind.strip()
    raw = sandbox_spec.strip()
    if raw.startswith("{"):
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("sandbox_spec JSON must be an object")
        payload.setdefault("kind", kind)
        payload.setdefault("base_image", DEFAULT_BASE_IMAGES.get(str(payload["kind"])))
        return SandboxSpec.model_validate(payload)
    if raw and kind in {"docker", "node", "venv"} and _looks_like_image(raw):
        return SandboxSpec(
            kind=cast(SandboxKind, kind),
            base_image=raw,
            setup_commands=[],
            files={},
        )
    return SandboxSpec(
        kind=cast(SandboxKind, kind),
        base_image=DEFAULT_BASE_IMAGES.get(kind),
        setup_commands=[] if raw in {"", "none"} else [raw],
        files={},
    )


def _looks_like_image(value: str) -> bool:
    return not any(char.isspace() for char in value) and (
        ":" in value or "/" in value
    )
