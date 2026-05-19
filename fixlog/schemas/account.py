from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from fixlog.schemas.common import ORMModel


class AccountStatusSchema(StrEnum):
    ACTIVE = "active"
    THROTTLED = "throttled"
    BANNED = "banned"


class AccountRead(ORMModel):
    id: UUID
    created_at: datetime
    human_name: str
    status: AccountStatusSchema

