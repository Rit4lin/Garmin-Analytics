"""Estado persistente para el backfill reanudable."""

import sqlalchemy as sa

from alembic import op

revision = "0002_sync_backfill_state"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sync_state") as batch:
        batch.add_column(sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(
            sa.Column(
                "backfill_status",
                sa.String(30),
                nullable=False,
                server_default="not_started",
            )
        )
        batch.add_column(sa.Column("backfill_start_date", sa.Date()))
        batch.add_column(sa.Column("backfill_cursor_date", sa.Date()))
        batch.add_column(sa.Column("backfill_started_at", sa.DateTime()))
        batch.add_column(sa.Column("backfill_completed_at", sa.DateTime()))


def downgrade() -> None:
    with op.batch_alter_table("sync_state") as batch:
        batch.drop_column("backfill_completed_at")
        batch.drop_column("backfill_started_at")
        batch.drop_column("backfill_cursor_date")
        batch.drop_column("backfill_start_date")
        batch.drop_column("backfill_status")
        batch.drop_column("retry_count")
