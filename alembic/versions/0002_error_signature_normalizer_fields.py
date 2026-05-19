from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_error_signature_normalizer_fields"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


ERROR_KIND_ENUM = sa.Enum(
    "traceback",
    "pytest",
    "pip",
    "generic",
    name="errorsignatureerrorkind",
    native_enum=False,
)


def upgrade() -> None:
    with op.batch_alter_table("error_signatures") as batch_op:
        batch_op.add_column(sa.Column("exception_type", sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column("exception_message", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("last_frame_module", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("last_frame_function", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("traceback_shape", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("error_kind", ERROR_KIND_ENUM, nullable=True))
        batch_op.add_column(
            sa.Column(
                "was_chained",
                sa.Boolean(),
                nullable=True,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("error_signatures") as batch_op:
        batch_op.drop_column("was_chained")
        batch_op.drop_column("error_kind")
        batch_op.drop_column("traceback_shape")
        batch_op.drop_column("last_frame_function")
        batch_op.drop_column("last_frame_module")
        batch_op.drop_column("exception_message")
        batch_op.drop_column("exception_type")
