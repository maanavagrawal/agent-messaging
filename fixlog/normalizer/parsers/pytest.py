from __future__ import annotations

import re

from fixlog.normalizer.common import module_basename, truncate_pytest_diff_dump
from fixlog.normalizer.models import ErrorKind, ParsedError

# Matches pytest's one-line failed-node summary. It intentionally requires the
# FAILED prefix and a node id so ordinary text containing "failed" is ignored.
FAILED_SUMMARY_RE = re.compile(r"^FAILED\s+([^\s]+?)\s+-\s+([A-Za-z_][\w.]*):\s*(.*)$")

# Matches pytest's one-line errored-node summary. It intentionally mirrors the
# FAILED parser and does not match generic "ERROR:" log lines.
ERROR_SUMMARY_RE = re.compile(r"^ERROR\s+([^\s]+?)\s+-\s+([A-Za-z_][\w.]*):\s*(.*)$")

# Matches pytest setup/fixture section headers. It intentionally only captures
# the test function name from pytest's "ERROR at ..." wording.
ERROR_AT_SETUP_RE = re.compile(r"ERROR at .* of ([A-Za-z_][\w]*(?:\[[^\]]+\])?)")

# Matches pytest "E   ValueError: message" exception echo lines. It intentionally
# requires the pytest E-prefix indentation.
PYTEST_E_EXCEPTION_RE = re.compile(r"^E\s+([A-Za-z_][\w.]*):\s*(.*)$")


def _split_node_id(node_id: str) -> tuple[str | None, str | None]:
    parts = node_id.split("::")
    if not parts:
        return None, None
    module = module_basename(parts[0])
    function = parts[-1] if len(parts) > 1 else None
    if function is not None:
        function = re.sub(r"\[[^\]]+\]$", "", function)
    return module, function


def _parse_summary_line(raw: str) -> ParsedError | None:
    for line in raw.splitlines():
        match = FAILED_SUMMARY_RE.match(line.strip()) or ERROR_SUMMARY_RE.match(line.strip())
        if match is None:
            continue
        module, function = _split_node_id(match.group(1))
        message = truncate_pytest_diff_dump(match.group(3))
        shape = [(module, function)] if module is not None and function is not None else []
        return ParsedError(
            exception_type=match.group(2),
            exception_message=message,
            error_kind=ErrorKind.PYTEST,
            last_frame_module=module,
            last_frame_function=function,
            traceback_shape=shape,
        )
    return None


def _parse_setup_error(raw: str) -> ParsedError | None:
    setup_function: str | None = None
    for line in raw.splitlines():
        setup_match = ERROR_AT_SETUP_RE.search(line.strip())
        if setup_match:
            setup_function = re.sub(r"\[[^\]]+\]$", "", setup_match.group(1))
            break
    if setup_function is None and "::test_" not in raw:
        return None

    for line in raw.splitlines():
        exception_match = PYTEST_E_EXCEPTION_RE.match(line.strip())
        if exception_match:
            return ParsedError(
                exception_type=exception_match.group(1),
                exception_message=truncate_pytest_diff_dump(exception_match.group(2)),
                error_kind=ErrorKind.PYTEST,
                last_frame_function=setup_function,
                traceback_shape=[],
            )
    return None


def parse_pytest_error(raw: str) -> ParsedError | None:
    """Return ParsedError for pytest failure output with strong pytest markers.

    Extracts pytest node id/module/function when available, keeps the first
    assertion line, and drops trailing diff/dump output. Returns None when the
    input is not recognizably pytest output.
    """
    return _parse_summary_line(raw) or _parse_setup_error(raw)
