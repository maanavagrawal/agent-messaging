from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fixlog.auth.collector import (
    CollectorAuth,
    mark_device_token_used,
    require_collector_auth,
)
from fixlog.db.session import get_db

router = APIRouter(prefix="/collector", tags=["collector"])


@router.get("/status")
def collector_status(
    auth: CollectorAuth = Depends(require_collector_auth),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    mark_device_token_used(auth)
    db.commit()
    return {
        "ok": True,
        "account_name": auth.account.human_name,
        "auth_kind": "device_token" if auth.device_token is not None else "account_token",
        "device_token_id": str(auth.device_token.id) if auth.device_token else None,
    }
