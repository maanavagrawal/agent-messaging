from __future__ import annotations

from dataclasses import dataclass


DEFAULT_ALLOWED_IMAGES = (
    "python:3.11-slim",
    "python:3.12-slim",
    "node:20-slim",
    "node:22-slim",
)


@dataclass(frozen=True)
class SandboxLimits:
    timeout_s: int = 60
    memory_mb: int = 512
    cpu_count: float = 1.0
    pids_limit: int = 128
    workspace_tmpfs_mb: int = 128

