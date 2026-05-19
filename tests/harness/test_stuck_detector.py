from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fixlog_harness.models import NormalizedEvent, ToolResult
from fixlog_harness.stuck_detector import StuckDetector


BASE = datetime(2026, 4, 27, 1, 0, tzinfo=UTC)


def _event(
    index: int,
    *,
    is_error: bool = False,
    signature: str | None = None,
    content: str = "",
    seconds: int | None = None,
) -> NormalizedEvent:
    return NormalizedEvent(
        source_tool="claude_code",
        source_session_id="session",
        source_event_id=f"evt-{index}",
        ts=BASE + timedelta(seconds=seconds if seconds is not None else index),
        kind="tool_result",
        redacted=False,
        tool_result=ToolResult(
            tool_call_id=f"tool-{index}",
            content=content,
            is_error=is_error,
            error_signature=signature,
            exit_code=1 if is_error else None,
        ),
    )


def test_repeated_error_signal_after_three_matches() -> None:
    detector = StuckDetector()
    assert detector.process(_event(1, is_error=True, signature="abc")) is None
    assert detector.process(_event(2, is_error=True, signature="abc")) is None
    signal = detector.process(_event(3, is_error=True, signature="abc"))
    assert signal is not None
    assert signal.kind == "repeated_error"
    assert signal.error_signature == "abc"


def test_repeated_error_ignores_old_matches() -> None:
    detector = StuckDetector()
    detector.process(_event(1, is_error=True, signature="abc", seconds=0))
    detector.process(_event(2, is_error=True, signature="abc", seconds=400))
    signal = detector.process(_event(3, is_error=True, signature="abc", seconds=401))
    assert signal is None


def test_thrashing_signal_after_eight_errors_without_success() -> None:
    detector = StuckDetector()
    signal = None
    for index in range(8):
        signal = detector.process(
            _event(index, is_error=True, signature=f"sig-{index}", seconds=index)
        )
    assert signal is not None
    assert signal.kind == "thrashing"


def test_thrashing_suppressed_by_successful_test_result() -> None:
    detector = StuckDetector()
    detector.process(_event(100, content="3 passed in 0.22s", seconds=0))
    signal = None
    for index in range(8):
        signal = detector.process(
            _event(index, is_error=True, signature=f"sig-{index}", seconds=index + 1)
        )
    assert signal is None


def test_cooldown_suppresses_back_to_back_signals() -> None:
    detector = StuckDetector()
    for index in range(3):
        detector.process(_event(index, is_error=True, signature="abc", seconds=index))
    signal = detector.process(_event(4, is_error=True, signature="abc", seconds=4))
    assert signal is None
