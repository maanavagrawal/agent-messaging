from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from fixlog.api.shared import (
    load_question_or_none,
    question_read,
    question_summary,
    upsert_error_signature,
    with_question_summary_options,
)
from fixlog.auth.deps import require_account, require_session
from fixlog.db.models import (
    Account,
    AgentSession,
    Entry,
    Question,
    QuestionEntryLink,
    QuestionStatus,
)
from fixlog.db.session import get_db
from fixlog.schemas.question import (
    QuestionCreate,
    QuestionLinkEntryRequest,
    QuestionListResponse,
    QuestionRead,
    QuestionStatusSchema,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("", response_model=QuestionListResponse)
def list_questions(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: QuestionStatusSchema | None = None,
    db: Session = Depends(get_db),
) -> QuestionListResponse:
    stmt = select(Question).order_by(desc(Question.created_at)).offset(offset).limit(limit)
    if status is not None:
        stmt = stmt.where(Question.status == QuestionStatus(status.value))
    questions = list(db.scalars(with_question_summary_options(stmt)).unique().all())
    return QuestionListResponse(
        items=[question_summary(question) for question in questions],
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=QuestionRead, status_code=status.HTTP_201_CREATED)
def create_question(
    payload: QuestionCreate,
    auth: tuple[Account, AgentSession] = Depends(require_session),
    db: Session = Depends(get_db),
) -> QuestionRead:
    account, session = auth
    signature = upsert_error_signature(db, payload.error_signature)
    question = Question(
        account_id=account.id,
        persona_id=session.persona_id,
        session_id=session.id,
        error_signature_id=signature.id,
        env_context=payload.env_context.model_dump(),
        attempts_made=payload.attempts_made,
        agent_metadata=payload.agent_metadata.model_dump(),
    )
    db.add(question)
    db.commit()
    loaded = load_question_or_none(db, question.id)
    if loaded is None:
        raise RuntimeError("Created question could not be reloaded")
    logger.info("question created id=%s account=%s persona=%s", loaded.id, account.id, session.persona_id)
    return question_read(db, loaded)


@router.post("/{question_id}/link_entry", response_model=QuestionRead)
def link_entry_to_question(
    question_id: UUID,
    payload: QuestionLinkEntryRequest,
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
) -> QuestionRead:
    question = load_question_or_none(db, question_id)
    entry = db.get(Entry, payload.entry_id)
    if question is None or entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question and entry must both exist",
        )
    existing = db.get(
        QuestionEntryLink,
        {"question_id": question.id, "entry_id": entry.id},
    )
    if existing is None:
        db.add(
            QuestionEntryLink(
                question_id=question.id,
                entry_id=entry.id,
                linked_by_account_id=account.id,
            )
        )
        db.commit()
    loaded = load_question_or_none(db, question.id)
    if loaded is None:
        raise RuntimeError("Linked question could not be reloaded")
    return question_read(db, loaded)
