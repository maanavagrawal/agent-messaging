from __future__ import annotations

from fixlog.normalizer.common import CANONICAL_SEPARATOR
from fixlog.normalizer.python import normalize_python_error


def test_literal_pipe_in_message_does_not_ambiguate_canonical_string() -> None:
    raw = """Traceback (most recent call last):
  File "/tmp/parser.py", line 10, in parse_pipeline
    raise ValueError("expected | got nothing | still parsing")
ValueError: expected | got nothing | still parsing
"""

    result = normalize_python_error(raw)

    assert result.canonical_string.count(CANONICAL_SEPARATOR) == 3
    assert "expected | got nothing | still parsing" in result.canonical_string


def test_literal_pipe_position_is_preserved_in_canonical_string() -> None:
    first = normalize_python_error("ValueError: expected | got nothing")
    second = normalize_python_error("ValueError: expected got | nothing")

    assert first.canonical_string.count(CANONICAL_SEPARATOR) == 3
    assert second.canonical_string.count(CANONICAL_SEPARATOR) == 3
    assert first.canonical_string != second.canonical_string


def test_unit_separator_is_stripped_from_fields_before_joining() -> None:
    result = normalize_python_error(f"ValueError: bad{CANONICAL_SEPARATOR}message")

    assert result.canonical_string.count(CANONICAL_SEPARATOR) == 3
    assert f"bad{CANONICAL_SEPARATOR}message" not in result.canonical_string
    assert "bad message" in result.canonical_string
