from __future__ import annotations

from fixlog.normalizer.models import ErrorKind
from fixlog.normalizer.python import normalize_python_error


def test_strong_pytest_marker_wins_over_embedded_traceback() -> None:
    raw = """FAILED tests/test_api.py::test_create_user - AssertionError: assert False
Traceback (most recent call last):
  File "/tmp/app.py", line 10, in create
    raise ValueError("wrong parser")
ValueError: wrong parser
"""

    result = normalize_python_error(raw)

    assert result.error_kind == ErrorKind.PYTEST
    assert result.exception_type == "AssertionError"
    assert result.last_frame_module == "test_api"
    assert result.last_frame_function == "test_create_user"
