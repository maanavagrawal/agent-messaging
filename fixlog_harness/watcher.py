from __future__ import annotations

import json
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from fixlog_harness.config import HarnessSettings
from fixlog_harness.models import (
    CandidateEntry,
    NormalizedEvent,
    SessionMapping,
    StuckSignal,
)
from fixlog_harness.parsers.base import LogParser
from fixlog_harness.parsers.claude_code import ClaudeCodeLogParser
from fixlog_harness.stuck_detector import StuckDetector

logger = logging.getLogger(__name__)


class FixlogClientProtocol(Protocol):
    def start_session(self, event: NormalizedEvent) -> SessionMapping: ...

    def post_event(self, session_id: str, event: NormalizedEvent) -> str: ...

    def post_stuck_signal(self, session_id: str, signal: StuckSignal) -> str: ...

    def submit_candidate(self, candidate: CandidateEntry) -> dict[str, object]: ...


class HarvesterProtocol(Protocol):
    settings: object

    def harvest(
        self, events: list[NormalizedEvent], fixlog_session_id: str | None = None
    ) -> CandidateEntry | None: ...


class SessionMapStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._mappings: dict[str, SessionMapping] = self._load()

    def get(self, source_tool: str, source_session_id: str) -> SessionMapping | None:
        return self._mappings.get(_mapping_key(source_tool, source_session_id))

    def put(
        self, source_tool: str, source_session_id: str, mapping: SessionMapping
    ) -> None:
        self._mappings[_mapping_key(source_tool, source_session_id)] = mapping
        self.save()

    def remove(self, source_tool: str, source_session_id: str) -> None:
        self._mappings.pop(_mapping_key(source_tool, source_session_id), None)
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            key: value.model_dump(mode="json") for key, value in self._mappings.items()
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n")

    def _load(self) -> dict[str, SessionMapping]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text())
        if not isinstance(raw, dict):
            return {}
        return {
            str(key): SessionMapping.model_validate(value)
            for key, value in raw.items()
            if isinstance(value, dict)
        }


class HarnessPipeline:
    def __init__(
        self,
        *,
        client: FixlogClientProtocol,
        session_store: SessionMapStore,
        detector: StuckDetector,
        harvester: HarvesterProtocol,
    ) -> None:
        self.client = client
        self.session_store = session_store
        self.detector = detector
        self.harvester = harvester
        self.events_by_source: dict[str, list[NormalizedEvent]] = {}

    def process_event(self, event: NormalizedEvent) -> SessionMapping:
        mapping = self._mapping_for(event)
        self.client.post_event(mapping.fixlog_session_id, event)
        key = _mapping_key(event.source_tool, event.source_session_id)
        self.events_by_source.setdefault(key, []).append(event)
        signal = self.detector.process(event)
        if signal is not None:
            logger.info("stuck signal emitted session=%s kind=%s", key, signal.kind)
            self.client.post_stuck_signal(mapping.fixlog_session_id, signal)
        return mapping

    def replay_file(self, path: Path, parser: LogParser | None = None) -> None:
        parser = parser or ClaudeCodeLogParser()
        last_event: NormalizedEvent | None = None
        for event in parser.initial_events_from_file_header(path):
            self.process_event(event)
            last_event = event
        for line in path.read_text().splitlines():
            for event in parser.parse_line(line):
                self.process_event(event)
                last_event = event
        if last_event is not None:
            end_event = last_event.model_copy(
                update={
                    "kind": "session_end",
                    "source_event_id": f"{last_event.source_session_id}:session_end",
                    "text": None,
                    "tool_call": None,
                    "tool_result": None,
                }
            )
            mapping = self.process_event(end_event)
            key = _mapping_key(end_event.source_tool, end_event.source_session_id)
            candidate = self.harvester.harvest(
                self.events_by_source.get(key, []), mapping.fixlog_session_id
            )
            if candidate is not None and _auto_submit_enabled(self.harvester):
                self.client.submit_candidate(candidate)
            self.session_store.remove(end_event.source_tool, end_event.source_session_id)

    def _mapping_for(self, event: NormalizedEvent) -> SessionMapping:
        mapping = self.session_store.get(event.source_tool, event.source_session_id)
        if mapping is not None:
            return mapping
        mapping = self.client.start_session(event)
        self.session_store.put(event.source_tool, event.source_session_id, mapping)
        return mapping


def discover_recent_session_files(projects_dir: Path, recent_seconds: int) -> list[Path]:
    cutoff = time.time() - recent_seconds
    if not projects_dir.exists():
        return []
    return [
        path
        for path in projects_dir.glob("**/*.jsonl")
        if path.is_file() and path.stat().st_mtime >= cutoff
    ]


def watch(settings: HarnessSettings, pipeline: HarnessPipeline) -> None:
    try:
        from watchdog.events import FileSystemEvent, FileSystemEventHandler
        from watchdog.observers import Observer
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency environment
        raise RuntimeError("watchdog package is required for watch mode") from exc

    class Handler(FileSystemEventHandler):
        def on_created(self, event: FileSystemEvent) -> None:
            if not event.is_directory and str(event.src_path).endswith(".jsonl"):
                threading.Thread(
                    target=tail_file,
                    args=(Path(str(event.src_path)), pipeline),
                    daemon=True,
                ).start()

    for path in discover_recent_session_files(
        settings.claude_projects_dir, settings.recent_seconds
    ):
        threading.Thread(target=tail_file, args=(path, pipeline), daemon=True).start()
    observer = Observer()
    observer.schedule(Handler(), str(settings.claude_projects_dir), recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()


def tail_file(path: Path, pipeline: HarnessPipeline) -> None:
    parser = ClaudeCodeLogParser()
    last_event: NormalizedEvent | None = None
    with path.open() as handle:
        handle.seek(0, 2)
        last_change = datetime.now(UTC)
        while True:
            line = handle.readline()
            if line:
                last_change = datetime.now(UTC)
                for event in parser.parse_line(line):
                    pipeline.process_event(event)
                    last_event = event
                continue
            if datetime.now(UTC) - last_change > timedelta(
                seconds=_quiet_seconds(pipeline.harvester)
            ):
                logger.info("session file quiet path=%s", path)
                if last_event is not None:
                    end_event = last_event.model_copy(
                        update={
                            "kind": "session_end",
                            "source_event_id": f"{last_event.source_session_id}:session_end",
                            "text": None,
                            "tool_call": None,
                            "tool_result": None,
                        }
                    )
                    mapping = pipeline.process_event(end_event)
                    key = _mapping_key(
                        end_event.source_tool, end_event.source_session_id
                    )
                    candidate = pipeline.harvester.harvest(
                        pipeline.events_by_source.get(key, []),
                        mapping.fixlog_session_id,
                    )
                    if candidate is not None and _auto_submit_enabled(pipeline.harvester):
                        pipeline.client.submit_candidate(candidate)
                    pipeline.session_store.remove(
                        end_event.source_tool, end_event.source_session_id
                    )
                return
            time.sleep(1)


def _mapping_key(source_tool: str, source_session_id: str) -> str:
    return f"{source_tool}:{source_session_id}"


def _auto_submit_enabled(harvester: HarvesterProtocol) -> bool:
    return bool(getattr(harvester.settings, "auto_submit_harvests", False))


def _quiet_seconds(harvester: HarvesterProtocol) -> int:
    return int(getattr(harvester.settings, "quiet_seconds", 300))
