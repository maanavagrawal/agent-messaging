from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from fixlog.schemas.common import ORMModel


class EntryPatchRequest(BaseModel):
    field_changed: str
    new_value: str
    reason: str


class EntrySupersedeRequest(BaseModel):
    new_entry_id: UUID
    reason: str


class EditRead(ORMModel):
    id: UUID
    entry_id: UUID
    ts: datetime
    editor_account_id: UUID
    field_changed: str
    old_value: str
    new_value: str
    reason: str

