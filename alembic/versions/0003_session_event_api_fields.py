from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_session_event_api_fields"
down_revision = "0002_error_signature_normalizer_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("source_tool", sa.String(length=80), nullable=True))
        batch.add_column(
            sa.Column("source_tool_session_id", sa.String(length=200), nullable=True)
        )
        batch.create_index("ix_sessions_source_tool", ["source_tool"], unique=False)
        batch.create_index(
            "ix_sessions_source_tool_session_id",
            ["source_tool_session_id"],
            unique=False,
        )

    with op.batch_alter_table("session_events") as batch:
        batch.create_index("ix_session_events_kind", ["kind"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("session_events") as batch:
        batch.drop_index("ix_session_events_kind")

    with op.batch_alter_table("sessions") as batch:
        batch.drop_index("ix_sessions_source_tool_session_id")
        batch.drop_index("ix_sessions_source_tool")
        batch.drop_column("source_tool_session_id")
        batch.drop_column("source_tool")
