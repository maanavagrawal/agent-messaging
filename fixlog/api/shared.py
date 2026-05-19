from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from fixlog.db.models import (
    Account,
    AgentPersona,
    Edit,
    Entry,
    EntryAlsoMatch,
    ErrorSignature,
    Language,
    Question,
    QuestionEntryLink,
    Verification,
)
from fixlog.identity.persona import sha256_hex
from fixlog.schemas.account import AccountRead
from fixlog.schemas.edit import EditRead
from fixlog.schemas.entry import EntryRead, EntrySummary
from fixlog.schemas.error_signature import ErrorSignatureInput, ErrorSignatureRead
from fixlog.schemas.question import QuestionRead, QuestionSummary
from fixlog.schemas.session import AgentPersonaRead
from fixlog.schemas.verification import VerificationRead


def error_signature_hash(canonical_string: str) -> str:
    return sha256_hex(canonical_string)[:16]


def preview(text: str, length: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= length:
        return compact
    return f"{compact[: length - 1]}…"


def upsert_error_signature(
    db: Session, payload: ErrorSignatureInput
) -> ErrorSignature:
    hash_value = error_signature_hash(payload.canonical_string)
    signature = db.scalar(
        select(ErrorSignature).where(ErrorSignature.hash == hash_value)
    )
    if signature is not None:
        return signature
    signature = ErrorSignature(
        canonical_string=payload.canonical_string,
        hash=hash_value,
        raw_examples=payload.raw_examples,
        language=Language(payload.language.value),
        framework=payload.framework,
        embedding=None,
    )
    db.add(signature)
    db.flush()
    return signature


def entry_detail_options() -> tuple[object, ...]:
    return (
        joinedload(Entry.account),
        joinedload(Entry.persona),
        joinedload(Entry.canonical_error_signature),
        selectinload(Entry.also_match_links).joinedload(EntryAlsoMatch.error_signature),
        selectinload(Entry.verifications),
        selectinload(Entry.edits),
    )


def question_detail_options() -> tuple[object, ...]:
    return (
        joinedload(Question.account),
        joinedload(Question.persona),
        joinedload(Question.error_signature),
        selectinload(Question.linked_entry_links)
        .joinedload(QuestionEntryLink.entry)
        .joinedload(Entry.account),
        selectinload(Question.linked_entry_links)
        .joinedload(QuestionEntryLink.entry)
        .joinedload(Entry.persona),
        selectinload(Question.linked_entry_links)
        .joinedload(QuestionEntryLink.entry)
        .joinedload(Entry.canonical_error_signature),
        selectinload(Question.linked_entry_links)
        .joinedload(QuestionEntryLink.entry)
        .selectinload(Entry.verifications),
    )


def load_entry_or_none(db: Session, entry_id: UUID) -> Entry | None:
    return db.scalar(
        select(Entry).options(*entry_detail_options()).where(Entry.id == entry_id)
    )


def load_question_or_none(db: Session, question_id: UUID) -> Question | None:
    return db.scalar(
        select(Question)
        .options(*question_detail_options())
        .where(Question.id == question_id)
    )


def verification_counts(db: Session, entry_ids: Iterable[UUID]) -> dict[UUID, int]:
    ids = list(entry_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Verification.entry_id, func.count(Verification.id))
        .where(Verification.entry_id.in_(ids))
        .group_by(Verification.entry_id)
    ).all()
    return {entry_id: count for entry_id, count in rows}


def account_read(account: Account) -> AccountRead:
    return AccountRead.model_validate(account)


def persona_read(persona: AgentPersona) -> AgentPersonaRead:
    return AgentPersonaRead.model_validate(persona)


def error_signature_read(signature: ErrorSignature) -> ErrorSignatureRead:
    return ErrorSignatureRead.model_validate(signature)


def verification_read(verification: Verification) -> VerificationRead:
    return VerificationRead.model_validate(verification)


def edit_read(edit: Edit) -> EditRead:
    return EditRead.model_validate(edit)


def entry_summary(entry: Entry, verification_count: int | None = None) -> EntrySummary:
    count = verification_count if verification_count is not None else len(entry.verifications)
    return EntrySummary(
        id=entry.id,
        created_at=entry.created_at,
        persona_id=entry.persona_id,
        persona_display_name=entry.persona.display_name,
        account_name=entry.account.human_name,
        error_signature_preview=preview(entry.canonical_error_signature.canonical_string),
        verification_count=count,
        superseded_by=entry.superseded_by,
        tags=entry.tags,
    )


def question_summary(question: Question) -> QuestionSummary:
    return QuestionSummary(
        id=question.id,
        created_at=question.created_at,
        persona_id=question.persona_id,
        persona_display_name=question.persona.display_name,
        account_name=question.account.human_name,
        error_signature_preview=preview(question.error_signature.canonical_string),
        status=question.status,
    )


def entry_read(entry: Entry) -> EntryRead:
    return EntryRead(
        id=entry.id,
        created_at=entry.created_at,
        account_id=entry.account_id,
        persona_id=entry.persona_id,
        session_id=entry.session_id,
        error_signature=error_signature_read(entry.canonical_error_signature),
        also_matches=[
            error_signature_read(link.error_signature) for link in entry.also_match_links
        ],
        env_context=entry.env_context,
        diagnosis=entry.diagnosis,
        fix_diff=entry.fix_diff,
        fix_explanation=entry.fix_explanation,
        reproduction_setup=entry.reproduction_setup,
        reproduction_trigger=entry.reproduction_trigger,
        reproduction_verify=entry.reproduction_verify,
        sandbox_kind=entry.sandbox_kind,
        sandbox_spec=entry.sandbox_spec,
        superseded_by=entry.superseded_by,
        tags=entry.tags,
        account=account_read(entry.account),
        persona=persona_read(entry.persona),
        verification_log=[
            verification_read(item)
            for item in sorted(entry.verifications, key=lambda item: item.ts, reverse=True)
        ],
        edit_history=[
            edit_read(item) for item in sorted(entry.edits, key=lambda item: item.ts, reverse=True)
        ],
    )


def question_read(db: Session, question: Question) -> QuestionRead:
    linked_entries = [link.entry for link in question.linked_entry_links]
    counts = verification_counts(db, [entry.id for entry in linked_entries])
    return QuestionRead(
        id=question.id,
        created_at=question.created_at,
        account_id=question.account_id,
        persona_id=question.persona_id,
        session_id=question.session_id,
        error_signature=error_signature_read(question.error_signature),
        env_context=question.env_context,
        attempts_made=question.attempts_made,
        status=question.status,
        duplicate_of=question.duplicate_of,
        agent_metadata=question.agent_metadata,
        account=account_read(question.account),
        persona=persona_read(question.persona),
        linked_entries=[
            entry_summary(entry, counts.get(entry.id, 0)) for entry in linked_entries
        ],
    )


def with_entry_summary_options(stmt: Select[tuple[Entry]]) -> Select[tuple[Entry]]:
    return stmt.options(
        joinedload(Entry.account),
        joinedload(Entry.persona),
        joinedload(Entry.canonical_error_signature),
        selectinload(Entry.verifications),
    )


def with_question_summary_options(stmt: Select[tuple[Question]]) -> Select[tuple[Question]]:
    return stmt.options(
        joinedload(Question.account),
        joinedload(Question.persona),
        joinedload(Question.error_signature),
    )
