from __future__ import annotations

import re

from fixlog.normalizer.models import ErrorKind, ParsedError

# Matches pip's "Could not find a version" resolver failure. It intentionally
# requires the pip-style ERROR prefix.
VERSION_NOT_FOUND_RE = re.compile(
    r"^ERROR:\s+Could not find a version that satisfies the requirement\s+(.+)$",
    re.MULTILINE,
)

# Matches pip dependency resolver conflict messages. It intentionally requires
# dependency and conflict wording somewhere on the same ERROR line.
DEPENDENCY_CONFLICT_RE = re.compile(
    r"^ERROR:\s+(.+)$",
    re.IGNORECASE | re.MULTILINE,
)

# Matches any pip-style ERROR line. It intentionally only captures the first
# line so large resolver dumps do not dominate the signature.
PIP_ERROR_RE = re.compile(r"^ERROR:\s+(.+)$", re.MULTILINE)


def parse_pip_error(raw: str) -> ParsedError | None:
    """Return ParsedError for pip/package-manager error output.

    Uses fixed synthetic exception types: pip.VersionNotFound,
    pip.DependencyConflict, or pip.InstallError. Returns None when the input is
    not pip-like.
    """
    version_match = VERSION_NOT_FOUND_RE.search(raw)
    if version_match:
        return ParsedError(
            exception_type="pip.VersionNotFound",
            exception_message=f"Could not find a version that satisfies the requirement {version_match.group(1)}",
            error_kind=ErrorKind.PIP,
        )

    for conflict_match in DEPENDENCY_CONFLICT_RE.finditer(raw):
        conflict_line = conflict_match.group(1)
        lowered = conflict_line.lower()
        if "dependenc" not in lowered or "conflict" not in lowered:
            continue
        return ParsedError(
            exception_type="pip.DependencyConflict",
            exception_message=conflict_line,
            error_kind=ErrorKind.PIP,
        )

    error_match = PIP_ERROR_RE.search(raw)
    if error_match:
        return ParsedError(
            exception_type="pip.InstallError",
            exception_message=error_match.group(1),
            error_kind=ErrorKind.PIP,
        )

    return None
