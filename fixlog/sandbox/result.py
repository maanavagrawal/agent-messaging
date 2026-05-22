from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

OUTPUT_LIMIT_BYTES = 64 * 1024


def cap_output(value: str) -> str:
    data = value.encode("utf-8", errors="replace")
    if len(data) <= OUTPUT_LIMIT_BYTES:
        return value
    capped = data[:OUTPUT_LIMIT_BYTES].decode("utf-8", errors="replace")
    return f"{capped}\n<TRUNCATED_TO_64KB>"


class SandboxResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exit_code: int
    stdout: str = Field(default="")
    stderr: str = Field(default="")
    duration_ms: int
    timed_out: bool
    oom_killed: bool
    image_pulled: bool

    @field_validator("stdout", "stderr")
    @classmethod
    def cap_text_output(cls, value: str) -> str:
        return cap_output(value)

