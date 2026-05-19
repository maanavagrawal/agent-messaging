from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import auth_headers
from fixlog.db.models import SessionEvent
from fixlog_harness.models import NormalizedEvent, SessionMapping, StuckSignal
from fixlog_harness.parsers.claude_code import ClaudeCodeLogParser
from fixlog_harness.stuck_detector import StuckDetector
from fixlog_harness.watcher import HarnessPipeline, SessionMapStore

FIXTURES = Path(__file__).parent / "fixtures" / "claude_code"


class ServerTestClient:
    def __init__(self, client: TestClient) -> None:
        self.client = client

    def start_session(self, event: NormalizedEvent) -> SessionMapping:
        response = self.client.post(
            "/sessions/start",
            headers=auth_headers(),
            json={
                "model_name": "claude-code",
                "harness_name": "claude-code-log-watcher",
                "source_tool": event.source_tool,
                "source_tool_session_id": event.source_session_id,
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        return SessionMapping(
            fixlog_session_id=payload["session_id"],
            fixlog_persona_id=payload["persona_id"],
            started_at=event.ts,
        )

    def post_event(self, session_id: str, event: NormalizedEvent) -> str:
        response = self.client.post(
            f"/sessions/{session_id}/events",
            headers=auth_headers(session_id=session_id),
            json={
                "kind": event.kind,
                "ts": event.ts.isoformat(),
                "payload": event.model_dump(mode="json"),
            },
        )
        assert response.status_code == 200, response.text
        return str(response.json()["event_id"])

    def post_stuck_signal(self, session_id: str, signal: StuckSignal) -> str:
        response = self.client.post(
            f"/sessions/{session_id}/events",
            headers=auth_headers(session_id=session_id),
            json={
                "kind": "stuck_emitted",
                "ts": signal.ts.isoformat(),
                "payload": signal.model_dump(mode="json"),
            },
        )
        assert response.status_code == 200, response.text
        return str(response.json()["event_id"])

    def submit_candidate(self, candidate: object) -> dict[str, Any]:
        return {}


class NoopHarvester:
    def __init__(self) -> None:
        self.settings = type("Settings", (), {"auto_submit_harvests": False})()

    def harvest(self, events: list[NormalizedEvent], fixlog_session_id: str | None = None) -> None:
        return None


def test_replay_pipeline_posts_redacted_events_to_fixlog_server(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    pipeline = HarnessPipeline(
        client=ServerTestClient(client),
        session_store=SessionMapStore(tmp_path / "session_map.json"),
        detector=StuckDetector(),
        harvester=NoopHarvester(),
    )
    pipeline.replay_file(FIXTURES / "env_leak_redaction.jsonl", ClaudeCodeLogParser())
    events = db_session.scalars(select(SessionEvent).order_by(SessionEvent.ts)).all()
    assert [event.kind for event in events] == [
        "session_start",
        "tool_call",
        "tool_result",
        "session_end",
    ]
    assert events[2].payload["redacted"] is True
    assert "sk-proj" not in str(events[2].payload)
