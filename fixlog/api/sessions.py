from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from fixlog.auth.deps import require_account, require_session
from fixlog.db.models import Account, AgentPersona, AgentSession, SessionEvent, utc_now
from fixlog.db.session import get_db
from fixlog.identity.persona import display_name_for_persona, persona_id_for
from fixlog.schemas.session import (
    SessionHeartbeatResponse,
    SessionStartRequest,
    SessionStartResponse,
)
from fixlog.schemas.session_event import (
    ActiveSessionSummary,
    ActiveSessionsResponse,
    SessionEventCreate,
    SessionEventCreateResponse,
    SessionEventListResponse,
    SessionEventRead,
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

    session = AgentSession(
        persona=persona,
        started_at=now,
        last_heartbeat=now,
        source_tool=payload.source_tool,
        source_tool_session_id=payload.source_tool_session_id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info(
        "session created id=%s persona=%s account=%s", session.id, persona.id, account.id
    )
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


@router.post("/active", response_model=ActiveSessionsResponse)
def active_sessions(db: Session = Depends(get_db)) -> ActiveSessionsResponse:
    return ActiveSessionsResponse(items=build_active_sessions(db))


@router.post("/{session_id}/events", response_model=SessionEventCreateResponse)
def create_session_event(
    session_id: UUID,
    payload: SessionEventCreate,
    auth: tuple[Account, AgentSession] = Depends(require_session),
    db: Session = Depends(get_db),
) -> SessionEventCreateResponse:
    _account, session = auth
    if session.id != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="URL session_id does not match X-Fixlog-Session-Id",
        )
    event = SessionEvent(
        session_id=session.id,
        ts=payload.ts,
        kind=payload.kind,
        payload=payload.payload,
    )
    session.last_heartbeat = utc_now()
    db.add(event)
    db.commit()
    db.refresh(event)
    logger.info(
        "session event created id=%s session=%s kind=%s",
        event.id,
        session.id,
        event.kind,
    )
    return SessionEventCreateResponse(event_id=event.id)


@router.get("/{session_id}/events", response_model=SessionEventListResponse)
def list_session_events(
    session_id: UUID,
    limit: int = 50,
    offset: int = 0,
    kind: str | None = None,
    auth: tuple[Account, AgentSession] = Depends(require_session),
    db: Session = Depends(get_db),
) -> SessionEventListResponse:
    _account, session = auth
    if session.id != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="URL session_id does not match X-Fixlog-Session-Id",
        )
    capped_limit = min(max(limit, 1), 200)
    stmt = (
        select(SessionEvent)
        .where(SessionEvent.session_id == session_id)
        .order_by(SessionEvent.ts.desc())
        .offset(offset)
        .limit(capped_limit)
    )
    if kind is not None:
        stmt = stmt.where(SessionEvent.kind == kind)
    events = db.scalars(stmt).all()
    return SessionEventListResponse(
        items=[SessionEventRead.model_validate(event) for event in events],
        limit=capped_limit,
        offset=offset,
    )


def build_active_sessions(db: Session) -> list[ActiveSessionSummary]:
    now = utc_now()
    active_cutoff = now - timedelta(seconds=600)
    hour_cutoff = now - timedelta(seconds=3600)
    sessions = db.scalars(
        select(AgentSession)
        .options(
            joinedload(AgentSession.persona).joinedload(AgentPersona.account),
            selectinload(AgentSession.events),
        )
        .where(AgentSession.last_heartbeat >= active_cutoff)
        .order_by(AgentSession.last_heartbeat.desc())
        .limit(100)
    ).all()
    summaries: list[ActiveSessionSummary] = []
    for session in sessions:
        session_events = sorted(session.events, key=lambda item: item.ts, reverse=True)
        if not session_events:
            continue
        recent_events = [event for event in session_events if event.ts >= hour_cutoff]
        counted_events = recent_events or session_events
        project_slug = _latest_payload_value(session_events, "project_slug")
        source_tool = session.source_tool or _latest_payload_value(
            session_events, "source_tool"
        )
        summaries.append(
            ActiveSessionSummary(
                session_id=session.id,
                persona_id=session.persona_id,
                persona_display_name=session.persona.display_name,
                account_name=session.persona.account.human_name,
                source_tool=source_tool,
                source_tool_session_id=session.source_tool_session_id,
                project_slug=project_slug,
                event_count_last_hour=len(counted_events),
                redaction_count=sum(
                    1 for event in session_events if event.payload.get("redacted") is True
                ),
                stuck_emitted=any(
                    event.kind == "stuck_emitted" for event in session_events
                ),
                last_event_at=session.last_heartbeat,
            )
        )
    return sorted(summaries, key=lambda item: item.last_event_at, reverse=True)


def _latest_payload_value(events: list[SessionEvent], key: str) -> str | None:
    for event in sorted(events, key=lambda item: item.ts, reverse=True):
        value = event.payload.get(key)
        if isinstance(value, str):
            return value
    return None
