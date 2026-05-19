from __future__ import annotations

from typing import Any

import httpx

from fixlog_harness.config import HarnessSettings
from fixlog_harness.models import CandidateEntry, NormalizedEvent, SessionMapping, StuckSignal


class FixlogClient:
    def __init__(self, settings: HarnessSettings) -> None:
        self.settings = settings
        self._client = httpx.Client(base_url=settings.fixlog_base_url, timeout=10)

    def start_session(self, event: NormalizedEvent) -> SessionMapping:
        response = self._client.post(
            "/sessions/start",
            headers=self._auth_headers(),
            json={
                "model_name": self.settings.fixlog_harness_model_name,
                "harness_name": self.settings.fixlog_harness_name,
                "source_tool": event.source_tool,
                "source_tool_session_id": event.source_session_id,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return SessionMapping(
            fixlog_session_id=payload["session_id"],
            fixlog_persona_id=payload["persona_id"],
            started_at=event.ts,
        )

    def post_event(self, session_id: str, event: NormalizedEvent) -> str:
        body = {
            "kind": event.kind,
            "ts": event.ts.isoformat(),
            "payload": event.model_dump(mode="json"),
        }
        return self._post_session_event(session_id, body)

    def post_stuck_signal(self, session_id: str, signal: StuckSignal) -> str:
        body = {
            "kind": "stuck_emitted",
            "ts": signal.ts.isoformat(),
            "payload": signal.model_dump(mode="json"),
        }
        return self._post_session_event(session_id, body)

    def submit_candidate(self, candidate: CandidateEntry) -> dict[str, Any]:
        if candidate.fixlog_session_id is None:
            raise ValueError("candidate.fixlog_session_id is required")
        response = self._client.post(
            "/entries",
            headers=self._auth_headers(candidate.fixlog_session_id),
            json={
                "error_signature": {
                    "raw_text": candidate.raw_error_text,
                    "raw_examples": [candidate.raw_error_text],
                    "language": "python",
                    "framework": None,
                },
                "also_matches": [],
                "env_context": {
                    "language_version": "unknown",
                    "framework_version": None,
                    "key_deps": {},
                    "os": None,
                },
                "diagnosis": candidate.diagnosis,
                "fix_diff": candidate.fix_diff,
                "fix_explanation": None,
                "reproduction_setup": candidate.reproduction_setup,
                "reproduction_trigger": candidate.reproduction_trigger,
                "reproduction_verify": candidate.reproduction_verify,
                "sandbox_kind": "none",
                "sandbox_spec": "none",
                "tags": ["harvested"],
            },
        )
        response.raise_for_status()
        return response.json()

    def _post_session_event(self, session_id: str, body: dict[str, Any]) -> str:
        response = self._client.post(
            f"/sessions/{session_id}/events",
            headers=self._auth_headers(session_id),
            json=body,
        )
        response.raise_for_status()
        return str(response.json()["event_id"])

    def _auth_headers(self, session_id: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.settings.fixlog_api_token}"}
        if session_id is not None:
            headers["X-Fixlog-Session-Id"] = session_id
        return headers
