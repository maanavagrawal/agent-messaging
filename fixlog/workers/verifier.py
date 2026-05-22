from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import logging
import re
import shlex
from asyncio import AbstractEventLoop
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from fixlog.db.models import Entry, Verification, VerificationResult, VerifierKind
from fixlog.sandbox.result import SandboxResult
from fixlog.sandbox.runner import SandboxRunner
from fixlog.sandbox.spec import SandboxSpec, build_sandbox_spec

logger = logging.getLogger(__name__)

AUTO_SANDBOX_VERIFIER_ID = "fixlog-auto-sandbox"


class RunnerProtocol(Protocol):
    def run(
        self,
        spec: SandboxSpec,
        workspace: bytes | None,
        command: str,
        timeout_s: int = 60,
        memory_mb: int = 512,
        allow_network: bool = False,
    ) -> SandboxResult: ...


@dataclass(frozen=True)
class VerificationJob:
    entry_id: UUID


class VerifierWorker:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        runner: RunnerProtocol | None = None,
        allowed_images: set[str] | frozenset[str],
        queue_size: int = 100,
        timeout_s: int = 60,
        memory_mb: int = 512,
        shutdown_timeout_s: int = 5,
    ) -> None:
        self.session_factory = session_factory
        self.runner = runner or SandboxRunner()
        self.allowed_images = frozenset(allowed_images)
        self.queue: asyncio.Queue[VerificationJob | None] = asyncio.Queue(
            maxsize=queue_size
        )
        self.timeout_s = timeout_s
        self.memory_mb = memory_mb
        self.shutdown_timeout_s = shutdown_timeout_s
        self._task: asyncio.Task[None] | None = None
        self._event_loop: AbstractEventLoop | None = None
        self._running = False
        self._stopping = False
        self.last_error: str | None = None
        self.result_counts: Counter[str] = Counter()
        self.recent_results: deque[str] = deque(maxlen=25)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._running = True
        self._stopping = False
        self._event_loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopping = True
        self._running = False
        if self._task is None:
            self._event_loop = None
            return
        self._discard_pending_jobs()
        self.queue.put_nowait(None)
        try:
            await asyncio.wait_for(self._task, timeout=self.shutdown_timeout_s)
        except TimeoutError:
            self.last_error = "verifier worker shutdown timed out"
            logger.error(self.last_error)
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        except asyncio.CancelledError:
            pass
        self._task = None
        self._event_loop = None

    async def enqueue(self, entry_id: UUID) -> bool:
        if self._stopping or self.queue.full():
            return False
        self.queue.put_nowait(VerificationJob(entry_id=entry_id))
        return True

    def enqueue_threadsafe(self, entry_id: UUID) -> bool:
        if self._event_loop is None or not self._running or self._stopping:
            return False
        future = asyncio.run_coroutine_threadsafe(self.enqueue(entry_id), self._event_loop)
        try:
            return bool(future.result(timeout=1))
        except (TimeoutError, concurrent.futures.TimeoutError):
            return False

    def status(self) -> dict[str, object]:
        return {
            "running": self._running and self._task is not None and not self._task.done(),
            "queue_depth": self.queue.qsize(),
            "last_error": self.last_error,
            "recent_result_counts": dict(self.result_counts),
        }

    async def _loop(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                if job is None:
                    return
                await asyncio.to_thread(self.verify_entry, job.entry_id)
            except Exception as exc:  # pragma: no cover - defensive worker guard
                logger.exception(
                    "auto sandbox verification failed entry=%s",
                    job.entry_id if job is not None else None,
                )
                self.last_error = str(exc)
            finally:
                self.queue.task_done()

    def _discard_pending_jobs(self) -> None:
        while True:
            try:
                _job = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            self.queue.task_done()

    def verify_entry(self, entry_id: UUID) -> Verification:
        with self.session_factory() as db:
            entry = _load_entry(db, entry_id)
            if entry is None:
                raise ValueError(f"entry not found: {entry_id}")
            verification = self._verify_loaded_entry(db, entry)
            self.result_counts[verification.result.value] += 1
            self.recent_results.append(verification.result.value)
            return verification

    def write_queue_overflow(self, entry_id: UUID) -> Verification:
        with self.session_factory() as db:
            entry = _load_entry(db, entry_id)
            if entry is None:
                raise ValueError(f"entry not found: {entry_id}")
            verification = _create_verification(
                db,
                entry,
                VerificationResult.PARTIAL,
                "queue overflow",
                {},
            )
            self.result_counts[verification.result.value] += 1
            self.recent_results.append(verification.result.value)
            return verification

    def _verify_loaded_entry(self, db: Session, entry: Entry) -> Verification:
        try:
            spec = build_sandbox_spec(entry.sandbox_kind.value, entry.sandbox_spec)
        except Exception as exc:
            return _create_verification(
                db,
                entry,
                VerificationResult.FAIL,
                f"invalid sandbox spec: {exc}",
                {},
            )
        if spec.kind == "none":
            return _create_verification(
                db,
                entry,
                VerificationResult.PARTIAL,
                "sandbox kind none cannot auto-verify",
                _env_snapshot(spec),
            )
        if spec.base_image not in self.allowed_images:
            return _create_verification(
                db,
                entry,
                VerificationResult.FAIL,
                f"image not in whitelist: {spec.base_image}",
                _env_snapshot(spec),
            )

        setup_commands = spec.setup_commands + _commands_from_text(
            entry.reproduction_setup
        )
        baseline_spec = spec.model_copy(update={"setup_commands": setup_commands})
        try:
            trigger = self.runner.run(
                baseline_spec,
                workspace=None,
                command=entry.reproduction_trigger,
                timeout_s=self.timeout_s,
                memory_mb=self.memory_mb,
            )
        except Exception as exc:
            return _create_verification(
                db,
                entry,
                VerificationResult.PARTIAL,
                f"sandbox runner failed during trigger: {exc}",
                _env_snapshot(spec),
            )
        if trigger.timed_out or trigger.oom_killed:
            return _create_verification(
                db,
                entry,
                VerificationResult.PARTIAL,
                _notes("trigger", trigger),
                _env_snapshot(spec),
            )
        if not _trigger_reproduced(entry, trigger):
            return _create_verification(
                db,
                entry,
                VerificationResult.FAIL,
                _notes("trigger did not reproduce expected error", trigger),
                _env_snapshot(spec),
            )

        try:
            fixed_files = apply_unified_diff(spec.files, entry.fix_diff)
        except ValueError as exc:
            return _create_verification(
                db,
                entry,
                VerificationResult.FAIL,
                f"fix_diff could not be applied: {exc}\n\n{_notes('trigger', trigger)}",
                _env_snapshot(spec),
            )
        try:
            fixed_setup_commands = setup_commands + _fix_overlay_commands(
                spec.files, fixed_files
            )
        except ValueError as exc:
            return _create_verification(
                db,
                entry,
                VerificationResult.FAIL,
                f"fix_diff could not be applied: {exc}\n\n{_notes('trigger', trigger)}",
                _env_snapshot(spec),
            )
        fixed_spec = spec.model_copy(
            update={"files": spec.files, "setup_commands": fixed_setup_commands}
        )
        try:
            verify = self.runner.run(
                fixed_spec,
                workspace=None,
                command=entry.reproduction_verify,
                timeout_s=self.timeout_s,
                memory_mb=self.memory_mb,
            )
        except Exception as exc:
            return _create_verification(
                db,
                entry,
                VerificationResult.PARTIAL,
                f"{_notes('trigger', trigger)}\n\n"
                f"sandbox runner failed during verify: {exc}",
                _env_snapshot(spec),
            )
        if verify.timed_out or verify.oom_killed:
            result = VerificationResult.PARTIAL
        elif verify.exit_code == 0:
            result = VerificationResult.PASS
        else:
            result = VerificationResult.FAIL
        return _create_verification(
            db,
            entry,
            result,
            f"{_notes('trigger', trigger)}\n\n{_notes('verify', verify)}",
            _env_snapshot(spec),
        )


def _load_entry(db: Session, entry_id: UUID) -> Entry | None:
    return db.scalar(
        select(Entry)
        .options(joinedload(Entry.canonical_error_signature))
        .where(Entry.id == entry_id)
    )


def _create_verification(
    db: Session,
    entry: Entry,
    result: VerificationResult,
    notes: str,
    env_snapshot: dict[str, object],
) -> Verification:
    verification = Verification(
        entry_id=entry.id,
        verifier_kind=VerifierKind.AUTO_SANDBOX,
        verifier_id=AUTO_SANDBOX_VERIFIER_ID,
        result=result,
        env_snapshot=env_snapshot or entry.env_context,
        notes=notes,
    )
    db.add(verification)
    db.commit()
    db.refresh(verification)
    logger.info(
        "auto sandbox verification created id=%s entry=%s result=%s",
        verification.id,
        entry.id,
        result.value,
    )
    return verification


def _commands_from_text(value: str) -> list[str]:
    return [
        line.strip()
        for line in value.splitlines()
        if line.strip() and line.strip().lower() not in {"none", "n/a"}
    ]


def _trigger_reproduced(entry: Entry, result: SandboxResult) -> bool:
    output = f"{result.stdout}\n{result.stderr}"
    if result.exit_code != 0:
        return True
    signature = entry.canonical_error_signature
    needles = list(signature.raw_examples or [])
    needles.extend(
        item
        for item in [
            signature.canonical_string,
            signature.exception_type,
            signature.exception_message,
        ]
        if item
    )
    return any(needle and needle in output for needle in needles)


def _env_snapshot(spec: SandboxSpec) -> dict[str, object]:
    return {
        "language_version": spec.base_image or spec.kind,
        "framework_version": None,
        "key_deps": {
            "base_image": spec.base_image or "",
            "sandbox_kind": spec.kind,
        },
        "os": "docker" if spec.kind != "none" else "none",
    }


def _notes(step: str, result: SandboxResult) -> str:
    return (
        f"{step}: exit_code={result.exit_code} timed_out={result.timed_out} "
        f"oom_killed={result.oom_killed} duration_ms={result.duration_ms}\n"
        f"stdout:\n{result.stdout[:4000]}\n"
        f"stderr:\n{result.stderr[:4000]}"
    )


def _fix_overlay_commands(
    original_files: dict[str, str], fixed_files: dict[str, str]
) -> list[str]:
    commands: list[str] = []
    for path in sorted(set(original_files) | set(fixed_files)):
        if path not in fixed_files:
            commands.append(_remove_file_command(path))
        elif original_files.get(path) != fixed_files[path]:
            commands.append(_write_file_command(path, fixed_files[path]))
    return commands


def _write_file_command(path: str, content: str) -> str:
    _validate_workspace_path(path)
    quoted_path = shlex.quote(f"/workspace/{path}")
    quoted_dir = shlex.quote(str(PurePosixPath(f"/workspace/{path}").parent))
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return (
        f"mkdir -p {quoted_dir} && "
        f"printf %s {shlex.quote(encoded)} | base64 -d > {quoted_path}"
    )


def _remove_file_command(path: str) -> str:
    _validate_workspace_path(path)
    return f"rm -f {shlex.quote(f'/workspace/{path}')}"


def _validate_workspace_path(path: str) -> None:
    pure_path = PurePosixPath(path)
    if pure_path.is_absolute() or ".." in pure_path.parts or "\x00" in path:
        raise ValueError(f"unsafe sandbox file path: {path}")
    if str(pure_path) in {"", "."} or path.endswith("/"):
        raise ValueError(f"unsafe sandbox file path: {path}")


def apply_unified_diff(files: dict[str, str], diff: str) -> dict[str, str]:
    result = dict(files)
    lines = diff.splitlines()
    index = 0
    while index < len(lines):
        if not lines[index].startswith("--- "):
            index += 1
            continue
        old_path = _diff_path(lines[index][4:])
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise ValueError("expected +++ line after --- line")
        new_path = _diff_path(lines[index][4:])
        index += 1
        hunks: list[list[str]] = []
        while index < len(lines) and not lines[index].startswith("--- "):
            if not lines[index].startswith("@@"):
                index += 1
                continue
            hunk = [lines[index]]
            index += 1
            while index < len(lines) and not lines[index].startswith("@@") and not lines[index].startswith("--- "):
                hunk.append(lines[index])
                index += 1
            hunks.append(hunk)
        if new_path == "/dev/null":
            result.pop(old_path, None)
            continue
        target_path = new_path
        source_path = old_path if old_path != "/dev/null" else target_path
        original = result.get(source_path)
        if original is None:
            original = _original_from_hunks(hunks)
        result[target_path] = _apply_hunks(original, hunks)
        if target_path != source_path:
            result.pop(source_path, None)
    return result


def _diff_path(raw_path: str) -> str:
    path = raw_path.split("\t", 1)[0].split(" ", 1)[0]
    if path in {"/dev/null", "dev/null"}:
        return "/dev/null"
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def _apply_hunks(original: str, hunks: list[list[str]]) -> str:
    original_lines = original.splitlines()
    output: list[str] = []
    old_index = 0
    for hunk in hunks:
        match = re.match(r"@@ -(?P<old>\d+)(?:,\d+)? \+(?P<new>\d+)(?:,\d+)? @@", hunk[0])
        if match is None:
            raise ValueError(f"invalid hunk header: {hunk[0]}")
        old_start = int(match.group("old")) - 1
        if old_start < old_index:
            raise ValueError("overlapping hunks")
        output.extend(original_lines[old_index:old_start])
        old_index = old_start
        for line in hunk[1:]:
            if line.startswith("\\"):
                continue
            if line == "":
                prefix = " "
                text = ""
            else:
                prefix = line[0]
                text = line[1:]
            if prefix == " ":
                if old_index >= len(original_lines) or original_lines[old_index] != text:
                    raise ValueError("context line did not match")
                output.append(text)
                old_index += 1
            elif prefix == "-":
                if old_index >= len(original_lines) or original_lines[old_index] != text:
                    raise ValueError("removed line did not match")
                old_index += 1
            elif prefix == "+":
                output.append(text)
            else:
                raise ValueError(f"unknown hunk line prefix: {prefix}")
    output.extend(original_lines[old_index:])
    return "\n".join(output) + ("\n" if original.endswith("\n") or output else "")


def _original_from_hunks(hunks: list[list[str]]) -> str:
    lines: list[str] = []
    for hunk in hunks:
        for line in hunk[1:]:
            if line.startswith((" ", "-")):
                lines.append(line[1:])
    return "\n".join(lines) + ("\n" if lines else "")
