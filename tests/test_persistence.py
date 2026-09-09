from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models.all_models import Activity
from app.services.activity_service import upsert_activity


def test_activity_upsert_is_idempotent() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    data = {
        "activityId": 42,
        "startTimeLocal": "2026-01-02T10:00:00",
        "activityName": "Test",
        "activityType": {"typeKey": "running"},
        "duration": 1200,
        "distance": 3000,
    }
    with Session(engine) as db:
        upsert_activity(db, data)
        data["activityName"] = "Actualizada"
        upsert_activity(db, data)
        db.commit()
        rows = list(db.scalars(select(Activity)))
    assert len(rows) == 1
    assert rows[0].name == "Actualizada"
    assert rows[0].start_time == datetime(2026, 1, 2, 10, 0)
