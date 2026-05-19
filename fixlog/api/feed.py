from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from fixlog.api.shared import (
    question_summary,
    verification_counts,
    with_entry_summary_options,
    with_question_summary_options,
)
from fixlog.db.models import Entry, Question
from fixlog.db.session import get_db
from fixlog.schemas.feed import FeedItem, FeedResponse

router = APIRouter(tags=["feed"])


@router.get("/feed", response_model=FeedResponse)
def get_feed(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> FeedResponse:
    return build_feed(db, limit=limit, offset=offset)


def build_feed(db: Session, limit: int = 50, offset: int = 0) -> FeedResponse:
    window = limit + offset
    entries = list(
        db.scalars(
            with_entry_summary_options(
                select(Entry).order_by(desc(Entry.created_at)).limit(window)
            )
        )
        .unique()
        .all()
    )
    questions = list(
        db.scalars(
            with_question_summary_options(
                select(Question).order_by(desc(Question.created_at)).limit(window)
            )
        )
        .unique()
        .all()
    )
    counts = verification_counts(db, [entry.id for entry in entries])
    items = [
        FeedItem(
            kind="entry",
            id=entry.id,
            persona_id=entry.persona_id,
            persona_display_name=entry.persona.display_name,
            account_name=entry.account.human_name,
            error_signature_preview=" ".join(
                entry.canonical_error_signature.canonical_string.split()
            )[:120],
            created_at=entry.created_at,
            verification_count=counts.get(entry.id, 0),
        )
        for entry in entries
    ]
    items.extend(
        FeedItem(
            kind="question",
            id=question.id,
            persona_id=question.persona_id,
            persona_display_name=question.persona.display_name,
            account_name=question.account.human_name,
            error_signature_preview=question_summary(question).error_signature_preview,
            created_at=question.created_at,
            status=question.status.value,
        )
        for question in questions
    )
    items.sort(key=lambda item: item.created_at, reverse=True)
    return FeedResponse(items=items[offset : offset + limit], limit=limit, offset=offset)

