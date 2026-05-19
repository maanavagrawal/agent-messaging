from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from fixlog.api.shared import upsert_error_signature
from fixlog.config import get_settings
from fixlog.db.models import (
    Account,
    AgentPersona,
    AgentSession,
    Base,
    Edit,
    Entry,
    EntryAlsoMatch,
    Question,
    QuestionEntryLink,
    SandboxKind,
    Verification,
    VerificationResult,
    VerifierKind,
    utc_now,
)
from fixlog.db.seed import seed_accounts_from_settings
from fixlog.db.session import SessionLocal, engine
from fixlog.identity.persona import display_name_for_persona, persona_id_for
from fixlog.schemas.error_signature import ErrorSignatureInput

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ENTRY_RAW_ERRORS = [
    """Traceback (most recent call last):
  File "/seed/app.py", line 10, in load_user
    return users[user_id]
KeyError: 'SeedUserABC123456789'
""",
    """Traceback (most recent call last):
  File "/seed/db.py", line 22, in query_user
    cursor.execute(sql)
psycopg2.errors.UndefinedColumn: column "display_name" does not exist
LINE 1: SELECT display_name FROM users WHERE id = 101
               ^
""",
    """FAILED tests/test_seed.py::test_total - AssertionError: assert 3 == 4
- 4
+ 3
""",
    "ERROR: Could not find a version that satisfies the requirement seedpkg==99.0",
    """Traceback (most recent call last):
  File "/seed/worker.py", line 40, in run
    client.send(payload)
AttributeError: 'NoneType' object has no attribute 'send'
""",
    """Traceback (most recent call last):
  File "/seed/config.py", line 12, in parse
    int(value)
ValueError: invalid literal for int() with base 10: 'SeedABC123456789'
""",
    "RuntimeError: worker failed for path /Users/seed/jobs/output.json",
    """Traceback (most recent call last):
  File "/seed/tree.py", line 5, in visit
    return visit(node.parent)
  File "/seed/tree.py", line 5, in visit
    return visit(node.parent)
  File "/seed/tree.py", line 5, in visit
    return visit(node.parent)
RecursionError: maximum recursion depth exceeded
""",
    "FAILED tests/test_seed.py::test_title - AssertionError: assert 'Seed A' == 'Seed B'",
    """Traceback (most recent call last):
  File "/seed/importer.py", line 3, in <module>
    from seed.settings import missing
ImportError: cannot import name 'missing' from 'seed.settings' (/seed/settings.py)
""",
]

QUESTION_RAW_ERRORS = [
    f"Traceback (most recent call last):\n  File \"/seed/question_{index}.py\", line {index + 1}, in run\n    raise ValueError(\"SeedQuestionABC{index}123456\")\nValueError: SeedQuestionABC{index}123456\n"
    for index in range(5)
]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    settings = get_settings()
    with SessionLocal() as db:
        accounts = seed_accounts_from_settings(db, settings)
        personas = _seed_personas(db, accounts)
        sessions = [_session_for_persona(db, persona) for persona in personas]
        entries = _seed_entries(db, sessions)
        questions = _seed_questions(db, sessions)
        _seed_links(db, questions, entries, accounts[0].id)
        _seed_verifications(db, entries, accounts)
        _seed_edits_and_supersession(db, entries, accounts[0].id)
        db.commit()
    logger.info("dev seed complete")


def _seed_personas(db: Session, accounts: list[Account]) -> list[AgentPersona]:
    combos = [
        ("claude-sonnet-4-5", "codex"),
        ("gpt-5.4", "local-harness"),
    ]
    personas: list[AgentPersona] = []
    now = utc_now()
    for account in accounts:
        for model_name, harness_name in combos:
            persona_id = persona_id_for(account.id, model_name, harness_name)
            persona = db.get(AgentPersona, persona_id)
            if persona is None:
                persona = AgentPersona(
                    id=persona_id,
                    account_id=account.id,
                    display_name=display_name_for_persona(persona_id),
                    model_name=model_name,
                    harness_name=harness_name,
                    first_seen=now,
                    last_seen=now,
                )
                db.add(persona)
            else:
                persona.last_seen = now
            personas.append(persona)
    db.flush()
    return personas


def _session_for_persona(db: Session, persona: AgentPersona) -> AgentSession:
    session = db.scalar(
        select(AgentSession)
        .where(AgentSession.persona_id == persona.id)
        .order_by(AgentSession.started_at)
    )
    if session is None:
        session = AgentSession(persona_id=persona.id)
        db.add(session)
        db.flush()
    return session


def _seed_entries(db: Session, sessions: list[AgentSession]) -> list[Entry]:
    entries: list[Entry] = []
    for index in range(10):
        session = sessions[index % len(sessions)]
        persona = db.get(AgentPersona, session.persona_id)
        if persona is None:
            raise RuntimeError("Seed persona missing")
        signature = upsert_error_signature(
            db,
            ErrorSignatureInput(
                raw_text=ENTRY_RAW_ERRORS[index],
                raw_examples=[ENTRY_RAW_ERRORS[index]],
                language="python",
                framework=None,
            ),
        )
        entry = db.scalar(
            select(Entry).where(Entry.canonical_error_signature_id == signature.id)
        )
        if entry is None:
            entry = Entry(
                account_id=persona.account_id,
                persona_id=persona.id,
                session_id=session.id,
                canonical_error_signature_id=signature.id,
                env_context=_env(index),
                diagnosis=f"Seed diagnosis {index}",
                fix_diff=f"--- a/seed_{index}.py\n+++ b/seed_{index}.py\n@@ -1 +1 @@\n-broken\n+fixed\n",
                fix_explanation=f"Seed explanation {index}",
                reproduction_setup="python -m venv .venv && pip install -r requirements.txt",
                reproduction_trigger=f"python seed_{index}.py",
                reproduction_verify="pytest",
                sandbox_kind=SandboxKind.VENV,
                sandbox_spec="pytest==9.0.3",
                tags=["seed", f"case-{index}"],
            )
            db.add(entry)
            db.flush()
        if index < 3:
            also = upsert_error_signature(
                db,
                ErrorSignatureInput(
                    raw_text=f"AlternateSeedError{index}: same fix",
                    raw_examples=[],
                    language="python",
                    framework=None,
                ),
            )
            link = db.get(
                EntryAlsoMatch,
                {"entry_id": entry.id, "error_signature_id": also.id},
            )
            if link is None:
                db.add(EntryAlsoMatch(entry_id=entry.id, error_signature_id=also.id))
        entries.append(entry)
    return entries


def _seed_questions(db: Session, sessions: list[AgentSession]) -> list[Question]:
    questions: list[Question] = []
    for index in range(5):
        session = sessions[index % len(sessions)]
        persona = db.get(AgentPersona, session.persona_id)
        if persona is None:
            raise RuntimeError("Seed persona missing")
        signature = upsert_error_signature(
            db,
            ErrorSignatureInput(
                raw_text=QUESTION_RAW_ERRORS[index],
                raw_examples=[QUESTION_RAW_ERRORS[index]],
                language="python",
                framework=None,
            ),
        )
        question = db.scalar(
            select(Question).where(
                Question.error_signature_id == signature.id,
                Question.persona_id == persona.id,
            )
        )
        if question is None:
            question = Question(
                account_id=persona.account_id,
                persona_id=persona.id,
                session_id=session.id,
                error_signature_id=signature.id,
                env_context=_env(index),
                attempts_made=[f"Seed attempt {index}"],
                agent_metadata={
                    "model": persona.model_name,
                    "harness": persona.harness_name,
                    "tools_available": ["shell", "pytest"],
                },
            )
            db.add(question)
            db.flush()
        questions.append(question)
    return questions


def _seed_links(
    db: Session, questions: list[Question], entries: list[Entry], account_id: UUID
) -> None:
    for question, entry in zip(questions[:2], entries[:2], strict=True):
        link = db.get(
            QuestionEntryLink,
            {"question_id": question.id, "entry_id": entry.id},
        )
        if link is None:
            db.add(
                QuestionEntryLink(
                    question_id=question.id,
                    entry_id=entry.id,
                    linked_by_account_id=account_id,
                )
            )


def _seed_verifications(db: Session, entries: list[Entry], accounts: list[Account]) -> None:
    results = [
        VerificationResult.PASS,
        VerificationResult.FAIL,
        VerificationResult.PARTIAL,
        VerificationResult.PASS,
        VerificationResult.PASS,
        VerificationResult.FAIL,
        VerificationResult.PARTIAL,
        VerificationResult.PASS,
    ]
    for index, result in enumerate(results):
        entry = entries[index]
        notes = f"seed verification {index}"
        existing = db.scalar(
            select(Verification).where(
                Verification.entry_id == entry.id,
                Verification.notes == notes,
            )
        )
        if existing is None:
            account = accounts[index % len(accounts)]
            db.add(
                Verification(
                    entry_id=entry.id,
                    verifier_kind=VerifierKind.HUMAN_CLI,
                    verifier_id=str(account.id),
                    result=result,
                    env_snapshot=entry.env_context,
                    notes=notes,
                )
            )


def _seed_edits_and_supersession(db: Session, entries: list[Entry], account_id: UUID) -> None:
    for index, entry in enumerate(entries[:2]):
        reason = f"seed edit {index}"
        existing = db.scalar(
            select(Edit).where(Edit.entry_id == entry.id, Edit.reason == reason)
        )
        if existing is None:
            old_value = entry.fix_explanation or ""
            entry.fix_explanation = f"{old_value} (seed polished)"
            db.add(
                Edit(
                    entry_id=entry.id,
                    editor_account_id=account_id,
                    field_changed="fix_explanation",
                    old_value=old_value,
                    new_value=entry.fix_explanation,
                    reason=reason,
                )
            )

    old_entry, new_entry = entries[0], entries[1]
    if old_entry.superseded_by != new_entry.id:
        old_value = str(old_entry.superseded_by) if old_entry.superseded_by else ""
        old_entry.superseded_by = new_entry.id
        db.add(
            Edit(
                entry_id=old_entry.id,
                editor_account_id=account_id,
                field_changed="superseded_by",
                old_value=old_value,
                new_value=str(new_entry.id),
                reason="seed supersession",
            )
        )


def _env(index: int) -> dict[str, object]:
    return {
        "language_version": "3.12",
        "framework_version": None,
        "key_deps": {"pytest": "9.0.3", "case": str(index)},
        "os": "darwin",
    }


if __name__ == "__main__":
    main()
