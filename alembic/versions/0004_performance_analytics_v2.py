"""Add Garmin Analytics v2 performance history and personal records."""

import sqlalchemy as sa

from alembic import op

revision = "0004_performance_analytics_v2"
down_revision = "0003_backfill_nested_training_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "performance_metrics",
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("race_5k_seconds", sa.Float(), nullable=True),
        sa.Column("race_10k_seconds", sa.Float(), nullable=True),
        sa.Column("race_half_seconds", sa.Float(), nullable=True),
        sa.Column("race_marathon_seconds", sa.Float(), nullable=True),
        sa.Column("lactate_hr", sa.Float(), nullable=True),
        sa.Column("lactate_speed_mps", sa.Float(), nullable=True),
        sa.Column("running_tolerance", sa.Float(), nullable=True),
        sa.Column("fitness_age", sa.Float(), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("metric_date"),
    )
    op.create_table(
        "personal_records",
        sa.Column("record_id", sa.String(length=160), nullable=False),
        sa.Column("record_type", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("record_date", sa.Date(), nullable=True),
        sa.Column("activity_id", sa.String(length=64), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("record_id"),
    )
    op.create_index(
        op.f("ix_personal_records_record_type"),
        "personal_records",
        ["record_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_personal_records_record_type"),
        table_name="personal_records",
    )
    op.drop_table("personal_records")
    op.drop_table("performance_metrics")
