from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from fixlog_harness.models import NormalizedEvent


class LogParser(ABC):
    @abstractmethod
    def parse_line(self, line: str) -> list[NormalizedEvent]:
        """Parse one log line into zero or more redacted normalized events.

        Returns an empty list for skipped or unrecognized lines. A single log
        line may produce multiple events when the source message contains both
        text and tool content.
        """

    @abstractmethod
    def initial_events_from_file_header(self, file_path: Path) -> list[NormalizedEvent]:
        """Emit initial redacted events established from the log file header.

        Implementations should inspect leading metadata and return a
        `session_start` event when enough source session context exists. Empty
        or malformed files return an empty list.
        """
