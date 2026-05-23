from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
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
from fixlog.auth.collector import generate_device_token
from fixlog.auth.web import (
    WEB_SESSION_COOKIE,
    account_from_request,
    account_from_viewer_access_code,
    create_web_session_cookie,
)
from fixlog.config import get_settings
from fixlog.db.models import (
    Account,
    AgentPersona,
    AgentSession,
    DeviceToken,
    Entry,
    EntryAlsoMatch,
    ErrorSignature,
    Question,
    QuestionStatus,
    SessionEvent,
    utc_now,
)
from fixlog.db.seed import token_hash
from fixlog.db.session import get_db
from fixlog.normalizer.python import normalize_python_error
from fixlog.schemas.search import SearchResponse
from fixlog.schemas.session_event import (
    SessionEventListResponse,
    SessionEventRead,
)
from fixlog.web.agent_skill import build_agent_skill_markdown
from fixlog.web.install_script import build_collector_install_script, normalize_public_url

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


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    next: str = "/settings/devices",
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "next_path": _safe_next_path(next),
            "error": None,
            "public_url": _public_url(request),
        },
    )


@router.post("/login", response_class=Response)
async def login_submit(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    settings = get_settings()
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    access_code = form.get("access_code", [""])[0].strip()
    next_path = _safe_next_path(form.get("next", ["/settings/devices"])[0])
    account = account_from_viewer_access_code(access_code, db)
    if account is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next_path": next_path,
                "error": "That access code was not recognized.",
                "public_url": _public_url(request),
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    cookie_value = create_web_session_cookie(account, settings)
    response = RedirectResponse(next_path, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        WEB_SESSION_COOKIE,
        cookie_value,
        max_age=settings.fixlog_web_session_ttl_seconds,
        httponly=True,
        secure=settings.web_cookie_secure,
        samesite="lax",
    )
    return response


@router.post("/logout", response_class=Response)
def logout() -> Response:
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(WEB_SESSION_COOKIE)
    return response


@router.get("/agent", response_class=HTMLResponse)
def agent_onboarding_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "agent_onboarding.html",
        {"public_url": _public_url(request)},
    )


@router.get("/skill.md", response_class=PlainTextResponse)
def agent_skill(request: Request) -> PlainTextResponse:
    return PlainTextResponse(
        build_agent_skill_markdown(public_url=_public_url(request)),
        media_type="text/markdown",
    )


@router.get("/install.sh", response_class=PlainTextResponse)
def collector_install_script(request: Request) -> PlainTextResponse:
    settings = get_settings()
    script = build_collector_install_script(
        base_url=_public_url(request),
        package_url=settings.fixlog_collector_package_url,
    )
    return PlainTextResponse(script, media_type="text/x-shellscript")


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


@router.get("/settings/devices", response_class=HTMLResponse)
def device_settings_page(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    account = _dashboard_account(request, authorization, db)
    return _device_settings_response(request, account, db)


@router.post("/settings/devices", response_class=HTMLResponse)
async def create_device_settings_token(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    account = _dashboard_account(request, authorization, db)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    name = form.get("name", [""])[0].strip() or "Local collector"
    raw_token = generate_device_token()
    device_token = DeviceToken(
        account_id=account.id,
        name=name[:200],
        token_hash=token_hash(raw_token),
    )
    db.add(device_token)
    db.commit()
    return _device_settings_response(
        request,
        account,
        db,
        created_token=raw_token,
        created_name=device_token.name,
    )


@router.post("/settings/devices/{device_token_id}/revoke", response_class=HTMLResponse)
def revoke_device_settings_token(
    device_token_id: UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    account = _dashboard_account(request, authorization, db)
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
    return _device_settings_response(request, account, db)


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
    account = _dashboard_account(request, authorization, db)
    session = _session_for_dashboard(account, session_id, x_fixlog_session_id, db)
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


def _safe_next_path(value: str) -> str:
    if not value.startswith("/") or value.startswith("//"):
        return "/"
    return value


def _device_settings_response(
    request: Request,
    account: Account,
    db: Session,
    *,
    created_token: str | None = None,
    created_name: str | None = None,
) -> HTMLResponse:
    rows = db.scalars(
        select(DeviceToken)
        .where(DeviceToken.account_id == account.id)
        .order_by(DeviceToken.created_at.desc())
    ).all()
    public_url = _public_url(request)
    return templates.TemplateResponse(
        request,
        "device_settings.html",
        {
            "account": account,
            "device_tokens": rows,
            "created_token": created_token,
            "created_name": created_name,
            "public_url": public_url.rstrip("/"),
        },
    )


def _public_url(request: Request) -> str:
    configured_url = get_settings().fixlog_public_url.rstrip("/")
    if configured_url:
        return normalize_public_url(configured_url)
    hostname = request.url.hostname or ""
    if hostname in {"127.0.0.1", "::1", "localhost", "testserver"}:
        return str(request.base_url).rstrip("/")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="FIXLOG_PUBLIC_URL is required for public setup links",
    )


def _dashboard_account(
    request: Request,
    authorization: str | None,
    db: Session,
) -> Account:
    settings = get_settings()
    if authorization is not None:
        return account_from_authorization(authorization, db)
    account = account_from_request(request, db, settings)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Dashboard login required",
        )
    return account


def _session_for_dashboard(
    account: Account,
    session_id: UUID,
    x_fixlog_session_id: str | None,
    db: Session,
) -> AgentSession:
    if x_fixlog_session_id is not None:
        session = session_from_header(account, x_fixlog_session_id, db)
        if session.id != session_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="URL session_id does not match X-Fixlog-Session-Id",
            )
        return session

    session = db.scalar(
        select(AgentSession)
        .options(joinedload(AgentSession.persona).joinedload(AgentPersona.account))
        .where(AgentSession.id == session_id)
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    return session


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
