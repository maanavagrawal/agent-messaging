from __future__ import annotations

import io
import base64
import shlex
import tarfile
import threading
import time
from queue import Queue
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

from fixlog.sandbox.config import SandboxLimits
from fixlog.sandbox.result import OUTPUT_LIMIT_BYTES, SandboxResult
from fixlog.sandbox.spec import (
    MAX_SPEC_FILE_BYTES,
    MAX_SPEC_FILE_COUNT,
    MAX_SPEC_TOTAL_FILE_BYTES,
    SandboxSpec,
)


class SandboxRunner:
    def __init__(self, limits: SandboxLimits | None = None) -> None:
        self.limits = limits or SandboxLimits()

    def run(
        self,
        spec: SandboxSpec,
        workspace: bytes | None,
        command: str,
        timeout_s: int = 60,
        memory_mb: int = 512,
        allow_network: bool = False,
    ) -> SandboxResult:
        if spec.kind == "none":
            raise ValueError("sandbox kind none cannot be executed")
        if spec.base_image is None:
            raise ValueError("base_image is required")
        started_at = time.monotonic()
        docker, docker_errors = _docker_modules()
        client = docker.from_env()
        try:
            image_pulled = _ensure_image(
                client, docker_errors, spec.base_image, timeout_s=timeout_s
            )
        except TimeoutError:
            return SandboxResult(
                exit_code=124,
                stdout="",
                stderr=f"image pull timed out: {spec.base_image}",
                duration_ms=int((time.monotonic() - started_at) * 1000),
                timed_out=True,
                oom_killed=False,
                image_pulled=False,
            )
        except Exception as exc:
            return SandboxResult(
                exit_code=125,
                stdout="",
                stderr=f"image pull failed: {exc}",
                duration_ms=int((time.monotonic() - started_at) * 1000),
                timed_out=False,
                oom_killed=False,
                image_pulled=False,
            )
        container = None
        timed_out = False
        exit_code = 125
        try:
            # Security posture:
            # - network is disabled by default (`network_mode="none"`)
            # - root filesystem is read-only (`read_only=True`)
            # - only /workspace is writable, via tmpfs
            # - memory, CPU, and PID counts are bounded
            # - no privileged mode, no added capabilities, all caps dropped
            # - no-new-privileges blocks privilege escalation through setuid binaries
            # - process runs as a numeric non-root user independent of image defaults
            container = client.containers.create(
                image=spec.base_image,
                command=["sleep", "infinity"],
                working_dir="/workspace",
                detach=True,
                user="65532:65532",
                network_mode=None if allow_network else "none",
                read_only=True,
                tmpfs={
                    "/workspace": (
                        f"rw,size={self.limits.workspace_tmpfs_mb}m,"
                        "uid=65532,gid=65532,mode=1777"
                    )
                },
                mem_limit=f"{memory_mb}m",
                nano_cpus=int(self.limits.cpu_count * 1_000_000_000),
                pids_limit=self.limits.pids_limit,
                privileged=False,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                use_config_proxy=False,
            )
            container.start()
            _prepare_workspace(container, spec, workspace, command)
            exec_result = _exec_with_timeout(
                container, ["/bin/sh", "/workspace/.fixlog/run.sh"], timeout_s
            )
            if exec_result is None:
                timed_out = True
                _terminate_container(container)
                container.reload()
                state = container.attrs.get("State", {})
                exit_code = int(state.get("ExitCode") or 124)
            else:
                exit_code = int(exec_result.exit_code)
            container.reload()
            stdout, stderr = _read_captured_output(container)
            state = container.attrs.get("State", {})
            oom_killed = (
                bool(state.get("OOMKilled", False))
                or exit_code == 137
                or _looks_memory_exhausted(stdout, stderr)
            )
        finally:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            if container is not None:
                _remove_container(container)
        return SandboxResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            timed_out=timed_out,
            oom_killed=oom_killed,
            image_pulled=image_pulled,
        )


def _docker_modules() -> tuple[Any, Any]:
    try:
        import docker
        import docker.errors
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("docker package is required for sandbox verification") from exc
    return docker, docker.errors


def _ensure_image(
    client: Any, docker_errors: Any, image: str, timeout_s: int
) -> bool:
    try:
        client.images.get(image)
        return False
    except docker_errors.ImageNotFound:
        _call_with_timeout(lambda: client.images.pull(image), timeout_s)
        return True


def _prepare_workspace(
    container: Any, spec: SandboxSpec, workspace: bytes | None, command: str
) -> None:
    _exec_checked(container, "mkdir -p /workspace/.fixlog")
    _write_container_file(container, ".fixlog/stdout", b"", mode=0o666)
    _write_container_file(container, ".fixlog/stderr", b"", mode=0o666)
    if workspace is not None:
        for path, content in _workspace_files_from_tar(workspace).items():
            _write_container_file(container, path, content, mode=0o666)
    for path, content in spec.files.items():
        _write_container_file(container, path, content.encode("utf-8"), mode=0o666)
    _write_container_file(
        container,
        ".fixlog/run.sh",
        _run_script(spec.setup_commands, command).encode("utf-8"),
        mode=0o755,
    )


def _write_container_file(
    container: Any, path: str, content: bytes, mode: int = 0o666
) -> None:
    _validate_archive_path(path)
    quoted_path = shlex.quote(f"/workspace/{path}")
    quoted_dir = shlex.quote(str(PurePosixPath(f"/workspace/{path}").parent))
    b64 = base64.b64encode(content).decode("ascii")
    script = (
        f"mkdir -p {quoted_dir} && "
        f"printf %s {shlex.quote(b64)} | base64 -d > {quoted_path} && "
        f"chmod {mode:o} {quoted_path}"
    )
    _exec_checked(container, script)


def _exec_checked(container: Any, script: str) -> None:
    result = container.exec_run(["/bin/sh", "-c", script], demux=False)
    if int(result.exit_code) != 0:
        output = result.output.decode("utf-8", errors="replace") if result.output else ""
        raise RuntimeError(f"workspace setup failed: {output}")


def _run_script(setup_commands: Iterable[str], command: str) -> str:
    lines = [
        "#!/bin/sh",
        "set +e",
        "cd /workspace || exit 125",
        ": > /workspace/.fixlog/stdout",
        ": > /workspace/.fixlog/stderr",
    ]
    for setup_command in setup_commands:
        quoted = shlex.quote(setup_command)
        lines.extend(
            [
                f"/bin/sh -c {quoted} >>/workspace/.fixlog/stdout 2>>/workspace/.fixlog/stderr",
                "code=$?",
                'if [ "$code" -ne 0 ]; then exit "$code"; fi',
            ]
        )
    lines.extend(
        [
            f"/bin/sh -c {shlex.quote(command)} >>/workspace/.fixlog/stdout 2>>/workspace/.fixlog/stderr",
            "exit $?",
            "",
        ]
    )
    return "\n".join(lines)


def _workspace_files_from_tar(workspace: bytes) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    total_bytes = 0
    with tarfile.open(fileobj=io.BytesIO(workspace), mode="r:gz") as source:
        for member in source.getmembers():
            if not member.isfile():
                continue
            if len(files) >= MAX_SPEC_FILE_COUNT:
                raise ValueError(f"workspace file count too large: {len(files) + 1}")
            _validate_archive_path(member.name)
            if member.size > MAX_SPEC_FILE_BYTES:
                raise ValueError(f"workspace file content too large: {member.name}")
            total_bytes += int(member.size)
            if total_bytes > MAX_SPEC_TOTAL_FILE_BYTES:
                raise ValueError("workspace total file content too large")
            extracted = source.extractfile(member)
            if extracted is None:
                continue
            files[member.name] = extracted.read()
    return files


def _validate_archive_path(path: str) -> None:
    pure_path = PurePosixPath(path)
    if pure_path.is_absolute() or ".." in pure_path.parts or "\x00" in path:
        raise ValueError(f"unsafe workspace path: {path}")


def _read_captured_output(container: Any) -> tuple[str, str]:
    stdout = _read_container_file(container, "/workspace/.fixlog/stdout")
    stderr = _read_container_file(container, "/workspace/.fixlog/stderr")
    if stdout is None and stderr is None:
        logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
        return logs, ""
    return stdout or "", stderr or ""


def _read_container_file(container: Any, path: str) -> str | None:
    quoted_path = shlex.quote(path)
    script = (
        f"if [ -f {quoted_path} ] && [ ! -L {quoted_path} ]; then "
        f"dd if={quoted_path} bs={OUTPUT_LIMIT_BYTES} count=1 2>/dev/null; "
        f"elif [ -e {quoted_path} ]; then "
        f"printf %s {shlex.quote(f'<UNREADABLE_NON_REGULAR_OUTPUT:{path}>')}; "
        "fi"
    )
    try:
        result = _exec_with_timeout(container, ["/bin/sh", "-c", script], timeout_s=2)
    except Exception:
        return None
    if result is None:
        return f"<OUTPUT_READ_TIMED_OUT:{path}>"
    if int(result.exit_code) != 0:
        return None
    return result.output.decode("utf-8", errors="replace") if result.output else ""


def _looks_memory_exhausted(stdout: str, stderr: str) -> bool:
    text = f"{stdout}\n{stderr}"
    return "MemoryError" in text or "Cannot allocate memory" in text


def _exec_with_timeout(container: Any, command: list[str], timeout_s: int) -> Any | None:
    try:
        return _call_with_timeout(
            lambda: container.exec_run(command, demux=False), timeout_s
        )
    except TimeoutError:
        return None


def _call_with_timeout(action: Any, timeout_s: int) -> Any:
    results: Queue[Any] = Queue(maxsize=1)

    def run_action() -> None:
        try:
            results.put(action())
        except Exception as exc:  # pragma: no cover - defensive thread relay
            results.put(exc)

    thread = threading.Thread(target=run_action, daemon=True)
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        raise TimeoutError()
    result = results.get()
    if isinstance(result, Exception):
        raise result
    return result


def _terminate_container(container: Any) -> None:
    try:
        container.stop(timeout=5)
    except Exception:
        try:
            container.kill()
        except Exception:
            pass


def _remove_container(container: Any) -> None:
    try:
        container.remove(force=True)
    except Exception:
        pass
