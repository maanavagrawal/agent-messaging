from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath

from fixlog.normalizer.models import ParsedError

CANONICAL_SEPARATOR = "\x1f"

# Matches ANSI CSI terminal color/control sequences. It intentionally does not
# remove arbitrary ESC text outside the standard CSI/control forms.
ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")

# Matches macOS home path prefixes. It stops at the username path component and
# does not consume the rest of the path.
MAC_HOME_RE = re.compile(r"/Users/[^/\s\"'<>]+")

# Matches Linux home path prefixes. It stops at the username path component and
# does not consume the rest of the path.
LINUX_HOME_RE = re.compile(r"/home/[^/\s\"'<>]+")

# Matches Windows user home prefixes. It intentionally only handles the common
# C:\Users\<name> shape, not arbitrary drive layouts.
WINDOWS_HOME_RE = re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"'<>]+")

# Matches absolute POSIX paths in logs. It requires a leading slash and excludes
# whitespace, quotes, and angle brackets so ordinary prose is not swallowed.
POSIX_PATH_RE = re.compile(r"/(?:[^\s\"'<>:]+/)*[^\s\"'<>:]+")

# Matches absolute Windows paths like C:\Users\a\file.py. It does not try to
# parse UNC shares or paths with quoted separators.
WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\(?:[^\\\s\"'<>:]+\\)*[^\\\s\"'<>:]+")

# Matches traceback frame locations such as "line 42". It intentionally only
# replaces the number after the word line.
TRACEBACK_LINE_RE = re.compile(r"\bline\s+\d+\b")

# Matches Python memory addresses such as 0x7f4a2c1bd000. It intentionally
# requires at least 6 hex chars so tiny literals like 0xFF remain meaningful.
MEMORY_ADDRESS_RE = re.compile(r"\b0x[0-9a-fA-F]{6,}\b")

# Matches canonical dashed UUIDs. It runs before the 32-hex UUID pattern so the
# dashed form is replaced as one token.
DASHED_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# Matches compact UUIDs represented as exactly 32 hex chars. Longer hashes are
# left for SHA_LIKE_HASH_RE.
COMPACT_UUID_RE = re.compile(r"\b[0-9a-fA-F]{32}\b")

# Matches SHA-like hex runs longer than 16 chars. It does not match shorter
# IDs because those are often meaningful error codes.
SHA_LIKE_HASH_RE = re.compile(r"\b[0-9a-fA-F]{17,}\b")

# Matches ISO-ish timestamps with seconds, optional fractional seconds, and
# optional timezone. It intentionally does not match date-only strings.
ISO_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)

# Matches slash-separated timestamps used in logs. It intentionally requires
# both date and time so version-like strings are not changed.
COMMON_TIMESTAMP_RE = re.compile(r"\b\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\b")

# Matches IPython/Jupyter input prompt labels like In[5]. It intentionally
# keeps the In[...] structure for recognizability.
IPYTHON_CELL_RE = re.compile(r"\bIn\s*\[\d+\]")

# Matches lines that only contain one or more caret markers. It intentionally
# leaves carets embedded in prose alone.
COLUMN_MARKER_LINE_RE = re.compile(r"(?m)^[ \t]*\^+[ \t]*$")

# Matches quoted values for the simple ID heuristic. It intentionally avoids
# crossing quote boundaries and does not attempt escaped quote parsing.
QUOTED_VALUE_RE = re.compile(r"([\"'])([^\"']+)\1")

# Matches numeric SQL comparison literals such as id = 42. It intentionally
# does not replace version numbers or numbers outside comparison expressions.
SQL_NUMERIC_LITERAL_RE = re.compile(
    r"\b([A-Za-z_][\w.]*\s*(?:<=|>=|<>|!=|=|<|>)\s*)\d+\b"
)

# Matches traceback frame lines. It intentionally only captures CPython's
# standard File "...", line N, in function shape.
TRACEBACK_FRAME_RE = re.compile(r'^\s*File "([^"]+)", line \d+, in ([^\s]+)\s*$')


def strip_ansi_codes(text: str) -> str:
    return ANSI_RE.sub("", text)


def normalize_user_home_paths(text: str) -> str:
    text = MAC_HOME_RE.sub("/Users/<USER>", text)
    text = LINUX_HOME_RE.sub("/home/<USER>", text)
    return WINDOWS_HOME_RE.sub(lambda _match: r"C:\Users\<USER>", text)


def _basename_from_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    return PurePosixPath(normalized).name


def replace_absolute_paths_with_basenames(text: str) -> str:
    text = WINDOWS_PATH_RE.sub(lambda match: _basename_from_path(match.group(0)), text)
    return POSIX_PATH_RE.sub(lambda match: _basename_from_path(match.group(0)), text)


def normalize_traceback_line_numbers(text: str) -> str:
    return TRACEBACK_LINE_RE.sub("line <N>", text)


def normalize_memory_addresses(text: str) -> str:
    return MEMORY_ADDRESS_RE.sub("<ADDR>", text)


def normalize_uuids(text: str) -> str:
    text = DASHED_UUID_RE.sub("<UUID>", text)
    return COMPACT_UUID_RE.sub("<UUID>", text)


def normalize_sha_like_hashes(text: str) -> str:
    return SHA_LIKE_HASH_RE.sub("<HASH>", text)


def normalize_timestamps(text: str) -> str:
    text = ISO_TIMESTAMP_RE.sub("<TS>", text)
    return COMMON_TIMESTAMP_RE.sub("<TS>", text)


def normalize_ipython_cells(text: str) -> str:
    return IPYTHON_CELL_RE.sub("In[<N>]", text)


def strip_column_marker_lines(text: str) -> str:
    return COLUMN_MARKER_LINE_RE.sub("", text)


def collapse_message_whitespace(text: str) -> str:
    return " ".join(text.split())


def _looks_like_quoted_id(value: str) -> bool:
    if len(value) <= 8:
        return False
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return False
    has_digit = any(char.isdigit() for char in value)
    has_lower = any(char.islower() for char in value)
    has_upper = any(char.isupper() for char in value)
    return has_digit or (has_lower and has_upper)


def normalize_quoted_ids(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        value = match.group(2)
        if _looks_like_quoted_id(value):
            return "<ID>"
        return match.group(0)

    return QUOTED_VALUE_RE.sub(replace, text)


def normalize_sql_numeric_literals(text: str) -> str:
    return SQL_NUMERIC_LITERAL_RE.sub(lambda match: f"{match.group(1)}<N>", text)


def truncate_pytest_diff_dump(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if kept and (
            stripped.startswith("- ")
            or stripped.startswith("+ ")
            or stripped.startswith("E   -")
            or stripped.startswith("E   +")
            or stripped.startswith("Full diff:")
        ):
            break
        kept.append(line)
    return "\n".join(kept)


def module_basename(path_or_module: str) -> str:
    if not path_or_module:
        return "<none>"
    normalized = path_or_module.replace("\\", "/")
    name = PurePosixPath(normalized).name
    if name.endswith(".py"):
        name = name[:-3]
    return name or "<none>"


def parse_traceback_frames(text: str) -> list[tuple[str, str]]:
    frames: list[tuple[str, str]] = []
    for line in text.splitlines():
        match = TRACEBACK_FRAME_RE.match(line)
        if match:
            frames.append((module_basename(match.group(1)), match.group(2)))
    return frames


def truncate_traceback_shape(
    frames: list[tuple[str, str]], limit: int = 3
) -> list[tuple[str, str]]:
    return frames[-limit:]


def _canonical_field(value: str | None) -> str:
    if value is None or value == "":
        return "<none>"
    return value.replace(CANONICAL_SEPARATOR, "")


def _shape_to_text(shape: list[tuple[str, str]]) -> str:
    if not shape:
        return "<none>"
    return ">".join(
        f"{_canonical_field(module)}::{_canonical_field(function)}"
        for module, function in shape
    )


def build_canonical_string(parsed: ParsedError) -> str:
    if parsed.canonical_string_override is not None:
        return parsed.canonical_string_override
    module = _canonical_field(parsed.last_frame_module)
    function = _canonical_field(parsed.last_frame_function)
    fields = [
        _canonical_field(parsed.exception_type),
        _canonical_field(parsed.exception_message),
        f"{module}::{function}",
        _shape_to_text(parsed.traceback_shape),
    ]
    return CANONICAL_SEPARATOR.join(fields)


def signature_hash(canonical_string: str) -> str:
    return hashlib.sha256(canonical_string.encode("utf-8")).hexdigest()[:16]


def normalize_common_text(text: str) -> str:
    text = strip_ansi_codes(text)
    text = replace_absolute_paths_with_basenames(text)
    text = normalize_user_home_paths(text)
    text = normalize_traceback_line_numbers(text)
    text = normalize_memory_addresses(text)
    text = normalize_uuids(text)
    text = normalize_sha_like_hashes(text)
    text = normalize_timestamps(text)
    text = normalize_ipython_cells(text)
    text = strip_column_marker_lines(text)
    return text.strip()
