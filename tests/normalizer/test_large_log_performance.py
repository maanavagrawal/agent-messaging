from __future__ import annotations

from time import perf_counter

from fixlog.normalizer.python import normalize_python_error


def test_large_generic_log_does_not_trigger_regex_pathology() -> None:
    raw = "\n".join(
        f"2026-05-19T04:13:54Z line {index} request 550e8400-e29b-41d4-a716-446655440000"
        for index in range(5000)
    )

    start = perf_counter()
    result = normalize_python_error(raw)
    elapsed = perf_counter() - start

    assert result.error_kind == "generic"
    assert elapsed < 1.0
