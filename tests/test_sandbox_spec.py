from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from fixlog.sandbox.result import OUTPUT_LIMIT_BYTES, SandboxResult
from fixlog.sandbox.spec import SandboxSpec, build_sandbox_spec


def test_build_sandbox_spec_from_json() -> None:
    spec = build_sandbox_spec(
        "docker",
        json.dumps(
            {
                "base_image": "python:3.11-slim",
                "setup_commands": [" python -V ", ""],
                "files": {"app.py": "print('hello')"},
            }
        ),
    )

    assert spec.kind == "docker"
    assert spec.base_image == "python:3.11-slim"
    assert spec.setup_commands == ["python -V"]
    assert spec.files == {"app.py": "print('hello')"}


def test_build_sandbox_spec_from_legacy_text() -> None:
    spec = build_sandbox_spec("venv", "pip install pytest")

    assert spec.kind == "venv"
    assert spec.base_image == "python:3.11-slim"
    assert spec.setup_commands == ["pip install pytest"]
    assert spec.files == {}


def test_build_sandbox_spec_from_image_string() -> None:
    spec = build_sandbox_spec("docker", "python:3.11-slim")

    assert spec.kind == "docker"
    assert spec.base_image == "python:3.11-slim"
    assert spec.setup_commands == []


def test_sandbox_spec_rejects_unsafe_file_paths() -> None:
    with pytest.raises(ValidationError):
        SandboxSpec(
            kind="docker",
            base_image="python:3.11-slim",
            files={"../secret": "nope"},
        )


def test_sandbox_spec_rejects_too_many_files() -> None:
    with pytest.raises(ValidationError, match="sandbox file count too large"):
        SandboxSpec(
            kind="docker",
            base_image="python:3.11-slim",
            files={f"file-{index}.txt": "x" for index in range(101)},
        )


def test_sandbox_spec_rejects_large_total_file_content() -> None:
    with pytest.raises(ValidationError, match="sandbox total file content too large"):
        SandboxSpec(
            kind="docker",
            base_image="python:3.11-slim",
            files={f"file-{index}.txt": "x" * (256 * 1024) for index in range(9)},
        )


def test_sandbox_spec_rejects_none_with_image() -> None:
    with pytest.raises(ValidationError):
        SandboxSpec(kind="none", base_image="python:3.11-slim")


def test_sandbox_result_caps_output() -> None:
    result = SandboxResult(
        exit_code=0,
        stdout="x" * (OUTPUT_LIMIT_BYTES + 10),
        stderr="",
        duration_ms=1,
        timed_out=False,
        oom_killed=False,
        image_pulled=False,
    )

    assert len(result.stdout.encode()) < OUTPUT_LIMIT_BYTES + 100
    assert "<TRUNCATED_TO_64KB>" in result.stdout
