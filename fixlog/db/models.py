from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, Uuid


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


def enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class EmbeddingBlob384(TypeDecorator[bytes]):
    """Nullable sqlite-vec-compatible 384-dimension embedding blob.

    Phase 1 never writes embeddings. sqlite-vec extension loading is configured
    in the DB session layer when available; vector virtual tables and fuzzy
    matching are Phase 2.
    """

    impl = LargeBinary
    cache_ok = True


class UTCDateTime(TypeDecorator[datetime]):
    """Store datetimes in UTC and always return timezone-aware values."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: object
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(
        self, value: datetime | None, dialect: object
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class AccountStatus(StrEnum):
    ACTIVE = "active"
    THROTTLED = "throttled"
    BANNED = "banned"


class Language(StrEnum):
    PYTHON = "python"


class QuestionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DUPLICATE_OF = "duplicate_of"


class SandboxKind(StrEnum):
    DOCKER = "docker"
    VENV = "venv"
    NODE = "node"
    NONE = "none"


class VerifierKind(StrEnum):
    AUTO_SANDBOX = "auto_sandbox"
    AGENT_IN_CONTEXT = "agent_in_context"
    AGENT_OUT_OF_CONTEXT = "agent_out_of_context"
    HUMAN_CLI = "human_cli"


class VerificationResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


class SessionEventKind(StrEnum):
    SESSION_START = "session_start"
    USER_MESSAGE = "user_message"
    AGENT_MESSAGE = "agent_message"
    TOOL_RESULT = "tool_result"
    SESSION_END = "session_end"
    STUCK_EMITTED = "stuck_emitted"
    AGENT_ACTION = "agent_action"
    HUMAN_ACTION = "human_action"
    ERROR = "error"
    TOOL_CALL = "tool_call"
    EDIT = "edit"
    MESSAGE = "message"


class ErrorKind(StrEnum):
    TRACEBACK = "traceback"
    PYTEST = "pytest"
    PIP = "pip"
    GENERIC = "generic"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(timezone=True), default=utc_now, nullable=False
    )
    api_token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    human_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[AccountStatus] = mapped_column(
        Enum(
            AccountStatus,
            native_enum=False,
            values_callable=enum_values,
            validate_strings=True,
        ),
        default=AccountStatus.ACTIVE,
        nullable=False,
    )

    personas: Mapped[list[AgentPersona]] = relationship(back_populates="account")
    questions: Mapped[list[Question]] = relationship(back_populates="account")
    entries: Mapped[list[Entry]] = relationship(back_populates="account")


class AgentPersona(Base):
    __tablename__ = "agent_personas"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "model_name", "harness_name", name="uq_persona_identity"
        ),
        CheckConstraint("length(id) = 8", name="ck_agent_persona_id_len"),
    )

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id"), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    harness_name: Mapped[str] = mapped_column(String(200), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(
        UTCDateTime(timezone=True), default=utc_now, nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        UTCDateTime(timezone=True), default=utc_now, nullable=False
    )

    account: Mapped[Account] = relationship(back_populates="personas")
    sessions: Mapped[list[AgentSession]] = relationship(back_populates="persona")
    questions: Mapped[list[Question]] = relationship(back_populates="persona")
    entries: Mapped[list[Entry]] = relationship(back_populates="persona")


class AgentSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    persona_id: Mapped[str] = mapped_column(
        ForeignKey("agent_personas.id"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        UTCDateTime(timezone=True), default=utc_now, nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(timezone=True), nullable=True
    )
    last_heartbeat: Mapped[datetime] = mapped_column(
        UTCDateTime(timezone=True), default=utc_now, nullable=False
    )
    source_tool: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    source_tool_session_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True, index=True
    )

    persona: Mapped[AgentPersona] = relationship(back_populates="sessions")
    questions: Mapped[list[Question]] = relationship(back_populates="session")
    entries: Mapped[list[Entry]] = relationship(back_populates="session")
    events: Mapped[list[SessionEvent]] = relationship(back_populates="session")


class SessionEvent(Base):
    __tablename__ = "session_events"
    __table_args__ = (Index("ix_session_events_session_ts", "session_id", "ts"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
    ts: Mapped[datetime] = mapped_column(
        UTCDateTime(timezone=True), default=utc_now, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    session: Mapped[AgentSession] = relationship(back_populates="events")


class ErrorSignature(Base):
    __tablename__ = "error_signatures"
    __table_args__ = (
        CheckConstraint("length(hash) = 16", name="ck_error_signature_hash_len"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_string: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str] = mapped_column(
        String(16), nullable=False, unique=True, index=True
    )
    raw_examples: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    language: Mapped[Language] = mapped_column(
        Enum(
            Language,
            native_enum=False,
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    framework: Mapped[str | None] = mapped_column(String(200), nullable=True)
    embedding: Mapped[bytes | None] = mapped_column(EmbeddingBlob384, nullable=True)
    exception_type: Mapped[str | None] = mapped_column(String(300), nullable=True)
    exception_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_frame_module: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_frame_function: Mapped[str | None] = mapped_column(String(200), nullable=True)
    traceback_shape: Mapped[list[list[str]] | None] = mapped_column(JSON, nullable=True)
    error_kind: Mapped[ErrorKind | None] = mapped_column(
        Enum(
            ErrorKind,
            native_enum=False,
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=True,
    )
    was_chained: Mapped[bool | None] = mapped_column(default=False, nullable=True)

    questions: Mapped[list[Question]] = relationship(back_populates="error_signature")
    entries: Mapped[list[Entry]] = relationship(
        back_populates="canonical_error_signature"
    )
    also_match_links: Mapped[list[EntryAlsoMatch]] = relationship(
        back_populates="error_signature"
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id"), nullable=False, index=True
    )
    persona_id: Mapped[str] = mapped_column(
        ForeignKey("agent_personas.id"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
    error_signature_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("error_signatures.id"), nullable=False, index=True
    )
    env_context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    attempts_made: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    status: Mapped[QuestionStatus] = mapped_column(
        Enum(
            QuestionStatus,
            native_enum=False,
            values_callable=enum_values,
            validate_strings=True,
        ),
        default=QuestionStatus.OPEN,
        nullable=False,
        index=True,
    )
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("questions.id"), nullable=True
    )
    agent_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    account: Mapped[Account] = relationship(back_populates="questions")
    persona: Mapped[AgentPersona] = relationship(back_populates="questions")
    session: Mapped[AgentSession] = relationship(back_populates="questions")
    error_signature: Mapped[ErrorSignature] = relationship(back_populates="questions")
    duplicate_question: Mapped[Question | None] = relationship(remote_side=[id])
    linked_entry_links: Mapped[list[QuestionEntryLink]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id"), nullable=False, index=True
    )
    persona_id: Mapped[str] = mapped_column(
        ForeignKey("agent_personas.id"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
    canonical_error_signature_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("error_signatures.id"), nullable=False, index=True
    )
    env_context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    fix_diff: Mapped[str] = mapped_column(Text, nullable=False)
    fix_explanation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reproduction_setup: Mapped[str] = mapped_column(Text, nullable=False)
    reproduction_trigger: Mapped[str] = mapped_column(Text, nullable=False)
    reproduction_verify: Mapped[str] = mapped_column(Text, nullable=False)
    sandbox_kind: Mapped[SandboxKind] = mapped_column(
        Enum(
            SandboxKind,
            native_enum=False,
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    sandbox_spec: Mapped[str] = mapped_column(Text, nullable=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("entries.id"), nullable=True
    )
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    account: Mapped[Account] = relationship(back_populates="entries")
    persona: Mapped[AgentPersona] = relationship(back_populates="entries")
    session: Mapped[AgentSession] = relationship(back_populates="entries")
    canonical_error_signature: Mapped[ErrorSignature] = relationship(
        back_populates="entries"
    )
    superseding_entry: Mapped[Entry | None] = relationship(remote_side=[id])
    also_match_links: Mapped[list[EntryAlsoMatch]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )
    linked_question_links: Mapped[list[QuestionEntryLink]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )
    verifications: Mapped[list[Verification]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )
    edits: Mapped[list[Edit]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )


class EntryAlsoMatch(Base):
    __tablename__ = "entry_also_matches"
    __table_args__ = (
        UniqueConstraint("entry_id", "error_signature_id", name="uq_entry_also_match"),
    )

    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entries.id"), primary_key=True
    )
    error_signature_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("error_signatures.id"), primary_key=True
    )

    entry: Mapped[Entry] = relationship(back_populates="also_match_links")
    error_signature: Mapped[ErrorSignature] = relationship(
        back_populates="also_match_links"
    )


class QuestionEntryLink(Base):
    __tablename__ = "question_entry_links"
    __table_args__ = (
        UniqueConstraint("question_id", "entry_id", name="uq_question_entry_link"),
    )

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id"), primary_key=True
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entries.id"), primary_key=True
    )
    linked_at: Mapped[datetime] = mapped_column(
        UTCDateTime(timezone=True), default=utc_now, nullable=False
    )
    linked_by_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id"), nullable=False
    )

    question: Mapped[Question] = relationship(back_populates="linked_entry_links")
    entry: Mapped[Entry] = relationship(back_populates="linked_question_links")
    linked_by_account: Mapped[Account] = relationship()


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entries.id"), nullable=False, index=True
    )
    ts: Mapped[datetime] = mapped_column(
        UTCDateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    verifier_kind: Mapped[VerifierKind] = mapped_column(
        Enum(
            VerifierKind,
            native_enum=False,
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    verifier_id: Mapped[str] = mapped_column(String(80), nullable=False)
    result: Mapped[VerificationResult] = mapped_column(
        Enum(
            VerificationResult,
            native_enum=False,
            values_callable=enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    env_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    entry: Mapped[Entry] = relationship(back_populates="verifications")


class Edit(Base):
    __tablename__ = "edits"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entries.id"), nullable=False, index=True
    )
    ts: Mapped[datetime] = mapped_column(
        UTCDateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    editor_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id"), nullable=False, index=True
    )
    field_changed: Mapped[str] = mapped_column(String(120), nullable=False)
    old_value: Mapped[str] = mapped_column(Text, nullable=False)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    entry: Mapped[Entry] = relationship(back_populates="edits")
    editor_account: Mapped[Account] = relationship()


Index("ix_feed_entries_created_at", Entry.created_at.desc())
Index("ix_feed_questions_created_at", Question.created_at.desc())
