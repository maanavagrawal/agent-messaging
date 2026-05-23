from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from fixlog.auth.collector import (
    CollectorAuth,
    mark_device_token_used,
    require_collector_auth,
    require_collector_session,
)
from fixlog.auth.deps import require_session
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
    auth: CollectorAuth = Depends(require_collector_auth),
    db: Session = Depends(get_db),
) -> SessionStartResponse:
    account = auth.account
    account_id = account.id
    now = utc_now()
    persona = _get_or_create_persona(
        db,
        account_id=account_id,
        model_name=payload.model_name,
        harness_name=payload.harness_name,
        now=now,
    )
    existing_session = _session_for_source(db, persona=persona, payload=payload)
    if existing_session is not None:
        existing_session.last_heartbeat = now
        persona.last_seen = now
        mark_device_token_used(auth)
        db.commit()
        return _session_start_response(existing_session, persona)

    session = AgentSession(
        persona=persona,
        started_at=now,
        last_heartbeat=now,
        source_tool=payload.source_tool,
        source_tool_session_id=payload.source_tool_session_id,
    )
    mark_device_token_used(auth)
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info(
        "session created id=%s persona=%s account=%s", session.id, persona.id, account_id
    )
    return _session_start_response(session, persona)


def _session_start_response(
    session: AgentSession,
    persona: AgentPersona,
) -> SessionStartResponse:
    return SessionStartResponse(
        session_id=session.id,
        persona_id=persona.id,
        persona_display_name=persona.display_name,
        account_reputation=0.0,
        persona_reputation=0.0,
    )


def _session_for_source(
    db: Session,
    *,
    persona: AgentPersona,
    payload: SessionStartRequest,
) -> AgentSession | None:
    if payload.source_tool is None or payload.source_tool_session_id is None:
        return None
    return db.scalar(
        select(AgentSession)
        .where(
            AgentSession.persona_id == persona.id,
            AgentSession.source_tool == payload.source_tool,
            AgentSession.source_tool_session_id == payload.source_tool_session_id,
        )
        .order_by(AgentSession.started_at.desc())
    )


def _get_or_create_persona(
    db: Session,
    *,
    account_id: UUID,
    model_name: str,
    harness_name: str,
    now: datetime,
) -> AgentPersona:
    stmt = select(AgentPersona).where(
        AgentPersona.account_id == account_id,
        AgentPersona.model_name == model_name,
        AgentPersona.harness_name == harness_name,
    )
    persona = db.scalar(stmt)
    if persona is not None:
        persona.last_seen = now
        return persona

    persona_id = persona_id_for(account_id, model_name, harness_name)
    persona = AgentPersona(
        id=persona_id,
        account_id=account_id,
        display_name=display_name_for_persona(persona_id),
        model_name=model_name,
        harness_name=harness_name,
        first_seen=now,
        last_seen=now,
    )
    try:
        with db.begin_nested():
            db.add(persona)
            db.flush()
    except IntegrityError:
        persona = db.scalar(stmt)
        if persona is None:
            raise
        persona.last_seen = now
    return persona


@router.post("/{session_id}/heartbeat", response_model=SessionHeartbeatResponse)
def heartbeat_session(
    session_id: UUID,
    auth: tuple[CollectorAuth, AgentSession] = Depends(require_collector_session),
    db: Session = Depends(get_db),
) -> SessionHeartbeatResponse:
    collector_auth, session = auth
    if session.id != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="URL session_id does not match X-Fixlog-Session-Id",
        )
    now = utc_now()
    session.last_heartbeat = now
    session.persona.last_seen = now
    mark_device_token_used(collector_auth)
    db.commit()
    return SessionHeartbeatResponse(ok=True)


@router.post("/active", response_model=ActiveSessionsResponse)
def active_sessions(db: Session = Depends(get_db)) -> ActiveSessionsResponse:
    return ActiveSessionsResponse(items=build_active_sessions(db))


@router.post("/{session_id}/events", response_model=SessionEventCreateResponse)
def create_session_event(
    session_id: UUID,
    payload: SessionEventCreate,
    auth: tuple[CollectorAuth, AgentSession] = Depends(require_collector_session),
    db: Session = Depends(get_db),
) -> SessionEventCreateResponse:
    collector_auth, session = auth
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
    mark_device_token_used(collector_auth)
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
