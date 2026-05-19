from __future__ import annotations

from pathlib import Path

import pytest

from fixlog.normalizer.python import normalize_python_error

RAW_ROOT = Path(__file__).parent / "fixtures" / "python"


def fixture_paths() -> list[Path]:
    return sorted(RAW_ROOT.rglob("*.txt"))


@pytest.mark.parametrize("fixture_path", fixture_paths(), ids=lambda path: path.stem)
def test_normalization_is_canonical_string_idempotent(fixture_path: Path) -> None:
    first = normalize_python_error(fixture_path.read_text())
    second = normalize_python_error(first.canonical_string)

    assert second.canonical_string == first.canonical_string
    assert second.hash == first.hash
