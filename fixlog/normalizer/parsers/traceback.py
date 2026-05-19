from __future__ import annotations

import re

from fixlog.normalizer.common import (
    parse_traceback_frames,
    truncate_traceback_shape,
)
from fixlog.normalizer.models import ErrorKind, ParsedError

# Matches the CPython traceback header. It intentionally does not match pytest's
# short failure summaries without a real traceback block.
TRACEBACK_HEADER_RE = re.compile(r"^Traceback \(most recent call last\):\s*$", re.MULTILINE)

# Matches Python exception lines such as "ValueError: bad" or
# "psycopg2.errors.UndefinedColumn: ...". It intentionally requires a colon.
EXCEPTION_LINE_RE = re.compile(r"^\s*([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*):\s*(.*)$")

CHAIN_MARKERS = (
    "During handling of the above exception, another exception occurred",
    "The above exception was the direct cause of the following exception",
)


def _find_exception_line(lines: list[str]) -> int | None:
    for index in range(len(lines) - 1, -1, -1):
        if EXCEPTION_LINE_RE.match(lines[index]):
            return index
    return None


def parse_traceback_error(raw: str) -> ParsedError | None:
    """Return ParsedError for a standard Python traceback.

    Uses the last exception in a chained traceback and truncates the traceback
    shape to the last 3 frames in execution order. Returns None when no standard
    traceback can be parsed.
    """
    matches = list(TRACEBACK_HEADER_RE.finditer(raw))
    if not matches:
        return None

    section = raw[matches[-1].start() :]
    section_lines = section.splitlines()
    exception_index = _find_exception_line(section_lines)
    if exception_index is None:
        return None

    exception_match = EXCEPTION_LINE_RE.match(section_lines[exception_index])
    if exception_match is None:
        return None

    exception_type = exception_match.group(1)
    message_lines = [exception_match.group(2)]
    for line in section_lines[exception_index + 1 :]:
        if TRACEBACK_HEADER_RE.match(line):
            break
        if any(marker in line for marker in CHAIN_MARKERS):
            break
        message_lines.append(line)

    frames = truncate_traceback_shape(parse_traceback_frames(section))
    last_module: str | None = None
    last_function: str | None = None
    if frames:
        last_module, last_function = frames[-1]

    return ParsedError(
        exception_type=exception_type,
        exception_message="\n".join(message_lines).strip(),
        error_kind=ErrorKind.TRACEBACK,
        last_frame_module=last_module,
        last_frame_function=last_function,
        traceback_shape=frames,
        was_chained=any(marker in raw for marker in CHAIN_MARKERS),
    )
