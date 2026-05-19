from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fixlog.normalizer.python import normalize_python_error

FIXTURE_ROOT = Path(__file__).parent / "fixtures"
RAW_ROOT = FIXTURE_ROOT / "python"
EXPECTED_ROOT = FIXTURE_ROOT / "expected"


def fixture_paths() -> list[Path]:
    return sorted(RAW_ROOT.rglob("*.txt"))


@pytest.mark.parametrize("fixture_path", fixture_paths(), ids=lambda path: path.stem)
def test_python_normalizer_matches_fixture(fixture_path: Path) -> None:
    result = normalize_python_error(fixture_path.read_text())
    actual = result.model_dump(mode="json")
    actual_hash = actual.pop("hash")
    expected = json.loads((EXPECTED_ROOT / f"{fixture_path.stem}.json").read_text())

    assert actual == expected
    assert actual_hash == hashlib.sha256(result.canonical_string.encode("utf-8")).hexdigest()[:16]


def test_deep_traceback_truncates_to_last_three_frames() -> None:
    raw = (RAW_ROOT / "traceback" / "deep_traceback_100_frames.txt").read_text()
    result = normalize_python_error(raw)

    assert len(result.traceback_shape) == 3
    assert result.traceback_shape == [
        ("frame_098", "func_098"),
        ("frame_099", "func_099"),
        ("frame_100", "func_100"),
    ]


def test_chained_exception_uses_last_exception() -> None:
    raw = (RAW_ROOT / "traceback" / "chained_exception.txt").read_text()
    result = normalize_python_error(raw)

    assert result.was_chained is True
    assert result.exception_type == "RuntimeError"
    assert result.last_frame_module == "load"
