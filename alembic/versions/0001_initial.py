"""Esquema inicial de Garmin Analytics."""

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_state",
        sa.Column("name", sa.String(40), primary_key=True),
        sa.Column("status", sa.String(30)),
        sa.Column("progress_current", sa.Integer()),
        sa.Column("progress_total", sa.Integer()),
        sa.Column("last_sync_at", sa.DateTime()),
        sa.Column("last_date_downloaded", sa.Date()),
        sa.Column("error_message", sa.Text()),
        sa.Column("next_retry_at", sa.DateTime()),
    )
    op.create_table(
        "activities",
        sa.Column("activity_id", sa.String(64), primary_key=True),
        sa.Column("start_time", sa.DateTime(), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("activity_type", sa.String(80)),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("moving_duration_seconds", sa.Float()),
        sa.Column("distance_meters", sa.Float()),
        sa.Column("calories", sa.Float()),
        sa.Column("avg_hr", sa.Float()),
        sa.Column("max_hr", sa.Float()),
        sa.Column("elevation_gain", sa.Float()),
        sa.Column("elevation_loss", sa.Float()),
        sa.Column("avg_cadence", sa.Float()),
        sa.Column("avg_power", sa.Float()),
        sa.Column("aerobic_te", sa.Float()),
        sa.Column("anaerobic_te", sa.Float()),
        sa.Column("training_load", sa.Float()),
        sa.Column("vo2max", sa.Float()),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.Column("details_json", sa.JSON()),
        sa.Column("splits_json", sa.JSON()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_activities_start_time", "activities", ["start_time"])
    op.create_index("ix_activities_activity_type", "activities", ["activity_type"])
    op.create_index("ix_activities_date_type", "activities", ["start_time", "activity_type"])
    op.create_table(
        "daily_stats",
        sa.Column("stat_date", sa.Date(), primary_key=True),
        sa.Column("steps", sa.Integer()),
        sa.Column("distance_meters", sa.Float()),
        sa.Column("active_calories", sa.Float()),
        sa.Column("floors", sa.Integer()),
        sa.Column("intensity_minutes", sa.Integer()),
        sa.Column("resting_hr", sa.Float()),
        sa.Column("avg_hr", sa.Float()),
        sa.Column("stress_avg", sa.Float()),
        sa.Column("body_battery_high", sa.Float()),
        sa.Column("body_battery_low", sa.Float()),
        sa.Column("respiration_avg", sa.Float()),
        sa.Column("spo2_avg", sa.Float()),
        sa.Column("raw_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "sleep",
        sa.Column("sleep_date", sa.Date(), primary_key=True),
        sa.Column("start_time", sa.DateTime()),
        sa.Column("end_time", sa.DateTime()),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("score", sa.Float()),
        sa.Column("deep_seconds", sa.Float()),
        sa.Column("light_seconds", sa.Float()),
        sa.Column("rem_seconds", sa.Float()),
        sa.Column("awake_seconds", sa.Float()),
        sa.Column("raw_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "hrv",
        sa.Column("hrv_date", sa.Date(), primary_key=True),
        sa.Column("overnight_avg", sa.Float()),
        sa.Column("status", sa.String(80)),
        sa.Column("baseline_low", sa.Float()),
        sa.Column("baseline_high", sa.Float()),
        sa.Column("raw_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "weights",
        sa.Column("recorded_at", sa.DateTime(), primary_key=True),
        sa.Column("weight_kg", sa.Float()),
        sa.Column("bmi", sa.Float()),
        sa.Column("body_fat", sa.Float()),
        sa.Column("muscle_mass", sa.Float()),
        sa.Column("body_water", sa.Float()),
        sa.Column("raw_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_weights_date", "weights", ["recorded_at"])
    op.create_table(
        "training_metrics",
        sa.Column("metric_date", sa.Date(), primary_key=True),
        sa.Column("vo2max", sa.Float()),
        sa.Column("training_load", sa.Float()),
        sa.Column("acute_load", sa.Float()),
        sa.Column("training_status", sa.String(80)),
        sa.Column("readiness", sa.Float()),
        sa.Column("recovery_time_hours", sa.Float()),
        sa.Column("endurance_score", sa.Float()),
        sa.Column("hill_score", sa.Float()),
        sa.Column("raw_json", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "training_metrics",
        "weights",
        "hrv",
        "sleep",
        "daily_stats",
        "activities",
        "sync_state",
    ):
        op.drop_table(table)
