from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from fixlog_harness.models import CandidateEntry, NormalizedEvent, SessionMapping
from fixlog_harness.parsers.claude_code import ClaudeCodeLogParser
from fixlog_harness.stuck_detector import StuckDetector
from fixlog_harness.watcher import (
    HarnessPipeline,
    SessionMapStore,
    _observer_class,
    _process_event_from_tail,
    discover_recent_session_files,
)

FIXTURES = Path(__file__).parent / "fixtures" / "claude_code"


class FakeClient:
    def __init__(self) -> None:
        self.started: list[NormalizedEvent] = []
        self.events: list[tuple[str, NormalizedEvent]] = []
        self.stuck: list[object] = []
        self.published_issues: list[object] = []
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

    def publish_issue(self, candidate: object) -> dict[str, str]:
        self.published_issues.append(candidate)
        return {"id": "question"}

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


class AutoSubmitHarvester(FakeHarvester):
    def __init__(self) -> None:
        super().__init__()
        self.settings = type("Settings", (), {"auto_submit_harvests": True, "quiet_seconds": 1})()

    def harvest(
        self, events: list[NormalizedEvent], fixlog_session_id: str | None = None
    ) -> CandidateEntry:
        self.calls.append((events, fixlog_session_id))
        return CandidateEntry(
            source_tool="claude_code",
            source_session_id="source",
            fixlog_session_id=fixlog_session_id,
            cwd="/tmp/project",
            project_slug="project",
            git_commit=None,
            error_signature="ValueError: broken",
            raw_error_text="ValueError: broken",
            failing_command="python app.py",
            verification_command="python app.py",
            fix_diff="--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-broken\n+fixed\n",
            diagnosis="Initialize the value.",
            reproduction_setup="",
            reproduction_trigger="python app.py",
            reproduction_verify="python app.py",
        )


class PendingIssueHarvester(AutoSubmitHarvester):
    def __init__(self) -> None:
        super().__init__()
        self.settings = type("Settings", (), {"auto_submit_harvests": False, "quiet_seconds": 1})()


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


def test_replay_file_auto_submits_when_enabled(tmp_path: Path) -> None:
    client = FakeClient()
    harvester = AutoSubmitHarvester()
    pipeline = HarnessPipeline(
        client=client,
        session_store=SessionMapStore(tmp_path / "map.json"),
        detector=StuckDetector(),
        harvester=harvester,
    )

    pipeline.replay_file(FIXTURES / "env_leak_redaction.jsonl", ClaudeCodeLogParser())

    assert harvester.calls
    assert len(client.published_issues) == 1
    assert len(client.submitted) == 1


def test_replay_file_publishes_issue_when_harvest_is_pending(tmp_path: Path) -> None:
    client = FakeClient()
    harvester = PendingIssueHarvester()
    pipeline = HarnessPipeline(
        client=client,
        session_store=SessionMapStore(tmp_path / "map.json"),
        detector=StuckDetector(),
        harvester=harvester,
    )

    pipeline.replay_file(FIXTURES / "env_leak_redaction.jsonl", ClaudeCodeLogParser())

    assert harvester.calls
    assert len(client.published_issues) == 1
    assert client.submitted == []


def test_pipeline_drops_events_outside_allowed_projects(tmp_path: Path) -> None:
    client = FakeClient()
    pipeline = HarnessPipeline(
        client=client,
        session_store=SessionMapStore(tmp_path / "map.json"),
        detector=StuckDetector(),
        harvester=FakeHarvester(),
        allowed_projects=[tmp_path / "allowed"],
    )
    outside = NormalizedEvent(
        source_tool="claude_code",
        source_session_id="source-outside",
        source_event_id="event-outside",
        ts=datetime.fromisoformat("2026-04-27T01:00:00+00:00"),
        kind="agent_message",
        cwd=str(tmp_path / "elsewhere"),
        text="outside",
    )
    inside = outside.model_copy(
        update={
            "source_session_id": "source-inside",
            "source_event_id": "event-inside",
            "cwd": str(tmp_path / "allowed" / "repo"),
            "text": "inside",
        }
    )

    assert pipeline.process_event(outside) is None
    assert pipeline.process_event(inside) is not None

    assert [event.text for _, event in client.events] == ["inside"]


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


def test_observer_class_uses_polling_on_macos(monkeypatch) -> None:
    from watchdog.observers.polling import PollingObserver

    monkeypatch.setattr(sys, "platform", "darwin")
    assert _observer_class() is PollingObserver


def test_process_event_from_tail_logs_forwarding_failure(
    tmp_path: Path, caplog, monkeypatch
) -> None:
    class FailingPipeline:
        def process_event(self, event: NormalizedEvent) -> SessionMapping:
            raise RuntimeError("network blocked")

    event = NormalizedEvent(
        source_tool="claude_code",
        source_session_id="source",
        source_event_id="event",
        ts=datetime.fromisoformat("2026-04-27T01:00:00+00:00"),
        kind="agent_message",
        text="hello",
    )

    monkeypatch.setattr("fixlog_harness.watcher.time.sleep", lambda _seconds: None)
    caplog.set_level(logging.ERROR)
    result = _process_event_from_tail(
        tmp_path / "session.jsonl", FailingPipeline(), event  # type: ignore[arg-type]
    )

    assert result is None
    assert "failed to forward tailed event" in caplog.text
    assert "network blocked" in caplog.text


def test_process_event_from_tail_retries_transient_failure(
    tmp_path: Path, monkeypatch
) -> None:
    event = NormalizedEvent(
        source_tool="claude_code",
        source_session_id="source",
        source_event_id="event",
        ts=datetime.fromisoformat("2026-04-27T01:00:00+00:00"),
        kind="agent_message",
        text="hello",
    )

    class FlakyPipeline:
        def __init__(self) -> None:
            self.calls = 0

        def process_event(self, event: NormalizedEvent) -> SessionMapping:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary network blip")
            return SessionMapping(
                fixlog_session_id="fixlog-session",
                fixlog_persona_id="persona",
                started_at=event.ts,
            )

    pipeline = FlakyPipeline()
    monkeypatch.setattr("fixlog_harness.watcher.time.sleep", lambda _seconds: None)

    result = _process_event_from_tail(
        tmp_path / "session.jsonl", pipeline, event  # type: ignore[arg-type]
    )

    assert result is not None
    assert result.fixlog_session_id == "fixlog-session"
    assert pipeline.calls == 2
