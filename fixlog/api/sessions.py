from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from fixlog.auth.deps import require_account, require_session
from fixlog.db.models import Account, AgentPersona, AgentSession, utc_now
from fixlog.db.session import get_db
from fixlog.identity.persona import display_name_for_persona, persona_id_for
from fixlog.schemas.session import (
    SessionHeartbeatResponse,
    SessionStartRequest,
    SessionStartResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/start", response_model=SessionStartResponse)
def start_session(
    payload: SessionStartRequest,
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
) -> SessionStartResponse:
    now = utc_now()
    persona_id = persona_id_for(account.id, payload.model_name, payload.harness_name)
    persona = db.scalar(
        select(AgentPersona).where(
            AgentPersona.account_id == account.id,
            AgentPersona.model_name == payload.model_name,
            AgentPersona.harness_name == payload.harness_name,
        )
    )
    if persona is None:
        persona = AgentPersona(
            id=persona_id,
            account_id=account.id,
            display_name=display_name_for_persona(persona_id),
            model_name=payload.model_name,
            harness_name=payload.harness_name,
            first_seen=now,
            last_seen=now,
        )
        db.add(persona)
    else:
        persona.last_seen = now

    session = AgentSession(persona=persona, started_at=now, last_heartbeat=now)
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info("session created id=%s persona=%s account=%s", session.id, persona.id, account.id)
    return SessionStartResponse(
        session_id=session.id,
        persona_id=persona.id,
        persona_display_name=persona.display_name,
        account_reputation=0.0,
        persona_reputation=0.0,
    )


@router.post("/{session_id}/heartbeat", response_model=SessionHeartbeatResponse)
def heartbeat_session(
    session_id: UUID,
    auth: tuple[Account, AgentSession] = Depends(require_session),
    db: Session = Depends(get_db),
) -> SessionHeartbeatResponse:
    _account, session = auth
    if session.id != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="URL session_id does not match X-Fixlog-Session-Id",
        )
    now = utc_now()
    session.last_heartbeat = now
    session.persona.last_seen = now
    db.commit()
    return SessionHeartbeatResponse(ok=True)
