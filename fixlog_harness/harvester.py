from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Protocol

from fixlog_harness.config import HarnessSettings
from fixlog_harness.models import CandidateEntry, NormalizedEvent
from fixlog_harness.prompts.diagnosis import DIAGNOSIS_PROMPT
from fixlog_harness.prompts.reproduction import REPRODUCTION_PROMPT

logger = logging.getLogger(__name__)


class PromptClient(Protocol):
    def complete(self, prompt: str) -> str:
        """Return plain text completion for a prompt."""


class AnthropicPromptClient:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def complete(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for harvest prompt calls")
        try:
            from anthropic import Anthropic
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("anthropic package is required for harvest prompts") from exc

        client = Anthropic(api_key=self.api_key)
        message = client.messages.create(
            model=self.model,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        parts = [block.text for block in message.content if getattr(block, "type", None) == "text"]
        return "\n".join(parts).strip()


class Harvester:
    def __init__(
        self, settings: HarnessSettings, prompt_client: PromptClient | None = None
    ) -> None:
        self.settings = settings
        self.prompt_client = prompt_client or AnthropicPromptClient(
            settings.anthropic_api_key, settings.anthropic_model
        )

    def harvest(
        self, events: list[NormalizedEvent], fixlog_session_id: str | None = None
    ) -> CandidateEntry | None:
        first_error = _first_error_event(events)
        if first_error is None or first_error.tool_result is None:
            return None
        cwd = first_error.cwd
        if cwd is None:
            return None
        diff = _git_diff(cwd)
        if not diff.strip():
            return None
        failing_command = _command_for_result(events, first_error) or "<unknown>"
        verification_command = _last_successful_command(events)
        error_signature = (
            first_error.tool_result.error_signature or first_error.tool_result.content[:200]
        )
        reproduction_prompt = REPRODUCTION_PROMPT.format(
            error_signature=error_signature,
            diff=diff,
            failing_command=failing_command,
        )
        diagnosis_prompt = DIAGNOSIS_PROMPT.format(error_signature=error_signature, diff=diff)
        reproduction_setup = self.prompt_client.complete(reproduction_prompt)
        diagnosis = self.prompt_client.complete(diagnosis_prompt)
        candidate = CandidateEntry(
            source_tool=first_error.source_tool,
            source_session_id=first_error.source_session_id,
            fixlog_session_id=fixlog_session_id,
            cwd=cwd,
            project_slug=first_error.project_slug,
            git_commit=first_error.git_commit,
            error_signature=error_signature,
            raw_error_text=first_error.tool_result.content,
            failing_command=failing_command,
            verification_command=verification_command,
            fix_diff=diff,
            diagnosis=diagnosis,
            reproduction_setup=reproduction_setup,
            reproduction_trigger=failing_command,
            reproduction_verify=verification_command or failing_command,
        )
        return self.write_pending(candidate)

    def write_pending(self, candidate: CandidateEntry) -> CandidateEntry:
        self.settings.pending_harvest_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.pending_harvest_dir / f"{candidate.id}.json"
        payload = candidate.model_copy(update={"pending_path": path})
        path.write_text(json.dumps(payload.model_dump(mode="json"), indent=2) + "\n")
        logger.info("pending harvest written id=%s path=%s", candidate.id, path)
        return payload


def _first_error_event(events: list[NormalizedEvent]) -> NormalizedEvent | None:
    for event in events:
        if event.tool_result is not None and event.tool_result.is_error:
            return event
    return None


def _command_for_result(events: list[NormalizedEvent], result_event: NormalizedEvent) -> str | None:
    if result_event.tool_result is None:
        return None
    call_id = result_event.tool_result.tool_call_id
    for event in reversed(events):
        if event.tool_call is None or event.tool_call.tool_call_id != call_id:
            continue
        command = event.tool_call.args.get("command") or event.tool_call.args.get("cmd")
        return command if isinstance(command, str) else None
    return None


def _last_successful_command(events: list[NormalizedEvent]) -> str | None:
    for event in reversed(events):
        if event.tool_result is None or event.tool_result.is_error:
            continue
        command = _command_for_result(events, event)
        if command and _looks_like_test_command(command, event.tool_result.content):
            return command
    for event in reversed(events):
        if event.tool_result is None or event.tool_result.is_error:
            continue
        command = _command_for_result(events, event)
        if command:
            return command
    return None


def _looks_like_test_command(command: str, content: str) -> bool:
    lowered = f"{command}\n{content}".lower()
    return "pytest" in lowered or "unittest" in lowered or " passed" in lowered


def _git_diff(cwd: str) -> str:
    try:
        result = subprocess.run(
            ["git", "diff", "--no-ext-diff", "HEAD", "--"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def load_pending_harvests(directory: Path) -> list[CandidateEntry]:
    if not directory.exists():
        return []
    candidates = []
    for path in sorted(directory.glob("*.json")):
        candidate = CandidateEntry.model_validate_json(path.read_text())
        candidates.append(candidate.model_copy(update={"pending_path": path}))
    return candidates
