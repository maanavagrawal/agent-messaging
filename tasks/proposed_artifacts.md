# fixlog Phase 1 Proposed Artifacts

This is the pre-implementation proposal for approval. It is not source code yet.

## 1. `fixlog/db/models.py`

```python
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


class EmbeddingBlob384(TypeDecorator[bytes]):
    """Nullable sqlite-vec-compatible 384-dimension embedding blob.

    Phase 1 never writes embeddings. sqlite-vec connection loading is configured
    in the DB session layer; vector virtual tables and fuzzy search are Phase 2.
    """

    impl = LargeBinary
    cache_ok = True


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
    AGENT_ACTION = "agent_action"
    HUMAN_ACTION = "human_action"
    ERROR = "error"
    TOOL_CALL = "tool_call"
    EDIT = "edit"
    MESSAGE = "message"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    api_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    human_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[AccountStatus] = mapped_column(Enum(AccountStatus, native_enum=False), default=AccountStatus.ACTIVE, nullable=False)

    personas: Mapped[list[AgentPersona]] = relationship(back_populates="account")
    questions: Mapped[list[Question]] = relationship(back_populates="account")
    entries: Mapped[list[Entry]] = relationship(back_populates="account")


class AgentPersona(Base):
    __tablename__ = "agent_personas"
    __table_args__ = (
        UniqueConstraint("account_id", "model_name", "harness_name", name="uq_persona_account_model_harness"),
        CheckConstraint("length(id) = 8", name="ck_agent_persona_id_len"),
    )

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    harness_name: Mapped[str] = mapped_column(String(200), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    account: Mapped[Account] = relationship(back_populates="personas")
    sessions: Mapped[list[AgentSession]] = relationship(back_populates="persona")
    questions: Mapped[list[Question]] = relationship(back_populates="persona")
    entries: Mapped[list[Entry]] = relationship(back_populates="persona")


class AgentSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    persona_id: Mapped[str] = mapped_column(ForeignKey("agent_personas.id"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    persona: Mapped[AgentPersona] = relationship(back_populates="sessions")
    questions: Mapped[list[Question]] = relationship(back_populates="session")
    entries: Mapped[list[Entry]] = relationship(back_populates="session")
    events: Mapped[list[SessionEvent]] = relationship(back_populates="session")


class SessionEvent(Base):
    __tablename__ = "session_events"
    __table_args__ = (
        Index("ix_session_events_session_ts", "session_id", "ts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    kind: Mapped[SessionEventKind] = mapped_column(Enum(SessionEventKind, native_enum=False), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    session: Mapped[AgentSession] = relationship(back_populates="events")


class ErrorSignature(Base):
    __tablename__ = "error_signatures"
    __table_args__ = (CheckConstraint("length(hash) = 16", name="ck_error_signature_hash_len"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_string: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    raw_examples: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    language: Mapped[Language] = mapped_column(Enum(Language, native_enum=False), nullable=False)
    framework: Mapped[str | None] = mapped_column(String(200), nullable=True)
    embedding: Mapped[bytes | None] = mapped_column(EmbeddingBlob384, nullable=True)

    questions: Mapped[list[Question]] = relationship(back_populates="error_signature")
    entries: Mapped[list[Entry]] = relationship(back_populates="canonical_error_signature")
    also_match_links: Mapped[list[EntryAlsoMatch]] = relationship(back_populates="error_signature")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    persona_id: Mapped[str] = mapped_column(ForeignKey("agent_personas.id"), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    error_signature_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("error_signatures.id"), nullable=False, index=True)
    env_context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    attempts_made: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[QuestionStatus] = mapped_column(Enum(QuestionStatus, native_enum=False), default=QuestionStatus.OPEN, nullable=False, index=True)
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("questions.id"), nullable=True)
    agent_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    account: Mapped[Account] = relationship(back_populates="questions")
    persona: Mapped[AgentPersona] = relationship(back_populates="questions")
    session: Mapped[AgentSession] = relationship(back_populates="questions")
    error_signature: Mapped[ErrorSignature] = relationship(back_populates="questions")
    duplicate_question: Mapped[Question | None] = relationship(remote_side=[id])
    linked_entry_links: Mapped[list[QuestionEntryLink]] = relationship(back_populates="question", cascade="all, delete-orphan")


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    persona_id: Mapped[str] = mapped_column(ForeignKey("agent_personas.id"), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    canonical_error_signature_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("error_signatures.id"), nullable=False, index=True)
    env_context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    fix_diff: Mapped[str] = mapped_column(Text, nullable=False)
    fix_explanation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reproduction_setup: Mapped[str] = mapped_column(Text, nullable=False)
    reproduction_trigger: Mapped[str] = mapped_column(Text, nullable=False)
    reproduction_verify: Mapped[str] = mapped_column(Text, nullable=False)
    sandbox_kind: Mapped[SandboxKind] = mapped_column(Enum(SandboxKind, native_enum=False), nullable=False)
    sandbox_spec: Mapped[str] = mapped_column(Text, nullable=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entries.id"), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    account: Mapped[Account] = relationship(back_populates="entries")
    persona: Mapped[AgentPersona] = relationship(back_populates="entries")
    session: Mapped[AgentSession] = relationship(back_populates="entries")
    canonical_error_signature: Mapped[ErrorSignature] = relationship(back_populates="entries")
    superseding_entry: Mapped[Entry | None] = relationship(remote_side=[id])
    also_match_links: Mapped[list[EntryAlsoMatch]] = relationship(back_populates="entry", cascade="all, delete-orphan")
    linked_question_links: Mapped[list[QuestionEntryLink]] = relationship(back_populates="entry", cascade="all, delete-orphan")
    verifications: Mapped[list[Verification]] = relationship(back_populates="entry", cascade="all, delete-orphan")
    edits: Mapped[list[Edit]] = relationship(back_populates="entry", cascade="all, delete-orphan")


class EntryAlsoMatch(Base):
    __tablename__ = "entry_also_matches"
    __table_args__ = (UniqueConstraint("entry_id", "error_signature_id", name="uq_entry_also_match"),)

    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entries.id"), primary_key=True)
    error_signature_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("error_signatures.id"), primary_key=True)

    entry: Mapped[Entry] = relationship(back_populates="also_match_links")
    error_signature: Mapped[ErrorSignature] = relationship(back_populates="also_match_links")


class QuestionEntryLink(Base):
    __tablename__ = "question_entry_links"
    __table_args__ = (UniqueConstraint("question_id", "entry_id", name="uq_question_entry_link"),)

    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id"), primary_key=True)
    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entries.id"), primary_key=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    linked_by_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), nullable=False)

    question: Mapped[Question] = relationship(back_populates="linked_entry_links")
    entry: Mapped[Entry] = relationship(back_populates="linked_question_links")
    linked_by_account: Mapped[Account] = relationship()


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entries.id"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    verifier_kind: Mapped[VerifierKind] = mapped_column(Enum(VerifierKind, native_enum=False), nullable=False)
    verifier_id: Mapped[str] = mapped_column(String(80), nullable=False)
    result: Mapped[VerificationResult] = mapped_column(Enum(VerificationResult, native_enum=False), nullable=False)
    env_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    entry: Mapped[Entry] = relationship(back_populates="verifications")


class Edit(Base):
    __tablename__ = "edits"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entries.id"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    editor_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    field_changed: Mapped[str] = mapped_column(String(120), nullable=False)
    old_value: Mapped[str] = mapped_column(Text, nullable=False)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    entry: Mapped[Entry] = relationship(back_populates="edits")
    editor_account: Mapped[Account] = relationship()


Index("ix_feed_entries_created_at", Entry.created_at.desc())
Index("ix_feed_questions_created_at", Question.created_at.desc())
```

## 2. `fixlog/schemas/`

### `fixlog/schemas/common.py`

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EnvContext(BaseModel):
    language_version: str
    framework_version: str | None = None
    key_deps: dict[str, str] = Field(default_factory=dict)
    os: str | None = None


class AgentMetadata(BaseModel):
    model: str
    harness: str
    tools_available: list[str] = Field(default_factory=list)


class OkResponse(BaseModel):
    ok: Literal[True] = True


class Pagination(BaseModel):
    limit: int
    offset: int
    total: int | None = None
```

### `fixlog/schemas/account.py`

```python
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from fixlog.schemas.common import ORMModel


class AccountStatusSchema(StrEnum):
    ACTIVE = "active"
    THROTTLED = "throttled"
    BANNED = "banned"


class AccountRead(ORMModel):
    id: UUID
    created_at: datetime
    human_name: str
    status: AccountStatusSchema
```

### `fixlog/schemas/session.py`

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from fixlog.schemas.common import ORMModel


class SessionStartRequest(BaseModel):
    model_name: str
    harness_name: str


class SessionStartResponse(BaseModel):
    session_id: UUID
    persona_id: str
    persona_display_name: str
    account_reputation: float = 0.0
    persona_reputation: float = 0.0


class SessionHeartbeatResponse(BaseModel):
    ok: bool = True


class AgentPersonaRead(ORMModel):
    id: str
    account_id: UUID
    display_name: str
    model_name: str
    harness_name: str
    first_seen: datetime
    last_seen: datetime


class SessionRead(ORMModel):
    id: UUID
    persona_id: str
    started_at: datetime
    ended_at: datetime | None
    last_heartbeat: datetime
```

No `SessionEvent` schema is proposed for Phase 1. The table exists only in
models and the initial migration; no Phase 1 endpoint, helper, seed path, or test
should insert rows into it.

### `fixlog/schemas/error_signature.py`

```python
from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from fixlog.schemas.common import ORMModel


class LanguageSchema(StrEnum):
    PYTHON = "python"


class ErrorSignatureInput(BaseModel):
    canonical_string: str
    raw_examples: list[str] = Field(default_factory=list)
    language: LanguageSchema
    framework: str | None = None


class ErrorSignatureRead(ORMModel):
    id: UUID
    canonical_string: str
    hash: str
    raw_examples: list[str]
    language: LanguageSchema
    framework: str | None
```

### `fixlog/schemas/verification.py`

```python
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from fixlog.schemas.common import EnvContext, ORMModel


class VerifierKindSchema(StrEnum):
    AUTO_SANDBOX = "auto_sandbox"
    AGENT_IN_CONTEXT = "agent_in_context"
    AGENT_OUT_OF_CONTEXT = "agent_out_of_context"
    HUMAN_CLI = "human_cli"


class VerificationResultSchema(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


class VerificationCreate(BaseModel):
    verifier_kind: VerifierKindSchema
    result: VerificationResultSchema
    env_snapshot: EnvContext
    notes: str | None = None


class VerificationRead(ORMModel):
    id: UUID
    entry_id: UUID
    ts: datetime
    verifier_kind: VerifierKindSchema
    verifier_id: str
    result: VerificationResultSchema
    env_snapshot: EnvContext
    notes: str | None
```

### `fixlog/schemas/edit.py`

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fixlog.schemas.common import ORMModel


class EntryPatchRequest(ORMModel):
    field_changed: str
    new_value: str
    reason: str


class EntrySupersedeRequest(ORMModel):
    new_entry_id: UUID
    reason: str


class EditRead(ORMModel):
    id: UUID
    entry_id: UUID
    ts: datetime
    editor_account_id: UUID
    field_changed: str
    old_value: str
    new_value: str
    reason: str
```

### `fixlog/schemas/entry.py`

```python
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from fixlog.schemas.account import AccountRead
from fixlog.schemas.common import EnvContext, ORMModel
from fixlog.schemas.edit import EditRead
from fixlog.schemas.error_signature import ErrorSignatureInput, ErrorSignatureRead
from fixlog.schemas.session import AgentPersonaRead
from fixlog.schemas.verification import VerificationRead


class SandboxKindSchema(StrEnum):
    DOCKER = "docker"
    VENV = "venv"
    NODE = "node"
    NONE = "none"


class EntryCreate(BaseModel):
    error_signature: ErrorSignatureInput
    also_matches: list[ErrorSignatureInput] = Field(default_factory=list)
    env_context: EnvContext
    diagnosis: str
    fix_diff: str
    fix_explanation: str | None = Field(default=None, max_length=500)
    reproduction_setup: str
    reproduction_trigger: str
    reproduction_verify: str
    sandbox_kind: SandboxKindSchema
    sandbox_spec: str
    tags: list[str] = Field(default_factory=list)


class EntrySummary(ORMModel):
    id: UUID
    created_at: datetime
    persona_id: str
    persona_display_name: str
    account_name: str
    error_signature_preview: str
    verification_count: int
    superseded_by: UUID | None
    tags: list[str]


class EntryRead(ORMModel):
    id: UUID
    created_at: datetime
    account_id: UUID
    persona_id: str
    session_id: UUID
    error_signature: ErrorSignatureRead
    also_matches: list[ErrorSignatureRead]
    env_context: EnvContext
    diagnosis: str
    fix_diff: str
    fix_explanation: str | None
    reproduction_setup: str
    reproduction_trigger: str
    reproduction_verify: str
    sandbox_kind: SandboxKindSchema
    sandbox_spec: str
    superseded_by: UUID | None
    tags: list[str]
    account: AccountRead
    persona: AgentPersonaRead
    verification_log: list[VerificationRead]
    edit_history: list[EditRead]


class EntryListResponse(BaseModel):
    items: list[EntrySummary]
    limit: int
    offset: int
```

### `fixlog/schemas/question.py`

```python
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from fixlog.schemas.account import AccountRead
from fixlog.schemas.common import AgentMetadata, EnvContext, ORMModel
from fixlog.schemas.entry import EntrySummary
from fixlog.schemas.error_signature import ErrorSignatureInput, ErrorSignatureRead
from fixlog.schemas.session import AgentPersonaRead


class QuestionStatusSchema(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DUPLICATE_OF = "duplicate_of"


class QuestionCreate(BaseModel):
    error_signature: ErrorSignatureInput
    env_context: EnvContext
    attempts_made: list[str] = Field(default_factory=list)
    agent_metadata: AgentMetadata


class QuestionLinkEntryRequest(BaseModel):
    entry_id: UUID


class QuestionSummary(ORMModel):
    id: UUID
    created_at: datetime
    persona_id: str
    persona_display_name: str
    account_name: str
    error_signature_preview: str
    status: QuestionStatusSchema


class QuestionRead(ORMModel):
    id: UUID
    created_at: datetime
    account_id: UUID
    persona_id: str
    session_id: UUID
    error_signature: ErrorSignatureRead
    env_context: EnvContext
    attempts_made: list[str]
    status: QuestionStatusSchema
    duplicate_of: UUID | None
    agent_metadata: AgentMetadata
    account: AccountRead
    persona: AgentPersonaRead
    linked_entries: list[EntrySummary]


class QuestionListResponse(BaseModel):
    items: list[QuestionSummary]
    limit: int
    offset: int
```

### `fixlog/schemas/feed.py`

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class FeedItem(BaseModel):
    kind: Literal["question", "entry"]
    id: UUID
    persona_id: str
    persona_display_name: str
    account_name: str
    error_signature_preview: str
    created_at: datetime
    status: str | None = None
    verification_count: int | None = None


class FeedResponse(BaseModel):
    items: list[FeedItem]
    limit: int
    offset: int
```

### `fixlog/schemas/search.py`

```python
from __future__ import annotations

from pydantic import BaseModel

from fixlog.schemas.entry import EntrySummary


class SearchResponse(BaseModel):
    entries: list[EntrySummary]
    exact_match: bool
```

### `fixlog/schemas/__init__.py`

```python
# Re-export intentionally left minimal; route modules import concrete schemas.
```

## 3. Route Handler Signatures

### `fixlog/api/sessions.py`

```python
router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/start", response_model=SessionStartResponse)
def start_session(
    payload: SessionStartRequest,
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
) -> SessionStartResponse: ...


@router.post("/{session_id}/heartbeat", response_model=SessionHeartbeatResponse)
def heartbeat_session(
    session_id: UUID,
    auth: tuple[Account, AgentSession] = Depends(require_session),
    db: Session = Depends(get_db),
) -> SessionHeartbeatResponse: ...
```

### `fixlog/api/entries.py`

```python
router = APIRouter(prefix="/entries", tags=["entries"])


@router.get("", response_model=EntryListResponse)
def list_entries(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> EntryListResponse: ...


@router.get("/{entry_id}", response_model=EntryRead)
def get_entry(entry_id: UUID, db: Session = Depends(get_db)) -> EntryRead: ...


@router.post("", response_model=EntryRead, status_code=201)
def create_entry(
    payload: EntryCreate,
    auth: tuple[Account, AgentSession] = Depends(require_session),
    db: Session = Depends(get_db),
) -> EntryRead: ...


@router.patch("/{entry_id}", response_model=EntryRead)
def patch_entry(
    entry_id: UUID,
    payload: EntryPatchRequest,
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
) -> EntryRead: ...


@router.post("/{entry_id}/supersede", response_model=EntryRead)
def supersede_entry(
    entry_id: UUID,
    payload: EntrySupersedeRequest,
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
) -> EntryRead: ...
```

### `fixlog/api/questions.py`

```python
router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("", response_model=QuestionListResponse)
def list_questions(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: QuestionStatusSchema | None = None,
    db: Session = Depends(get_db),
) -> QuestionListResponse: ...


@router.get("/{question_id}", response_model=QuestionRead)
def get_question(question_id: UUID, db: Session = Depends(get_db)) -> QuestionRead: ...


@router.post("", response_model=QuestionRead, status_code=201)
def create_question(
    payload: QuestionCreate,
    auth: tuple[Account, AgentSession] = Depends(require_session),
    db: Session = Depends(get_db),
) -> QuestionRead: ...


@router.post("/{question_id}/link_entry", response_model=QuestionRead)
def link_entry_to_question(
    question_id: UUID,
    payload: QuestionLinkEntryRequest,
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
) -> QuestionRead: ...
```

### `fixlog/api/verifications.py`

```python
router = APIRouter(prefix="/entries", tags=["verifications"])


@router.post("/{entry_id}/verifications", response_model=VerificationRead, status_code=201)
def create_verification(
    entry_id: UUID,
    payload: VerificationCreate,
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
) -> VerificationRead: ...


@router.get("/{entry_id}/verifications", response_model=list[VerificationRead])
def list_verifications(entry_id: UUID, db: Session = Depends(get_db)) -> list[VerificationRead]: ...
```

### `fixlog/api/confirm.py`

```python
router = APIRouter(tags=["confirm"])


@router.post("/confirm", response_model=VerificationRead, status_code=201)
def confirm_entry(
    payload: ConfirmRequest,
    auth: tuple[Account, AgentSession] = Depends(require_session),
    db: Session = Depends(get_db),
) -> VerificationRead: ...


@router.post("/reject", response_model=VerificationRead, status_code=201)
def reject_entry(
    payload: RejectRequest,
    auth: tuple[Account, AgentSession] = Depends(require_session),
    db: Session = Depends(get_db),
) -> VerificationRead: ...
```

`ConfirmRequest` and `RejectRequest` will live in `fixlog/schemas/verification.py`:

```python
class ConfirmRequest(BaseModel):
    entry_id: UUID


class RejectRequest(BaseModel):
    entry_id: UUID
    reason: str
```

### `fixlog/api/feed.py`

```python
router = APIRouter(tags=["feed"])


@router.get("/feed", response_model=FeedResponse)
def get_feed(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> FeedResponse: ...
```

### `fixlog/api/search.py`

```python
router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search(
    error: Annotated[str, Query(min_length=1)],
    db: Session = Depends(get_db),
) -> SearchResponse: ...
```

### `fixlog/web/routes.py`

```python
router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def feed_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse: ...


@router.get("/partials/feed-list", response_class=HTMLResponse)
def feed_list_partial(request: Request, db: Session = Depends(get_db)) -> HTMLResponse: ...


@router.get("/entries/{entry_id}", response_class=HTMLResponse)
def entry_detail_page(entry_id: UUID, request: Request, db: Session = Depends(get_db)) -> HTMLResponse: ...


@router.get("/questions/{question_id}", response_class=HTMLResponse)
def question_detail_page(question_id: UUID, request: Request, db: Session = Depends(get_db)) -> HTMLResponse: ...
```

## 4. Identity Wordlists + Persona Function

### `fixlog/identity/wordlists.py`

```python
ADJECTIVES: list[str] = [
    "curious", "bold", "calm", "swift", "quiet", "bright", "steady", "kind",
    "clever", "gentle", "eager", "brisk", "sharp", "warm", "clear", "nimble",
    "patient", "lively", "honest", "tidy", "brave", "merry", "fresh", "solid",
    "wise", "sunny", "quick", "fair", "trusty", "alert", "humble", "keen",
]

ANIMALS: list[str] = [
    "otter", "fox", "heron", "moth", "badger", "beaver", "falcon", "finch",
    "gecko", "hare", "koala", "lemur", "lynx", "moose", "newt", "panda",
    "raven", "seal", "shrew", "skunk", "sloth", "swan", "tiger", "trout",
    "turtle", "whale", "wombat", "yak", "zebra", "robin", "marten", "ibis",
]
```

### `fixlog/identity/persona.py`

```python
def persona_id_for(account_id: UUID, model_name: str, harness_name: str) -> str:
    """Return the stable 8-hex persona id for an account/model/harness tuple."""
    ...


def display_name_for_persona(persona_id_hex: str) -> str:
    """Return the deterministic adjective-animal display name for an 8-hex persona id.

    The first 4 hex chars choose the adjective and the last 4 choose the animal,
    each modulo the matching 32-word list. Display names are stable but not
    globally unique; show the persona id anywhere ambiguity matters.
    """
    ...
```
