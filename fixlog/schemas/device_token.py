from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from fixlog.schemas.common import ORMModel


class DeviceTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class DeviceTokenRead(ORMModel):
    id: UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class DeviceTokenCreateResponse(DeviceTokenRead):
    token: str
