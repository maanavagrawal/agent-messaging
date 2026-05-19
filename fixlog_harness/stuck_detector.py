from __future__ import annotations

import re
from collections import deque
from datetime import UTC, datetime, timedelta

from fixlog_harness.models import NormalizedEvent, StuckSignal, StuckSignalKind

REPEATED_ERROR_WINDOW = timedelta(minutes=5)
COOLDOWN = timedelta(seconds=60)
THRASHING_EVENT_WINDOW = 20

# Matches common successful pytest summaries.
PYTEST_SUCCESS_RE = re.compile(r"(?i)\b\d+\s+passed\b")

# Matches unittest's all-clear summary line.
UNITTEST_SUCCESS_RE = re.compile(r"(?m)^OK$")


class StuckDetector:
    def __init__(self) -> None:
        self._events: deque[NormalizedEvent] = deque(maxlen=200)
        self._last_signal_at: datetime | None = None

    def process(self, event: NormalizedEvent) -> StuckSignal | None:
        self._events.append(event)
        if self._in_cooldown(event.ts):
            return None
        signal = self._repeated_error_signal(event) or self._thrashing_signal(event)
        if signal is not None:
            self._last_signal_at = event.ts
        return signal

    def _in_cooldown(self, now: datetime) -> bool:
        if self._last_signal_at is None:
            return False
        return now - self._last_signal_at < COOLDOWN

    def _repeated_error_signal(self, event: NormalizedEvent) -> StuckSignal | None:
        result = event.tool_result
        if result is None or result.error_signature is None:
            return None
        cutoff = event.ts - REPEATED_ERROR_WINDOW
        matches = [
            item
            for item in self._events
            if item.ts >= cutoff
            and item.tool_result is not None
            and item.tool_result.error_signature == result.error_signature
        ]
        if len(matches) < 3:
            return None
        return StuckSignal(
            kind=StuckSignalKind.REPEATED_ERROR,
            ts=event.ts,
            source_tool=event.source_tool,
            source_session_id=event.source_session_id,
            error_signature=result.error_signature,
            reason="same error signature appeared 3+ times within 5 minutes",
            event_ids=[item.source_event_id for item in matches[-3:]],
        )

    def _thrashing_signal(self, event: NormalizedEvent) -> StuckSignal | None:
        recent = list(self._events)[-THRASHING_EVENT_WINDOW:]
        error_events = [
            item
            for item in recent
            if item.tool_result is not None and item.tool_result.is_error
        ]
        if len(error_events) < 8:
            return None
        if any(_is_successful_test_result(item) for item in recent):
            return None
        return StuckSignal(
            kind=StuckSignalKind.THRASHING,
            ts=event.ts,
            source_tool=event.source_tool,
            source_session_id=event.source_session_id,
            error_signature=event.tool_result.error_signature if event.tool_result else None,
            reason="8+ error events in the last 20 events with no successful test run",
            event_ids=[item.source_event_id for item in error_events[-8:]],
        )


def _is_successful_test_result(event: NormalizedEvent) -> bool:
    result = event.tool_result
    if result is None or result.is_error:
        return False
    return bool(
        PYTEST_SUCCESS_RE.search(result.content)
        or UNITTEST_SUCCESS_RE.search(result.content)
    )


def now_utc() -> datetime:
    return datetime.now(UTC)
