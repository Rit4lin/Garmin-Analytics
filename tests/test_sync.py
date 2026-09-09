from datetime import date, datetime, timedelta

from garminconnect import GarminConnectTooManyRequestsError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base
from app.models.all_models import Activity, SyncState
from app.services.sync_service import SyncService


class FakeGarmin:
    def __init__(self, fail_on: date | None = None) -> None:
        self.details_calls = 0
        self.activity_ranges: list[tuple[str, str]] = []
        self.fail_on = fail_on

    def connect(self) -> None:
        return None

    def activities(self, start: str, end: str):
        self.activity_ranges.append((start, end))
        return [
            {
                "activityId": 1,
                "startTimeLocal": "2026-01-01T10:00:00",
                "activityName": "Run",
                "activityType": {"typeKey": "running"},
            }
        ]

    def activity_details(self, _activity_id: str):
        self.details_calls += 1
        return {"details": []}

    def activity_splits(self, _activity_id: str):
        return {"lapDTOs": []}

    def stats(self, day: str):
        if self.fail_on == date.fromisoformat(day):
            raise GarminConnectTooManyRequestsError("429")
        return {"totalSteps": 100, "bodyBatteryHighestValue": 80, "bodyBatteryLowestValue": 25}

    def heart_rates(self, _day: str):
        return {"restingHeartRate": 50}

    def stress(self, _day: str):
        return {"avgStressLevel": 32}

    def spo2(self, _day: str):
        return {"averageSpO2": 97}

    def respiration(self, _day: str):
        return {"avgWakingRespirationValue": 14}

    def body_battery(self, _start: str, _end: str):
        return [{"values": [[1, 25], [2, 80]]}]

    def sleep(self, _day: str):
        return {}

    def hrv(self, _day: str):
        return {}

    def training_status(self, _day: str):
        return {"vo2Max": 48, "trainingLoad": 321, "acuteTrainingLoad": 250, "recoveryTime": 12}

    def training_readiness(self, _day: str):
        return [{"score": 76}]

    def endurance_score(self, _day: str):
        return {"enduranceScore": 6000}

    def hill_score(self, _day: str):
        return {"hillScore": 52}

    def weigh_ins(self, _start: str, _end: str):
        return {"dateWeightList": []}


def setup_service(monkeypatch, days: int = 3):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("app.services.sync_service.SessionLocal", factory)
    return SyncService(
        Settings(initial_sync_days=days, sync_recent_days=2, garmin_request_delay_seconds=0)
    ), factory


def run(service: SyncService) -> None:
    assert service._lock.acquire(blocking=False)
    service._run()


def test_empty_database_starts_backfill_and_completed_restart_is_recent(monkeypatch) -> None:
    service, factory = setup_service(monkeypatch)
    client = FakeGarmin()
    monkeypatch.setattr("app.services.sync_service.GarminClient", lambda _settings: client)
    run(service)
    with factory() as db:
        state = db.get(SyncState, "garmin")
        assert state.backfill_status == "completed"
        assert state.backfill_cursor_date == date.today()
    assert client.activity_ranges[0][0] == (date.today() - timedelta(days=2)).isoformat()
    run(service)
    assert client.activity_ranges[1][0] == (date.today() - timedelta(days=1)).isoformat()


def test_429_keeps_backfill_cursor_and_resume(monkeypatch) -> None:
    service, factory = setup_service(monkeypatch)
    start = date.today() - timedelta(days=2)
    limited = FakeGarmin(fail_on=start + timedelta(days=1))
    monkeypatch.setattr("app.services.sync_service.GarminClient", lambda _settings: limited)
    run(service)
    with factory() as db:
        state = db.get(SyncState, "garmin")
        assert state.backfill_status == "incomplete"
        assert state.backfill_cursor_date == start
        assert state.retry_count == 1
        state.next_retry_at = datetime.now() - timedelta(seconds=1)
        db.commit()
    resumed = FakeGarmin()
    monkeypatch.setattr("app.services.sync_service.GarminClient", lambda _settings: resumed)
    run(service)
    assert resumed.activity_ranges[0][0] == (start + timedelta(days=1)).isoformat()


def test_incremental_sync_does_not_redownload_activity_details(monkeypatch) -> None:
    service, factory = setup_service(monkeypatch)
    client = FakeGarmin()
    start = datetime(2026, 1, 1).date()
    service._sync_activities(client, start, start)
    service._sync_activities(client, start, start)
    with factory() as db:
        assert len(list(db.scalars(select(Activity)))) == 1
    assert client.details_calls == 1


def test_429_cooldown_cannot_be_skipped(monkeypatch) -> None:
    service, factory = setup_service(monkeypatch)
    service._finish_error("429")
    assert service.request_sync() is False
    with factory() as db:
        assert db.get(SyncState, "garmin").next_retry_at > datetime.now()
