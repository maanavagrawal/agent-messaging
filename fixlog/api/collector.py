from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi import status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from fixlog.api.shared import (
    load_question_or_none,
    question_read,
    upsert_error_signature,
)
from fixlog.auth.collector import (
    CollectorAuth,
    mark_device_token_used,
    require_collector_auth,
    require_collector_session,
)
from fixlog.db.models import AgentSession, Question
from fixlog.db.session import get_db
from fixlog.schemas.collector_issue import CollectorIssueCreate
from fixlog.schemas.question import QuestionRead

router = APIRouter(prefix="/collector", tags=["collector"])


@router.get("/status")
def collector_status(
    auth: CollectorAuth = Depends(require_collector_auth),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    mark_device_token_used(auth)
    db.commit()
    return {
        "ok": True,
        "account_name": auth.account.human_name,
        "auth_kind": "device_token" if auth.device_token is not None else "account_token",
        "device_token_id": str(auth.device_token.id) if auth.device_token else None,
    }


@router.post(
    "/issues",
    response_model=QuestionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_collector_issue(
    payload: CollectorIssueCreate,
    auth: tuple[CollectorAuth, AgentSession] = Depends(require_collector_session),
    db: Session = Depends(get_db),
) -> QuestionRead:
    collector_auth, session = auth
    signature = upsert_error_signature(db, payload.error_signature)
    existing = db.scalar(
        select(Question)
        .where(
            Question.session_id == session.id,
            Question.error_signature_id == signature.id,
        )
        .order_by(desc(Question.created_at))
    )
    mark_device_token_used(collector_auth)
    if existing is not None:
        db.commit()
        return question_read(db, existing)

    question = Question(
        account_id=collector_auth.account.id,
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
        raise RuntimeError("Created collector issue could not be reloaded")
    return question_read(db, loaded)
