from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from fixlog.auth.deps import account_from_authorization, session_from_header
from fixlog.db.models import Account, AgentSession, DeviceToken, utc_now
from fixlog.db.seed import token_hash
from fixlog.db.session import get_db

DEVICE_TOKEN_PREFIX = "flxdt_"


@dataclass(frozen=True)
class CollectorAuth:
    account: Account
    device_token: DeviceToken | None = None


def generate_device_token() -> str:
    return f"{DEVICE_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def require_collector_auth(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> CollectorAuth:
    return collector_auth_from_authorization(authorization, db)


def collector_auth_from_authorization(
    authorization: str | None,
    db: Session,
) -> CollectorAuth:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    raw_token = authorization.removeprefix("Bearer ").strip()
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    if raw_token.startswith(DEVICE_TOKEN_PREFIX):
        device_token = db.scalar(
            select(DeviceToken)
            .options(joinedload(DeviceToken.account))
            .where(
                DeviceToken.token_hash == token_hash(raw_token),
                DeviceToken.revoked_at.is_(None),
            )
        )
        if device_token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token",
            )
        return CollectorAuth(account=device_token.account, device_token=device_token)

    return CollectorAuth(account=account_from_authorization(authorization, db))


def require_collector_session(
    auth: CollectorAuth = Depends(require_collector_auth),
    x_fixlog_session_id: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> tuple[CollectorAuth, AgentSession]:
    return auth, session_from_header(auth.account, x_fixlog_session_id, db)


def mark_device_token_used(auth: CollectorAuth) -> None:
    if auth.device_token is not None:
        auth.device_token.last_used_at = utc_now()
