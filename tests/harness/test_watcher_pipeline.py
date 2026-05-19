from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fixlog_harness.models import NormalizedEvent, SessionMapping
from fixlog_harness.parsers.claude_code import ClaudeCodeLogParser
from fixlog_harness.stuck_detector import StuckDetector
from fixlog_harness.watcher import HarnessPipeline, SessionMapStore, discover_recent_session_files

FIXTURES = Path(__file__).parent / "fixtures" / "claude_code"


class FakeClient:
    def __init__(self) -> None:
        self.started: list[NormalizedEvent] = []
        self.events: list[tuple[str, NormalizedEvent]] = []
        self.stuck: list[object] = []
        self.submitted: list[object] = []

    def start_session(self, event: NormalizedEvent) -> SessionMapping:
        self.started.append(event)
        return SessionMapping(
            fixlog_session_id="fixlog-session",
            fixlog_persona_id="persona",
            started_at=event.ts,
        )

    def post_event(self, session_id: str, event: NormalizedEvent) -> str:
        self.events.append((session_id, event))
        return f"event-{len(self.events)}"

    def post_stuck_signal(self, session_id: str, signal: object) -> str:
        self.stuck.append((session_id, signal))
        return "stuck-event"

    def submit_candidate(self, candidate: object) -> dict[str, str]:
        self.submitted.append(candidate)
        return {"id": "entry"}


class FakeHarvester:
    def __init__(self) -> None:
        self.settings = type("Settings", (), {"auto_submit_harvests": False, "quiet_seconds": 1})()
        self.calls: list[tuple[list[NormalizedEvent], str | None]] = []

    def harvest(self, events: list[NormalizedEvent], fixlog_session_id: str | None = None) -> None:
        self.calls.append((events, fixlog_session_id))
        return None


def test_replay_file_posts_redacted_events_and_session_end(tmp_path: Path) -> None:
    client = FakeClient()
    harvester = FakeHarvester()
    pipeline = HarnessPipeline(
        client=client,
        session_store=SessionMapStore(tmp_path / "map.json"),
        detector=StuckDetector(),
        harvester=harvester,
    )
    pipeline.replay_file(FIXTURES / "env_leak_redaction.jsonl", ClaudeCodeLogParser())
    kinds = [event.kind for _, event in client.events]
    assert kinds == ["session_start", "tool_call", "tool_result", "session_end"]
    assert len(client.started) == 1
    assert client.events[-2][1].redacted is True
    assert "sk-proj" not in client.events[-2][1].model_dump_json()
    assert harvester.calls
    assert not (tmp_path / "map.json").read_text().strip() == ""


def test_session_map_store_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "map.json"
    store = SessionMapStore(path)
    mapping = SessionMapping(
        fixlog_session_id="session",
        fixlog_persona_id="persona",
        started_at=datetime.fromisoformat("2026-04-27T01:00:00+00:00"),
    )
    store.put("claude_code", "source", mapping)
    loaded = SessionMapStore(path)
    assert loaded.get("claude_code", "source") == mapping
    loaded.remove("claude_code", "source")
    assert loaded.get("claude_code", "source") is None


def test_discovers_only_recent_jsonl_files(tmp_path: Path) -> None:
    recent = tmp_path / "project" / "recent.jsonl"
    old = tmp_path / "project" / "old.jsonl"
    recent.parent.mkdir()
    recent.write_text("")
    old.write_text("")
    old.touch()
    import os
    import time

    os.utime(old, (time.time() - 900, time.time() - 900))
    assert discover_recent_session_files(tmp_path, recent_seconds=60) == [recent]
