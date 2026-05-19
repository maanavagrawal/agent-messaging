# fixlog Phase 2 Proposed Artifacts

This is the revised pre-implementation proposal after `/plan-eng-review`.
It is not source code yet.

## Approved Review Changes Reflected Here

- Strong pytest markers dispatch before traceback parsing.
- Already-normalized canonical strings are parsed explicitly for idempotency.
- Pip/generic synthetic exception types are fixed, not fixture-by-fixture taste calls.
- Traceback frame paths become module basenames. Paths inside messages become basenames only.
- Every common helper gets direct unit tests. A large-log smoke test guards regex performance.

## 1. `fixlog/normalizer/models.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ErrorKind(str, Enum):
    TRACEBACK = "traceback"
    PYTEST = "pytest"
    PIP = "pip"
    GENERIC = "generic"


class PythonErrorSignature(BaseModel):
    model_config = ConfigDict(frozen=True)

    exception_type: str = Field(min_length=1)
    exception_message: str
    last_frame_function: str | None = None
    last_frame_module: str | None = None
    traceback_shape: list[tuple[str, str]] = Field(default_factory=list, max_length=3)
    canonical_string: str = Field(min_length=1)
    hash: str = Field(pattern=r"^[0-9a-f]{16}$")
    error_kind: ErrorKind
    was_chained: bool = False


@dataclass(frozen=True)
class ParsedError:
    exception_type: str
    exception_message: str
    error_kind: ErrorKind
    last_frame_function: str | None = None
    last_frame_module: str | None = None
    traceback_shape: list[tuple[str, str]] = field(default_factory=list)
    was_chained: bool = False
    canonical_string_override: str | None = None
```

`canonical_string_override` is only for already-normalized canonical input.
When present, the dispatcher preserves that exact canonical string before hashing.

## 2. Fixture Corpus

Raw fixtures:

- `traceback/psycopg_undefined_column.txt`
- `traceback/django_does_not_exist.txt`
- `traceback/keyerror_session_id.txt`
- `traceback/recursion_error.txt`
- `traceback/chained_exception.txt`
- `traceback/type_error_nonetype.txt`
- `traceback/import_error.txt`
- `traceback/attribute_error.txt`
- `traceback/valueerror_in_init.txt`
- `traceback/deep_traceback_100_frames.txt`
- `pytest/assertion_dict_mismatch.txt`
- `pytest/assertion_string_diff.txt`
- `pytest/fixture_error.txt`
- `pytest/parametrized_failure.txt`
- `pip/version_not_found.txt`
- `pip/dependency_conflict.txt`
- `generic/bare_error_string.txt`
- `generic/multiline_log_with_error.txt`
- `generic/json_error_response.txt`
- `generic/non_python_error.txt`

Expected outputs live in `tests/normalizer/fixtures/expected/<stem>.json`.
The expected JSON excludes `hash`.

Sample raw fixture, `traceback/psycopg_undefined_column.txt`:

```text
Traceback (most recent call last):
  File "/home/danny/proj/app.py", line 42, in handle_request
    user = db.get_user(user_id)
  File "/home/danny/proj/db.py", line 18, in get_user
    return self._conn.execute(query, (user_id,)).fetchone()
psycopg2.errors.UndefinedColumn: column "user_name" does not exist
LINE 1: SELECT user_name FROM users WHERE id = 42
               ^
```

Sample expected JSON, `expected/psycopg_undefined_column.json`:

```json
{
  "exception_type": "psycopg2.errors.UndefinedColumn",
  "exception_message": "column \"user_name\" does not exist LINE 1: SELECT user_name FROM users WHERE id = <N>",
  "last_frame_function": "get_user",
  "last_frame_module": "db",
  "traceback_shape": [["app", "handle_request"], ["db", "get_user"]],
  "canonical_string": "psycopg2.errors.UndefinedColumn|column \"user_name\" does not exist LINE 1: SELECT user_name FROM users WHERE id = <N>|db::get_user|app::handle_request>db::get_user",
  "error_kind": "traceback",
  "was_chained": false
}
```

Additional required unit/performance tests:

- `tests/normalizer/test_common.py`: direct coverage for every helper in `common.py`.
- `tests/normalizer/test_dispatch.py`: pytest marker wins over traceback when markers are strong.
- `tests/normalizer/test_canonical_determinism.py`: at least 5 fixtures with at least 5 trivial variations each.
- `tests/normalizer/test_normalizer_idempotency.py`: every fixture plus explicit canonical-string input.
- `tests/normalizer/test_large_log_performance.py`: large multiline generic log completes within a small fixed threshold.

## 3. Function Signatures

```python
# fixlog/normalizer/python.py
def normalize_python_error(raw: str) -> PythonErrorSignature:
    """Normalize raw Python-related error output into a deterministic signature.

    Dispatch order is canonical input, pytest, traceback, pip, generic. Parser
    output is normalized by common helpers, converted to the unit-separator
    canonical_string, and hashed with sha256(canonical_string)[:16].
    """
```

```python
# fixlog/normalizer/parsers/traceback.py
def parse_traceback_error(raw: str) -> ParsedError | None:
    """Return ParsedError for a standard Python traceback.

    Uses the last exception in a chained traceback and truncates the traceback
    shape to the last 3 frames in execution order. Returns None when no standard
    traceback can be parsed.
    """
```

```python
# fixlog/normalizer/parsers/pytest.py
def parse_pytest_error(raw: str) -> ParsedError | None:
    """Return ParsedError for pytest failure output with strong pytest markers.

    Extracts pytest node id/module/function when available, keeps the first
    assertion line, and drops trailing diff/dump output. Returns None when the
    input is not recognizably pytest output.
    """
```

```python
# fixlog/normalizer/parsers/pip.py
def parse_pip_error(raw: str) -> ParsedError | None:
    """Return ParsedError for pip/package-manager error output.

    Uses fixed synthetic exception types: pip.VersionNotFound,
    pip.DependencyConflict, or pip.InstallError. Returns None when the input is
    not pip-like.
    """
```

```python
# fixlog/normalizer/parsers/generic.py
def parse_canonical_signature(raw: str) -> ParsedError | None:
    """Return ParsedError for an already-built canonical_string.

    Preserves the exact canonical string via canonical_string_override so
    normalizing canonical output is idempotent. Returns None when the input does
    not match the unit-separator canonical format.
    """


def parse_generic_error(raw: str) -> ParsedError:
    """Return a best-effort ParsedError for any input.

    Uses exception_type='GenericError' and a normalized first useful message
    line. This function never returns None.
    """
```

## 4. `common.py` Helper Functions

- `strip_ansi_codes(text: str) -> str`: remove terminal color/control escape codes.
- `normalize_user_home_paths(text: str) -> str`: replace `/Users/<name>`, `/home/<name>`, and `C:\Users\<name>` with placeholders.
- `replace_absolute_paths_with_basenames(text: str) -> str`: turn absolute file paths into their basename.
- `normalize_traceback_line_numbers(text: str) -> str`: replace `line 42` frame locations with `line <N>`.
- `normalize_memory_addresses(text: str) -> str`: replace `0x...` memory addresses with `<ADDR>`.
- `normalize_uuids(text: str) -> str`: replace dashed and 32-hex UUIDs with `<UUID>`.
- `normalize_sha_like_hashes(text: str) -> str`: replace long hex runs over 16 chars with `<HASH>`.
- `normalize_timestamps(text: str) -> str`: replace ISO and common datetime strings with `<TS>`.
- `normalize_ipython_cells(text: str) -> str`: replace `In[5]` with `In[<N>]`.
- `strip_column_marker_lines(text: str) -> str`: remove lines containing only whitespace and `^`.
- `collapse_message_whitespace(text: str) -> str`: collapse message whitespace to single spaces.
- `normalize_quoted_ids(text: str) -> str`: replace quoted ID-like strings with `<ID>`, preserving semantic names like `"user_name"`.
- `normalize_sql_numeric_literals(text: str) -> str`: replace SQL numeric comparisons like `id = 42` with `id = <N>`.
- `truncate_pytest_diff_dump(text: str) -> str`: keep first assertion line and drop pytest diff/dump tails.
- `module_basename(path_or_module: str) -> str`: derive module basename without directory or `.py`.
- `parse_traceback_frames(text: str) -> list[tuple[str, str]]`: extract traceback frame shape before truncation.
- `truncate_traceback_shape(frames: list[tuple[str, str]], limit: int = 3) -> list[tuple[str, str]]`: keep the last execution frames.
- `build_canonical_string(parsed: ParsedError) -> str`: produce `{type}\x1f{message}\x1f{module}::{function}\x1f{shape}` with `<none>` placeholders.
- `signature_hash(canonical_string: str) -> str`: compute `sha256(canonical_string)[:16]`.
- `normalize_common_text(text: str) -> str`: apply global normalization rules in the required order.

Every regex will be a named module-level compiled pattern with a comment explaining
what it matches and what it intentionally does not match.
