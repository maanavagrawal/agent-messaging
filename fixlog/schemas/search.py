from __future__ import annotations

from pydantic import BaseModel

from fixlog.schemas.entry import EntrySummary


class SearchResponse(BaseModel):
    entries: list[EntrySummary]
    exact_match: bool
