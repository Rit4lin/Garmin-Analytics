from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.all_models import Activity, PerformanceMetric
from app.services.performance_service import (
    activity_efficiency,
    aerobic_decoupling,
    build_performance_report,
    load_balance,
    normalize_performance_payloads,
    trend,
)


def test_trend_compares_recent_window_with_personal_baseline() -> None:
    start = date(2026, 1, 1)
    values = []
    for offset in range(56):
        value = 50.0 if offset < 42 else 55.0
        values.append((start + timedelta(days=offset), value))
    result = trend(values)
    assert result["status"] == "mejorando"
    assert result["change_pct"] == 10.0
    assert result["confidence"] == "alta"


def test_lower_is_better_inverts_direction() -> None:
    start = date(2026, 1, 1)
    values = []
    for offset in range(56):
        value = 60.0 if offset < 42 else 54.0
        values.append((start + timedelta(days=offset), value))
    result = trend(values, lower_is_better=True)
    assert result["status"] == "mejorando"
    assert result["change_pct"] == 10.0


def test_activity_efficiency_uses_speed_relative_to_heart_rate() -> None:
    activity = Activity(
        activity_id="1",
        start_time=datetime(2026, 1, 1, 9),
        distance_meters=5000,
        duration_seconds=1500,
        moving_duration_seconds=1500,
        avg_hr=150,
        raw_json={},
    )
    assert round(activity_efficiency(activity) or 0, 3) == 22.222


def test_aerobic_decoupling_detects_second_half_efficiency_loss() -> None:
    splits = {
        "lapDTOs": [
            {"distance": 1000, "duration": 300, "averageHR": 150},
            {"distance": 1000, "duration": 300, "averageHR": 150},
            {"distance": 1000, "duration": 310, "averageHR": 155},
            {"distance": 1000, "duration": 310, "averageHR": 155},
        ]
    }
    result = aerobic_decoupling(splits)
    assert result is not None
    assert result > 5


def test_load_balance_flags_high_acute_load() -> None:
    end = datetime(2026, 3, 1, 8)
    activities = []
    for offset in range(42):
        load = 30 if offset < 35 else 120
        activities.append(
            Activity(
                activity_id=str(offset),
                start_time=end - timedelta(days=41 - offset),
                training_load=load,
                raw_json={},
            )
        )
    result = load_balance(activities)
    assert result["ratio"] is not None
    assert result["acute"] > result["chronic"]


def test_normalize_optional_garmin_performance_payloads() -> None:
    values = normalize_performance_payloads(
        date(2026, 9, 14),
        race={
            "time5K": 1500,
            "time10K": 3200,
            "timeHalfMarathon": 7000,
            "timeMarathon": 15000,
        },
        lactate={
            "speed_and_heart_rate": {
                "speed": 3.5,
                "heartRate": 171,
            }
        },
        tolerance=[
            {
                "calendarDate": "2026-09-14",
                "runningTolerance": 48.5,
            }
        ],
        fitness_age={"fitnessAge": 29},
    )
    assert values["race_5k_seconds"] == 1500
    assert values["lactate_hr"] == 171
    assert values["lactate_speed_mps"] == 3.5
    assert values["running_tolerance"] == 48.5
    assert values["fitness_age"] == 29


def test_performance_report_exposes_fitness_age_trend() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    today = date.today()
    with Session(engine) as db:
        for offset in range(56):
            db.add(
                PerformanceMetric(
                    metric_date=today - timedelta(days=55 - offset),
                    fitness_age=31 if offset < 42 else 29,
                    raw_json={},
                )
            )
        db.commit()
        report = build_performance_report(db, 60)
    fitness_age = report["fitness"]["fitness_age"]
    assert fitness_age["status"] == "mejorando"
    assert fitness_age["current"] == 29
