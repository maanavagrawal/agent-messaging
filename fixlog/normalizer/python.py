from __future__ import annotations

from dataclasses import replace

from fixlog.normalizer.common import (
    build_canonical_string,
    collapse_message_whitespace,
    normalize_common_text,
    normalize_quoted_ids,
    normalize_sql_numeric_literals,
    signature_hash,
    strip_ansi_codes,
)
from fixlog.normalizer.models import ParsedError, PythonErrorSignature
from fixlog.normalizer.parsers.generic import parse_canonical_signature, parse_generic_error
from fixlog.normalizer.parsers.pip import parse_pip_error
from fixlog.normalizer.parsers.pytest import parse_pytest_error
from fixlog.normalizer.parsers.traceback import parse_traceback_error


def _normalize_parsed(parsed: ParsedError) -> ParsedError:
    if parsed.canonical_string_override is not None:
        return parsed

    message = normalize_common_text(parsed.exception_message)
    message = normalize_quoted_ids(message)
    message = normalize_sql_numeric_literals(message)
    message = collapse_message_whitespace(message)
    return replace(parsed, exception_message=message)


def normalize_python_error(raw: str) -> PythonErrorSignature:
    """Normalize raw Python-related error output into a deterministic signature.

    Dispatch order is canonical input, pytest, traceback, pip, generic. Parser
    output is normalized by common helpers, converted to canonical_string, and
    hashed with sha256(canonical_string)[:16].
    """
    dispatch_input = strip_ansi_codes(raw)
    parsed = (
        parse_canonical_signature(dispatch_input)
        or parse_pytest_error(dispatch_input)
        or parse_traceback_error(dispatch_input)
        or parse_pip_error(dispatch_input)
        or parse_generic_error(dispatch_input)
    )
    normalized = _normalize_parsed(parsed)
    canonical_string = build_canonical_string(normalized)
    return PythonErrorSignature(
        exception_type=normalized.exception_type,
        exception_message=normalized.exception_message,
        last_frame_function=normalized.last_frame_function,
        last_frame_module=normalized.last_frame_module,
        traceback_shape=normalized.traceback_shape,
        canonical_string=canonical_string,
        hash=signature_hash(canonical_string),
        error_kind=normalized.error_kind,
        was_chained=normalized.was_chained,
    )
