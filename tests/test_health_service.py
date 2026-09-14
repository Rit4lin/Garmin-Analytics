from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.all_models import DailyStat, Sleep, TrainingMetric, Weight
from app.services.health_service import upsert_daily, upsert_sleep, upsert_training, upsert_weights


def test_daily_optional_metrics_and_training_are_persisted() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        today = datetime(2026, 1, 3).date()
        upsert_daily(
            db,
            today,
            {"bodyBatteryHighestValue": 90, "bodyBatteryLowestValue": 20},
            stress={"avgStressLevel": 31},
            spo2={"averageSpO2": 98},
            respiration={"avgWakingRespirationValue": 14},
            body_battery=[{"series": [[1, 20], [2, 90]]}],
        )
        upsert_training(
            db,
            today,
            {"vo2Max": 50, "trainingLoad": 400, "acuteTrainingLoad": 300, "recoveryTime": 9},
            [{"score": 80}],
            {"enduranceScore": 7000},
            {"hillScore": 55},
        )
        db.commit()
        daily = db.get(DailyStat, today)
        training = db.get(TrainingMetric, today)
    assert (daily.stress_avg, daily.spo2_avg, daily.respiration_avg) == (31, 98, 14)
    assert (daily.body_battery_high, daily.body_battery_low) == (90, 20)
    assert (training.vo2max, training.acute_load, training.readiness) == (50, 300, 80)
    assert (training.recovery_time_hours, training.endurance_score, training.hill_score) == (
        9,
        7000,
        55,
    )


def test_training_status_accepts_current_nested_garmin_response() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    day = datetime(2026, 1, 4).date()
    payload = {
        "mostRecentVO2Max": {"generic": {"vo2MaxValue": 48.0}},
        "mostRecentTrainingStatus": {
            "latestTrainingStatusData": {
                "secondary-device": {
                    "primaryTrainingDevice": False,
                    "acuteTrainingLoadDTO": {"dailyTrainingLoadAcute": 99},
                },
                "primary-device": {
                    "primaryTrainingDevice": True,
                    "trainingStatusFeedbackPhrase": "RECOVERY_1",
                    "acuteTrainingLoadDTO": {"dailyTrainingLoadAcute": 191},
                },
            }
        },
    }
    with Session(engine) as db:
        upsert_training(db, day, payload, [])
        db.commit()
        row = db.get(TrainingMetric, day)
    assert row is not None
    assert (row.vo2max, row.training_load, row.acute_load) == (48.0, 191, 191)
    assert row.training_status == "RECOVERY_1"


def test_sleep_score_accepts_nested_overall_value() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    day = datetime(2026, 1, 7).date()
    payload = {
        "dailySleepDTO": {
            "sleepScores": {
                "overall": {"value": 82, "qualifierKey": "GOOD"},
            }
        }
    }
    with Session(engine) as db:
        upsert_sleep(db, day, payload)
        db.commit()
        row = db.get(Sleep, day)
    assert row is not None
    assert row.score == 82


def test_sleep_score_keeps_legacy_numeric_formats_and_rejects_non_numeric() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        day_one = datetime(2026, 1, 8).date()
        day_two = datetime(2026, 1, 9).date()
        day_three = datetime(2026, 1, 10).date()
        upsert_sleep(db, day_one, {"dailySleepDTO": {"sleepScores": {"overall": 77}}})
        upsert_sleep(db, day_two, {"dailySleepDTO": {"overallScore": 74}})
        upsert_sleep(
            db,
            day_three,
            {"dailySleepDTO": {"sleepScores": {"overall": {"value": "unknown"}}}},
        )
        db.commit()
        assert db.get(Sleep, day_one).score == 77
        assert db.get(Sleep, day_two).score == 74
        assert db.get(Sleep, day_three).score is None


def test_weight_accepts_iso_calendar_date() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        assert (
            upsert_weights(
                db, {"dateWeightList": [{"calendarDate": "2026-01-03", "weight": 72500}]}
            )
            == 1
        )
        db.commit()
        row = db.query(Weight).one()
    assert row.recorded_at == datetime(2026, 1, 3)
    assert row.weight_kg == 72.5
