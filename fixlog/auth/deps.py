from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from fixlog.db.models import Account, AgentSession
from fixlog.db.seed import token_hash
from fixlog.db.session import get_db


def require_account(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> Account:
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

    account = db.scalar(
        select(Account).where(Account.api_token_hash == token_hash(raw_token))
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )
    return account


def require_session(
    account: Account = Depends(require_account),
    x_fixlog_session_id: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> tuple[Account, AgentSession]:
    if x_fixlog_session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Fixlog-Session-Id header",
        )
    try:
        session_id = UUID(x_fixlog_session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-Fixlog-Session-Id header",
        ) from exc

    agent_session = db.scalar(
        select(AgentSession)
        .options(joinedload(AgentSession.persona))
        .where(AgentSession.id == session_id)
    )
    if agent_session is None or agent_session.persona.account_id != account.id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session does not belong to authenticated account",
        )
    return account, agent_session
