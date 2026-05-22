from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, joinedload

from fixlog.api.feed import build_feed
from fixlog.api.sessions import build_active_sessions
from fixlog.api.shared import (
    entry_read,
    entry_summary,
    load_entry_or_none,
    load_question_or_none,
    question_read,
    verification_counts,
    with_entry_summary_options,
)
from fixlog.auth.deps import account_from_authorization, session_from_header
from fixlog.db.models import (
    AgentPersona,
    AgentSession,
    Entry,
    EntryAlsoMatch,
    ErrorSignature,
    Question,
    QuestionStatus,
    SessionEvent,
)
from fixlog.db.session import get_db
from fixlog.normalizer.python import normalize_python_error
from fixlog.schemas.search import SearchResponse
from fixlog.schemas.session_event import (
    SessionEventListResponse,
    SessionEventRead,
)

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory="fixlog/web/templates")


def _relative_time(value: datetime) -> str:
    now = datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    delta = now - value.astimezone(UTC)
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def _clean_signature(value: str) -> str:
    return " ".join(value.replace("\x1f", " ").split())


def _signature_title(value: str, limit: int = 96) -> str:
    cleaned = _clean_signature(value)
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1].rstrip()}..."


def _short_id(value: object, length: int = 8) -> str:
    return str(value)[:length]


templates.env.filters["relative_time"] = _relative_time
templates.env.filters["clean_signature"] = _clean_signature
templates.env.filters["signature_title"] = _signature_title
templates.env.filters["short_id"] = _short_id


@router.get("/", response_class=HTMLResponse)
def feed_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    feed = build_feed(db, limit=50, offset=0)
    entry_count = db.scalar(select(func.count(Entry.id))) or 0
    open_question_count = (
        db.scalar(
            select(func.count(Question.id)).where(Question.status == QuestionStatus.OPEN)
        )
        or 0
    )
    return templates.TemplateResponse(
        request,
        "feed.html",
        {
            "feed": feed,
            "entry_count": entry_count,
            "open_question_count": open_question_count,
        },
    )


@router.get("/partials/feed-list", response_class=HTMLResponse)
def feed_list_partial(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    feed = build_feed(db, limit=50, offset=0)
    return templates.TemplateResponse(
        request,
        "partials/feed_list.html",
        {"feed": feed},
    )


@router.get("/sessions/active", response_class=HTMLResponse)
def active_sessions_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    sessions = build_active_sessions(db)
    return templates.TemplateResponse(
        request,
        "active_sessions.html",
        {"sessions": sessions},
    )


@router.get("/sessions/{session_id}/events/view", response_class=Response)
def session_events_page(
    session_id: UUID,
    request: Request,
    limit: int = 50,
    offset: int = 0,
    kind: str | None = None,
    authorization: str | None = Header(default=None),
    x_fixlog_session_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Response:
    account = account_from_authorization(authorization, db)
    session = session_from_header(account, x_fixlog_session_id, db)
    if session.id != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="URL session_id does not match X-Fixlog-Session-Id",
        )
    events = _session_events(db, session_id, limit=limit, offset=offset, kind=kind)
    if not _wants_html(request):
        payload = SessionEventListResponse(
            items=[SessionEventRead.model_validate(event) for event in events],
            limit=min(max(limit, 1), 200),
            offset=offset,
        )
        return JSONResponse(payload.model_dump(mode="json"))

    loaded_session = db.scalar(
        select(AgentSession)
        .options(joinedload(AgentSession.persona).joinedload(AgentPersona.account))
        .where(AgentSession.id == session_id)
    )
    if loaded_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    rows = [
        {
            "event": event,
            "payload_json": json.dumps(
                event.payload, indent=2, sort_keys=True, default=str
            ),
        }
        for event in events
    ]
    return templates.TemplateResponse(
        request,
        "session_events.html",
        {"session": loaded_session, "events": rows},
    )


@router.get("/search/errors", response_class=HTMLResponse)
def error_search_page(
    request: Request,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    result = _search_entries_for_web(error, db) if error else None
    return templates.TemplateResponse(
        request,
        "search_results.html",
        {"query": error or "", "result": result, "result_limit": WEB_SEARCH_LIMIT},
    )


@router.get("/entries/{entry_id}", response_class=Response)
def entry_detail_page(
    entry_id: UUID, request: Request, db: Session = Depends(get_db)
) -> Response:
    entry = load_entry_or_none(db, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    payload = entry_read(entry)
    if _wants_html(request):
        return templates.TemplateResponse(
            request,
            "entry_detail.html",
            {"entry": payload},
        )
    return JSONResponse(payload.model_dump(mode="json"))


@router.get("/questions/{question_id}", response_class=Response)
def question_detail_page(
    question_id: UUID, request: Request, db: Session = Depends(get_db)
) -> Response:
    question = load_question_or_none(db, question_id)
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Question not found"
        )
    payload = question_read(db, question)
    if _wants_html(request):
        return templates.TemplateResponse(
            request,
            "question_detail.html",
            {"question": payload},
        )
    return JSONResponse(payload.model_dump(mode="json"))


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept and "application/json" not in accept


def _session_events(
    db: Session,
    session_id: UUID,
    limit: int,
    offset: int,
    kind: str | None,
) -> list[SessionEvent]:
    capped_limit = min(max(limit, 1), 200)
    stmt = (
        select(SessionEvent)
        .where(SessionEvent.session_id == session_id)
        .order_by(desc(SessionEvent.ts))
        .offset(offset)
        .limit(capped_limit)
    )
    if kind is not None:
        stmt = stmt.where(SessionEvent.kind == kind)
    return list(db.scalars(stmt).all())


WEB_SEARCH_LIMIT = 25


def _search_entries_for_web(
    error: str, db: Session, limit: int = WEB_SEARCH_LIMIT
) -> SearchResponse:
    hash_value = normalize_python_error(error).hash
    signature = db.scalar(select(ErrorSignature).where(ErrorSignature.hash == hash_value))
    if signature is None:
        return SearchResponse(entries=[], exact_match=False)

    also_match_entry_ids = select(EntryAlsoMatch.entry_id).where(
        EntryAlsoMatch.error_signature_id == signature.id
    )
    entries = list(
        db.scalars(
            with_entry_summary_options(
                select(Entry)
                .where(
                    or_(
                        Entry.canonical_error_signature_id == signature.id,
                        Entry.id.in_(also_match_entry_ids),
                    )
                )
                .order_by(desc(Entry.created_at))
                .limit(limit)
            )
        )
        .unique()
        .all()
    )
    counts = verification_counts(db, [entry.id for entry in entries])
    return SearchResponse(
        entries=[entry_summary(entry, counts.get(entry.id, 0)) for entry in entries],
        exact_match=True,
    )
