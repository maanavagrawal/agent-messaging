from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from fixlog.auth.collector import generate_device_token
from fixlog.auth.deps import require_account
from fixlog.db.models import Account, DeviceToken, utc_now
from fixlog.db.seed import token_hash
from fixlog.db.session import get_db
from fixlog.schemas.device_token import (
    DeviceTokenCreate,
    DeviceTokenCreateResponse,
    DeviceTokenRead,
)

router = APIRouter(prefix="/device-tokens", tags=["device-tokens"])


@router.get("", response_model=list[DeviceTokenRead])
def list_device_tokens(
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
) -> list[DeviceTokenRead]:
    rows = db.scalars(
        select(DeviceToken)
        .where(DeviceToken.account_id == account.id)
        .order_by(desc(DeviceToken.created_at))
    ).all()
    return [DeviceTokenRead.model_validate(row) for row in rows]


@router.post(
    "",
    response_model=DeviceTokenCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_device_token(
    payload: DeviceTokenCreate,
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
) -> DeviceTokenCreateResponse:
    raw_token = generate_device_token()
    device_token = DeviceToken(
        account_id=account.id,
        name=payload.name.strip(),
        token_hash=token_hash(raw_token),
    )
    db.add(device_token)
    db.commit()
    db.refresh(device_token)
    body = DeviceTokenRead.model_validate(device_token).model_dump()
    return DeviceTokenCreateResponse(**body, token=raw_token)


@router.post("/{device_token_id}/revoke", response_model=DeviceTokenRead)
def revoke_device_token(
    device_token_id: UUID,
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
) -> DeviceTokenRead:
    device_token = db.scalar(
        select(DeviceToken).where(
            DeviceToken.id == device_token_id,
            DeviceToken.account_id == account.id,
        )
    )
    if device_token is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device token not found",
        )
    if device_token.revoked_at is None:
        device_token.revoked_at = utc_now()
        db.commit()
        db.refresh(device_token)
    return DeviceTokenRead.model_validate(device_token)
