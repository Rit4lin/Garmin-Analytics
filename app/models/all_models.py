from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_date_type", "start_time", "activity_type"),)

    activity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    activity_type: Mapped[str | None] = mapped_column(String(80), index=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    moving_duration_seconds: Mapped[float | None] = mapped_column(Float)
    distance_meters: Mapped[float | None] = mapped_column(Float)
    calories: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    max_hr: Mapped[float | None] = mapped_column(Float)
    elevation_gain: Mapped[float | None] = mapped_column(Float)
    elevation_loss: Mapped[float | None] = mapped_column(Float)
    avg_cadence: Mapped[float | None] = mapped_column(Float)
    avg_power: Mapped[float | None] = mapped_column(Float)
    aerobic_te: Mapped[float | None] = mapped_column(Float)
    anaerobic_te: Mapped[float | None] = mapped_column(Float)
    training_load: Mapped[float | None] = mapped_column(Float)
    vo2max: Mapped[float | None] = mapped_column(Float)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    splits_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class DailyStat(Base):
    __tablename__ = "daily_stats"

    stat_date: Mapped[date] = mapped_column(Date, primary_key=True)
    steps: Mapped[int | None] = mapped_column(Integer)
    distance_meters: Mapped[float | None] = mapped_column(Float)
    active_calories: Mapped[float | None] = mapped_column(Float)
    floors: Mapped[int | None] = mapped_column(Integer)
    intensity_minutes: Mapped[int | None] = mapped_column(Integer)
    resting_hr: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    stress_avg: Mapped[float | None] = mapped_column(Float)
    body_battery_high: Mapped[float | None] = mapped_column(Float)
    body_battery_low: Mapped[float | None] = mapped_column(Float)
    respiration_avg: Mapped[float | None] = mapped_column(Float)
    spo2_avg: Mapped[float | None] = mapped_column(Float)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class Sleep(Base):
    __tablename__ = "sleep"

    sleep_date: Mapped[date] = mapped_column(Date, primary_key=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)
    deep_seconds: Mapped[float | None] = mapped_column(Float)
    light_seconds: Mapped[float | None] = mapped_column(Float)
    rem_seconds: Mapped[float | None] = mapped_column(Float)
    awake_seconds: Mapped[float | None] = mapped_column(Float)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class Hrv(Base):
    __tablename__ = "hrv"
    hrv_date: Mapped[date] = mapped_column(Date, primary_key=True)
    overnight_avg: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str | None] = mapped_column(String(80))
    baseline_low: Mapped[float | None] = mapped_column(Float)
    baseline_high: Mapped[float | None] = mapped_column(Float)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class Weight(Base):
    __tablename__ = "weights"
    __table_args__ = (Index("ix_weights_date", "recorded_at"),)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    bmi: Mapped[float | None] = mapped_column(Float)
    body_fat: Mapped[float | None] = mapped_column(Float)
    muscle_mass: Mapped[float | None] = mapped_column(Float)
    body_water: Mapped[float | None] = mapped_column(Float)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class TrainingMetric(Base):
    __tablename__ = "training_metrics"
    metric_date: Mapped[date] = mapped_column(Date, primary_key=True)
    vo2max: Mapped[float | None] = mapped_column(Float)
    training_load: Mapped[float | None] = mapped_column(Float)
    acute_load: Mapped[float | None] = mapped_column(Float)
    training_status: Mapped[str | None] = mapped_column(String(80))
    readiness: Mapped[float | None] = mapped_column(Float)
    recovery_time_hours: Mapped[float | None] = mapped_column(Float)
    endurance_score: Mapped[float | None] = mapped_column(Float)
    hill_score: Mapped[float | None] = mapped_column(Float)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"

    metric_date: Mapped[date] = mapped_column(Date, primary_key=True)
    race_5k_seconds: Mapped[float | None] = mapped_column(Float)
    race_10k_seconds: Mapped[float | None] = mapped_column(Float)
    race_half_seconds: Mapped[float | None] = mapped_column(Float)
    race_marathon_seconds: Mapped[float | None] = mapped_column(Float)
    lactate_hr: Mapped[float | None] = mapped_column(Float)
    lactate_speed_mps: Mapped[float | None] = mapped_column(Float)
    running_tolerance: Mapped[float | None] = mapped_column(Float)
    fitness_age: Mapped[float | None] = mapped_column(Float)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class PersonalRecord(Base):
    __tablename__ = "personal_records"

    record_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    record_type: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(40))
    record_date: Mapped[date | None] = mapped_column(Date)
    activity_id: Mapped[str | None] = mapped_column(String(64))
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class SyncState(Base):
    __tablename__ = "sync_state"
    name: Mapped[str] = mapped_column(String(40), primary_key=True, default="garmin")
    status: Mapped[str] = mapped_column(String(30), default="idle")
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_date_downloaded: Mapped[date | None] = mapped_column(Date)
    error_message: Mapped[str | None] = mapped_column(Text)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    backfill_status: Mapped[str] = mapped_column(String(30), default="not_started")
    backfill_start_date: Mapped[date | None] = mapped_column(Date)
    backfill_cursor_date: Mapped[date | None] = mapped_column(Date)
    backfill_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    backfill_completed_at: Mapped[datetime | None] = mapped_column(DateTime)
