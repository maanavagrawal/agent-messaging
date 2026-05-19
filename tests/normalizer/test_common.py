from __future__ import annotations

from fixlog.normalizer.common import (
    build_canonical_string,
    collapse_message_whitespace,
    module_basename,
    normalize_common_text,
    normalize_ipython_cells,
    normalize_memory_addresses,
    normalize_quoted_ids,
    normalize_sha_like_hashes,
    normalize_sql_numeric_literals,
    normalize_timestamps,
    normalize_traceback_line_numbers,
    normalize_user_home_paths,
    normalize_uuids,
    parse_traceback_frames,
    replace_absolute_paths_with_basenames,
    signature_hash,
    strip_ansi_codes,
    strip_column_marker_lines,
    truncate_pytest_diff_dump,
    truncate_traceback_shape,
)
from fixlog.normalizer.models import ErrorKind, ParsedError


def test_strip_ansi_codes() -> None:
    assert strip_ansi_codes("\x1b[31mValueError\x1b[0m") == "ValueError"


def test_normalize_user_home_paths() -> None:
    raw = "/Users/alice/app/main.py /home/bob/app.py C:\\Users\\cara\\app.py"
    assert normalize_user_home_paths(raw) == (
        "/Users/<USER>/app/main.py /home/<USER>/app.py "
        "C:\\Users\\<USER>\\app.py"
    )


def test_replace_absolute_paths_with_basenames() -> None:
    raw = 'File "/Users/alice/project/app.py" and C:\\Users\\bob\\proj\\db.py'
    assert replace_absolute_paths_with_basenames(raw) == 'File "app.py" and db.py'


def test_normalize_traceback_line_numbers() -> None:
    assert normalize_traceback_line_numbers("File app.py, line 42") == "File app.py, line <N>"


def test_normalize_memory_addresses() -> None:
    assert normalize_memory_addresses("object at 0x7f4a2c1bd000") == "object at <ADDR>"


def test_normalize_uuids() -> None:
    raw = "id 550e8400-e29b-41d4-a716-446655440000 and 550e8400e29b41d4a716446655440000"
    assert normalize_uuids(raw) == "id <UUID> and <UUID>"


def test_normalize_sha_like_hashes() -> None:
    assert normalize_sha_like_hashes("commit abcdef1234567890abcdef") == "commit <HASH>"


def test_normalize_timestamps() -> None:
    raw = "at 2026-05-19T04:13:54Z and 2026/05/19 04:13:54"
    assert normalize_timestamps(raw) == "at <TS> and <TS>"


def test_normalize_ipython_cells() -> None:
    assert normalize_ipython_cells("In[5], line 1") == "In[<N>], line 1"


def test_strip_column_marker_lines() -> None:
    assert strip_column_marker_lines("LINE 1\n       ^\nnext") == "LINE 1\n\nnext"


def test_collapse_message_whitespace() -> None:
    assert collapse_message_whitespace("a\n  b\t c") == "a b c"


def test_normalize_quoted_ids_preserves_semantic_names() -> None:
    assert normalize_quoted_ids('column "user_name" missing') == 'column "user_name" missing'


def test_normalize_quoted_ids_replaces_id_like_values() -> None:
    assert normalize_quoted_ids("key 'UserA123456789' missing") == "key <ID> missing"


def test_normalize_sql_numeric_literals() -> None:
    assert normalize_sql_numeric_literals("WHERE id = 42 AND age>=99") == (
        "WHERE id = <N> AND age>=<N>"
    )


def test_truncate_pytest_diff_dump() -> None:
    raw = "assert 'a' == 'b'\n- b\n+ a\nFull diff:"
    assert truncate_pytest_diff_dump(raw) == "assert 'a' == 'b'"


def test_module_basename() -> None:
    assert module_basename("/tmp/project/db.py") == "db"


def test_parse_traceback_frames() -> None:
    raw = '  File "/tmp/app.py", line 2, in handle\n  File "/tmp/db.py", line 3, in fetch'
    assert parse_traceback_frames(raw) == [("app", "handle"), ("db", "fetch")]


def test_truncate_traceback_shape() -> None:
    frames = [("a", "one"), ("b", "two"), ("c", "three"), ("d", "four")]
    assert truncate_traceback_shape(frames) == [("b", "two"), ("c", "three"), ("d", "four")]


def test_build_canonical_string() -> None:
    parsed = ParsedError(
        exception_type="ValueError",
        exception_message="bad value",
        error_kind=ErrorKind.TRACEBACK,
        last_frame_module="app",
        last_frame_function="run",
        traceback_shape=[("app", "run")],
    )
    assert build_canonical_string(parsed) == "ValueError|bad value|app::run|app::run"


def test_signature_hash_is_16_hex_chars() -> None:
    assert len(signature_hash("ValueError|bad|app::run|app::run")) == 16


def test_normalize_common_text_applies_global_rules() -> None:
    raw = '\x1b[31mFile "/Users/alice/app.py", line 99 at 0x7f4a2c1bd000 2026-05-19T04:13:54Z\x1b[0m'
    assert normalize_common_text(raw) == "File \"app.py\", line <N> at <ADDR> <TS>"
