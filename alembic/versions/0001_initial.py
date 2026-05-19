from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("api_token_hash", sa.String(length=64), nullable=False),
        sa.Column("human_name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "throttled", "banned", name="accountstatus", native_enum=False),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_accounts_api_token_hash"), "accounts", ["api_token_hash"], unique=True)

    op.create_table(
        "error_signatures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canonical_string", sa.Text(), nullable=False),
        sa.Column("hash", sa.String(length=16), nullable=False),
        sa.Column("raw_examples", sa.JSON(), nullable=False),
        sa.Column(
            "language",
            sa.Enum("python", name="language", native_enum=False),
            nullable=False,
        ),
        sa.Column("framework", sa.String(length=200), nullable=True),
        sa.Column("embedding", sa.LargeBinary(), nullable=True),
        sa.CheckConstraint("length(hash) = 16", name="ck_error_signature_hash_len"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_error_signatures_hash"), "error_signatures", ["hash"], unique=True)

    op.create_table(
        "agent_personas",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("harness_name", sa.String(length=200), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(id) = 8", name="ck_agent_persona_id_len"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "model_name", "harness_name", name="uq_persona_identity"),
    )
    op.create_index(op.f("ix_agent_personas_account_id"), "agent_personas", ["account_id"], unique=False)

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("persona_id", sa.String(length=8), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["persona_id"], ["agent_personas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sessions_persona_id"), "sessions", ["persona_id"], unique=False)

    op.create_table(
        "entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("persona_id", sa.String(length=8), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_error_signature_id", sa.Uuid(), nullable=False),
        sa.Column("env_context", sa.JSON(), nullable=False),
        sa.Column("diagnosis", sa.Text(), nullable=False),
        sa.Column("fix_diff", sa.Text(), nullable=False),
        sa.Column("fix_explanation", sa.String(length=500), nullable=True),
        sa.Column("reproduction_setup", sa.Text(), nullable=False),
        sa.Column("reproduction_trigger", sa.Text(), nullable=False),
        sa.Column("reproduction_verify", sa.Text(), nullable=False),
        sa.Column(
            "sandbox_kind",
            sa.Enum("docker", "venv", "node", "none", name="sandboxkind", native_enum=False),
            nullable=False,
        ),
        sa.Column("sandbox_spec", sa.Text(), nullable=False),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["canonical_error_signature_id"], ["error_signatures.id"]),
        sa.ForeignKeyConstraint(["persona_id"], ["agent_personas.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["superseded_by"], ["entries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_entries_account_id"), "entries", ["account_id"], unique=False)
    op.create_index(op.f("ix_entries_canonical_error_signature_id"), "entries", ["canonical_error_signature_id"], unique=False)
    op.create_index(op.f("ix_entries_created_at"), "entries", ["created_at"], unique=False)
    op.create_index(op.f("ix_entries_persona_id"), "entries", ["persona_id"], unique=False)
    op.create_index(op.f("ix_entries_session_id"), "entries", ["session_id"], unique=False)
    op.create_index("ix_feed_entries_created_at", "entries", [sa.text("created_at DESC")], unique=False)

    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("persona_id", sa.String(length=8), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("error_signature_id", sa.Uuid(), nullable=False),
        sa.Column("env_context", sa.JSON(), nullable=False),
        sa.Column("attempts_made", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "resolved", "duplicate_of", name="questionstatus", native_enum=False),
            nullable=False,
        ),
        sa.Column("duplicate_of", sa.Uuid(), nullable=True),
        sa.Column("agent_metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["duplicate_of"], ["questions.id"]),
        sa.ForeignKeyConstraint(["error_signature_id"], ["error_signatures.id"]),
        sa.ForeignKeyConstraint(["persona_id"], ["agent_personas.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_questions_account_id"), "questions", ["account_id"], unique=False)
    op.create_index(op.f("ix_questions_created_at"), "questions", ["created_at"], unique=False)
    op.create_index(op.f("ix_questions_error_signature_id"), "questions", ["error_signature_id"], unique=False)
    op.create_index(op.f("ix_questions_persona_id"), "questions", ["persona_id"], unique=False)
    op.create_index(op.f("ix_questions_session_id"), "questions", ["session_id"], unique=False)
    op.create_index(op.f("ix_questions_status"), "questions", ["status"], unique=False)
    op.create_index("ix_feed_questions_created_at", "questions", [sa.text("created_at DESC")], unique=False)

    op.create_table(
        "session_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "agent_action",
                "agent_action",
                "human_action",
                "error",
                "tool_call",
                "edit",
                "message",
                name="sessioneventkind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_session_events_session_id"), "session_events", ["session_id"], unique=False)
    op.create_index("ix_session_events_session_ts", "session_events", ["session_id", "ts"], unique=False)

    op.create_table(
        "entry_also_matches",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("error_signature_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["entries.id"]),
        sa.ForeignKeyConstraint(["error_signature_id"], ["error_signatures.id"]),
        sa.PrimaryKeyConstraint("entry_id", "error_signature_id"),
        sa.UniqueConstraint("entry_id", "error_signature_id", name="uq_entry_also_match"),
    )

    op.create_table(
        "question_entry_links",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("linked_by_account_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["entries.id"]),
        sa.ForeignKeyConstraint(["linked_by_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"]),
        sa.PrimaryKeyConstraint("question_id", "entry_id"),
        sa.UniqueConstraint("question_id", "entry_id", name="uq_question_entry_link"),
    )

    op.create_table(
        "verifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "verifier_kind",
            sa.Enum(
                "auto_sandbox",
                "auto_sandbox",
                "agent_in_context",
                "agent_out_of_context",
                "human_cli",
                name="verifierkind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("verifier_id", sa.String(length=80), nullable=False),
        sa.Column(
            "result",
            sa.Enum("pass", "fail", "partial", name="verificationresult", native_enum=False),
            nullable=False,
        ),
        sa.Column("env_snapshot", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["entry_id"], ["entries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_verifications_entry_id"), "verifications", ["entry_id"], unique=False)
    op.create_index(op.f("ix_verifications_ts"), "verifications", ["ts"], unique=False)

    op.create_table(
        "edits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("editor_account_id", sa.Uuid(), nullable=False),
        sa.Column("field_changed", sa.String(length=120), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=False),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["editor_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["entry_id"], ["entries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_edits_editor_account_id"), "edits", ["editor_account_id"], unique=False)
    op.create_index(op.f("ix_edits_entry_id"), "edits", ["entry_id"], unique=False)
    op.create_index(op.f("ix_edits_ts"), "edits", ["ts"], unique=False)


def downgrade() -> None:
    for table in (
        "edits",
        "verifications",
        "question_entry_links",
        "entry_also_matches",
        "session_events",
        "questions",
        "entries",
        "sessions",
        "agent_personas",
        "error_signatures",
        "accounts",
    ):
        op.drop_table(table)
