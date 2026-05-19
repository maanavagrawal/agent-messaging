from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class FeedItem(BaseModel):
    kind: Literal["question", "entry"]
    id: UUID
    persona_id: str
    persona_display_name: str
    account_name: str
    error_signature_preview: str
    created_at: datetime
    status: str | None = None
    verification_count: int | None = None


class FeedResponse(BaseModel):
    items: list[FeedItem]
    limit: int
    offset: int

