from __future__ import annotations

from pathlib import Path

import pytest

from fixlog.normalizer.python import normalize_python_error

RAW_ROOT = Path(__file__).parent / "fixtures" / "python"


def _same_signature(raw: str, variations: list[str]) -> None:
    base = normalize_python_error(raw)
    for variation in variations:
        changed = normalize_python_error(variation)
        assert changed.canonical_string == base.canonical_string
        assert changed.hash == base.hash


@pytest.mark.parametrize(
    ("fixture_path", "variations"),
    [
        (
            RAW_ROOT / "traceback" / "psycopg_undefined_column.txt",
            [
                (RAW_ROOT / "traceback" / "psycopg_undefined_column.txt")
                .read_text()
                .replace("/home/danny/proj", "/Users/maria/work")
                .replace("line 42", "line 999")
                .replace("id = 42", "id = 123"),
                (RAW_ROOT / "traceback" / "psycopg_undefined_column.txt")
                .read_text()
                .replace("/home/danny/proj", "/srv/builds/run-123")
                .replace("line 18", "line 777"),
                (RAW_ROOT / "traceback" / "psycopg_undefined_column.txt")
                .read_text()
                .replace("id = 42", "id = 987654"),
                (RAW_ROOT / "traceback" / "psycopg_undefined_column.txt")
                .read_text()
                .replace("\n               ^", "\n                      ^"),
                "\x1b[31m"
                + (RAW_ROOT / "traceback" / "psycopg_undefined_column.txt").read_text()
                + "\x1b[0m",
            ],
        ),
        (
            RAW_ROOT / "traceback" / "keyerror_session_id.txt",
            [
                (RAW_ROOT / "traceback" / "keyerror_session_id.txt")
                .read_text()
                .replace("SessionABC123456789", "SessionXYZ987654321"),
                (RAW_ROOT / "traceback" / "keyerror_session_id.txt")
                .read_text()
                .replace("/home/maya/app", "/Users/nora/app")
                .replace("line 105", "line 1"),
                (RAW_ROOT / "traceback" / "keyerror_session_id.txt")
                .read_text()
                .replace("line 88", "line 600"),
                (RAW_ROOT / "traceback" / "keyerror_session_id.txt")
                .read_text()
                .replace("SessionABC123456789", "SessionA1B2C3D4E5"),
                (RAW_ROOT / "traceback" / "keyerror_session_id.txt")
                .read_text()
                .replace("/home/maya/app/server.py", "C:\\Users\\maya\\app\\server.py"),
            ],
        ),
        (
            RAW_ROOT / "traceback" / "import_error.txt",
            [
                (RAW_ROOT / "traceback" / "import_error.txt")
                .read_text()
                .replace("/Users/ivy/proj", "/home/ivy/proj")
                .replace("line 7", "line 70"),
                (RAW_ROOT / "traceback" / "import_error.txt")
                .read_text()
                .replace("/Users/ivy/proj/myapp/config.py", "/tmp/build/myapp/config.py"),
                (RAW_ROOT / "traceback" / "import_error.txt")
                .read_text()
                .replace("line 7", "line 8"),
                "\x1b[33m" + (RAW_ROOT / "traceback" / "import_error.txt").read_text() + "\x1b[0m",
                (RAW_ROOT / "traceback" / "import_error.txt")
                .read_text()
                .replace("/Users/ivy/proj/manage.py", "/opt/src/manage.py"),
            ],
        ),
        (
            RAW_ROOT / "traceback" / "valueerror_in_init.txt",
            [
                (RAW_ROOT / "traceback" / "valueerror_in_init.txt")
                .read_text()
                .replace("abc123XYZ999", "def456UVW888"),
                (RAW_ROOT / "traceback" / "valueerror_in_init.txt")
                .read_text()
                .replace("/Users/pat/proj", "/home/pat/proj"),
                (RAW_ROOT / "traceback" / "valueerror_in_init.txt")
                .read_text()
                .replace("line 5", "line 505"),
                (RAW_ROOT / "traceback" / "valueerror_in_init.txt")
                .read_text()
                .replace("abc123XYZ999", "CountA123456789"),
                "\x1b[35m" + (RAW_ROOT / "traceback" / "valueerror_in_init.txt").read_text(),
            ],
        ),
        (
            RAW_ROOT / "generic" / "json_error_response.txt",
            [
                (RAW_ROOT / "generic" / "json_error_response.txt")
                .read_text()
                .replace("550e8400-e29b-41d4-a716-446655440000", "123e4567-e89b-12d3-a456-426614174000"),
                (RAW_ROOT / "generic" / "json_error_response.txt")
                .read_text()
                .replace("2026-05-19T04:13:54Z", "2026-06-20T05:14:55Z"),
                (RAW_ROOT / "generic" / "json_error_response.txt")
                .read_text()
                .replace("/home/danny/proj/app.py", "/Users/alice/proj/app.py"),
                (RAW_ROOT / "generic" / "json_error_response.txt")
                .read_text()
                .replace("550e8400-e29b-41d4-a716-446655440000", "550e8400e29b41d4a716446655440000"),
                "\x1b[32m" + (RAW_ROOT / "generic" / "json_error_response.txt").read_text() + "\x1b[0m",
            ],
        ),
    ],
    ids=lambda value: value.name if isinstance(value, Path) else "variations",
)
def test_trivial_variations_keep_same_signature(
    fixture_path: Path, variations: list[str]
) -> None:
    _same_signature(fixture_path.read_text(), variations)
