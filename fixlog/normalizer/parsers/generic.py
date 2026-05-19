from __future__ import annotations

import re

from fixlog.normalizer.common import CANONICAL_SEPARATOR
from fixlog.normalizer.models import ErrorKind, ParsedError

# Matches module::function frame tokens in canonical shape text. It intentionally
# ignores malformed frame tokens rather than guessing.
CANONICAL_FRAME_RE = re.compile(r"^([^:>]+)::([^:>]+)$")

# Matches generic ExceptionType: message strings. It is used only to choose a
# useful first line; the synthetic GenericError type remains fixed.
GENERIC_EXCEPTION_LINE_RE = re.compile(r"^\s*([A-Za-z_][\w.]*):\s*(.+)$")


def _parse_location(location: str) -> tuple[str | None, str | None]:
    if "::" not in location:
        return None, None
    module, function = location.split("::", 1)
    return (
        None if module == "<none>" else module,
        None if function == "<none>" else function,
    )


def _parse_shape(shape_text: str) -> list[tuple[str, str]]:
    if shape_text == "<none>":
        return []
    frames: list[tuple[str, str]] = []
    for frame_text in shape_text.split(">"):
        frame_match = CANONICAL_FRAME_RE.match(frame_text)
        if frame_match:
            frames.append((frame_match.group(1), frame_match.group(2)))
    return frames


def parse_canonical_signature(raw: str) -> ParsedError | None:
    """Return ParsedError for an already-built canonical_string.

    Preserves the exact canonical string via canonical_string_override so
    normalizing canonical output is idempotent. Returns None when the input does
    not match the unit-separator canonical format.
    """
    stripped = raw.strip()
    parts = stripped.split(CANONICAL_SEPARATOR)
    if len(parts) != 4:
        return None
    exception_type, exception_message, location, shape_text = parts
    module, function = _parse_location(location)
    return ParsedError(
        exception_type=exception_type,
        exception_message=exception_message,
        error_kind=ErrorKind.GENERIC,
        last_frame_module=module,
        last_frame_function=function,
        traceback_shape=_parse_shape(shape_text),
        canonical_string_override=stripped,
    )


def parse_generic_error(raw: str) -> ParsedError:
    """Return a best-effort ParsedError for any input.

    Uses exception_type='GenericError' and a normalized first useful message
    line. This function never returns None.
    """
    useful_lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not useful_lines:
        message = "<empty>"
    else:
        message = useful_lines[0]
        for line in useful_lines:
            if GENERIC_EXCEPTION_LINE_RE.match(line):
                message = line
                break
    return ParsedError(
        exception_type="GenericError",
        exception_message=message,
        error_kind=ErrorKind.GENERIC,
    )
