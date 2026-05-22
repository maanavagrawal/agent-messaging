from __future__ import annotations

import io
import tarfile

import pytest

from fixlog.sandbox.runner import SandboxRunner
from fixlog.sandbox.spec import SandboxSpec


def docker_available() -> bool:
    try:
        import docker
    except ModuleNotFoundError:
        return False
    try:
        client = docker.from_env()
        client.ping()
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not docker_available(), reason="Docker daemon and docker package are required"
)


def test_sandbox_runner_echoes_hello() -> None:
    result = SandboxRunner().run(
        SandboxSpec(kind="docker", base_image="python:3.11-slim"),
        workspace=None,
        command="echo hello",
        timeout_s=10,
    )

    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert result.timed_out is False
    assert result.oom_killed is False


def test_sandbox_runner_loads_workspace_tarball() -> None:
    result = SandboxRunner().run(
        SandboxSpec(kind="docker", base_image="python:3.11-slim"),
        workspace=workspace_tarball({"app.py": "print('from workspace')\n"}),
        command="python app.py",
        timeout_s=10,
    )

    assert result.exit_code == 0
    assert "from workspace" in result.stdout


def test_sandbox_runner_rejects_unsafe_workspace_tarball() -> None:
    with pytest.raises(ValueError, match="unsafe workspace path"):
        SandboxRunner().run(
            SandboxSpec(kind="docker", base_image="python:3.11-slim"),
            workspace=workspace_tarball({"../escape.py": "print('nope')\n"}),
            command="true",
            timeout_s=10,
        )


def test_sandbox_runner_blocks_network_by_default() -> None:
    result = SandboxRunner().run(
        SandboxSpec(kind="docker", base_image="python:3.11-slim"),
        workspace=None,
        command=(
            "python -c \"import urllib.request; "
            "urllib.request.urlopen('https://example.com', timeout=3)\""
        ),
        timeout_s=10,
    )

    assert result.exit_code != 0


def test_sandbox_runner_uses_read_only_rootfs() -> None:
    result = SandboxRunner().run(
        SandboxSpec(kind="docker", base_image="python:3.11-slim"),
        workspace=None,
        command="touch /etc/should-not-write",
        timeout_s=10,
    )

    assert result.exit_code != 0
    assert "Read-only file system" in result.stderr


def test_sandbox_runner_allows_workspace_writes() -> None:
    result = SandboxRunner().run(
        SandboxSpec(kind="docker", base_image="python:3.11-slim"),
        workspace=None,
        command="touch /workspace/can-write && ls /workspace",
        timeout_s=10,
    )

    assert result.exit_code == 0
    assert "can-write" in result.stdout


def test_sandbox_runner_does_not_block_on_non_regular_output_files() -> None:
    result = SandboxRunner().run(
        SandboxSpec(kind="docker", base_image="python:3.11-slim"),
        workspace=None,
        command="rm /workspace/.fixlog/stdout && mkfifo /workspace/.fixlog/stdout",
        timeout_s=10,
    )

    assert result.exit_code == 0
    assert "<UNREADABLE_NON_REGULAR_OUTPUT:/workspace/.fixlog/stdout>" in result.stdout


def test_sandbox_runner_times_out() -> None:
    result = SandboxRunner().run(
        SandboxSpec(kind="docker", base_image="python:3.11-slim"),
        workspace=None,
        command="python -c \"import time; time.sleep(999)\"",
        timeout_s=2,
    )

    assert result.timed_out is True
    assert result.exit_code != 0


def test_sandbox_runner_reports_oom() -> None:
    result = SandboxRunner().run(
        SandboxSpec(kind="docker", base_image="python:3.11-slim"),
        workspace=None,
        command=(
            "python - <<'PY'\n"
            "chunks=[]\n"
            "while True:\n"
            "    chunks.append(bytearray(10 * 1024 * 1024))\n"
            "PY"
        ),
        timeout_s=15,
        memory_mb=64,
    )

    assert result.exit_code != 0
    assert result.oom_killed is True


def workspace_tarball(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for path, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(path)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return output.getvalue()
