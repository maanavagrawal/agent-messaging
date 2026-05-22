from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_device_tokens"
down_revision = "0003_session_event_api_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_device_tokens_account_id"),
        "device_tokens",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_device_tokens_token_hash"),
        "device_tokens",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_device_tokens_token_hash"), table_name="device_tokens")
    op.drop_index(op.f("ix_device_tokens_account_id"), table_name="device_tokens")
    op.drop_table("device_tokens")
