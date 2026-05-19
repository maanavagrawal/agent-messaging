from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fixlog.api.feed import build_feed
from fixlog.api.shared import entry_read, load_entry_or_none, load_question_or_none, question_read
from fixlog.db.models import Entry, Question
from fixlog.db.session import get_db

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


def _badge_style(persona_id: str) -> str:
    color = persona_id[:6].ljust(6, "0")
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    text = "#111827" if luminance > 0.62 else "#ffffff"
    return f"background-color: #{color}; color: {text};"


templates.env.filters["relative_time"] = _relative_time
templates.env.filters["badge_style"] = _badge_style


@router.get("/", response_class=HTMLResponse)
def feed_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    feed = build_feed(db, limit=50, offset=0)
    entry_count = db.scalar(select(func.count(Entry.id))) or 0
    question_count = db.scalar(select(func.count(Question.id))) or 0
    return templates.TemplateResponse(
        request,
        "feed.html",
        {
            "feed": feed,
            "entry_count": entry_count,
            "question_count": question_count,
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

