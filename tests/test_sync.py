from datetime import datetime

from garminconnect import GarminConnectTooManyRequestsError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base
from app.models.all_models import Activity
from app.services.sync_service import SyncService


class FakeGarmin:
    def __init__(self) -> None:
        self.details_calls = 0

    def activities(self, _start: str, _end: str):
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


def test_incremental_sync_does_not_redownload_activity_details(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("app.services.sync_service.SessionLocal", factory)
    service = SyncService(Settings(garmin_request_delay_seconds=0))
    client = FakeGarmin()
    start = datetime(2026, 1, 1).date()
    service._sync_activities(client, start, start)  # type: ignore[arg-type]
    service._sync_activities(client, start, start)  # type: ignore[arg-type]
    with factory() as db:
        assert len(list(db.scalars(select(Activity)))) == 1
    assert client.details_calls == 1


def test_429_is_recorded_without_retry_storm(monkeypatch) -> None:
    service = SyncService()
    recorded: list[tuple[str, int | None]] = []
    monkeypatch.setattr(
        service,
        "_finish_error",
        lambda message, retry_minutes=None: recorded.append((message, retry_minutes)),
    )

    class LimitedClient:
        def connect(self):
            raise GarminConnectTooManyRequestsError("429")

    monkeypatch.setattr("app.services.sync_service.GarminClient", lambda _settings: LimitedClient())
    assert service._lock.acquire(blocking=False)
    service._run(initial=False)
    assert recorded and recorded[0][1] == 60
