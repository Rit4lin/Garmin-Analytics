from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.all_models import Activity


def _value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if data.get(key) is not None:
            return data[key]
    return None


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError("La actividad no contiene una fecha válida")


def upsert_activity(
    db: Session,
    data: dict[str, Any],
    details: dict[str, Any] | None = None,
    splits: dict[str, Any] | None = None,
) -> Activity:
    activity_id = str(_value(data, "activityId", "activity_id"))
    if not activity_id or activity_id == "None":
        raise ValueError("Actividad sin activityId")
    activity = db.get(Activity, activity_id) or Activity(
        activity_id=activity_id,
        start_time=_datetime(_value(data, "startTimeLocal", "startTimeGMT")),
        raw_json={},
    )
    activity.start_time = _datetime(_value(data, "startTimeLocal", "startTimeGMT"))
    activity.name = _value(data, "activityName")
    activity_type = data.get("activityType") or {}
    activity.activity_type = (
        activity_type.get("typeKey") if isinstance(activity_type, dict) else str(activity_type)
    )
    activity.duration_seconds = _value(data, "duration")
    activity.moving_duration_seconds = _value(data, "movingDuration")
    activity.distance_meters = _value(data, "distance")
    activity.calories = _value(data, "calories")
    activity.avg_hr = _value(data, "averageHR", "avgHR")
    activity.max_hr = _value(data, "maxHR")
    activity.elevation_gain = _value(data, "elevationGain")
    activity.elevation_loss = _value(data, "elevationLoss")
    activity.avg_cadence = _value(data, "averageRunningCadenceInStepsPerMinute", "averageCadence")
    activity.avg_power = _value(data, "avgPower")
    activity.aerobic_te = _value(data, "aerobicTrainingEffect")
    activity.anaerobic_te = _value(data, "anaerobicTrainingEffect")
    activity.training_load = _value(data, "activityTrainingLoad")
    activity.vo2max = _value(data, "vO2MaxValue", "vo2MaxValue")
    activity.raw_json = data
    if details is not None:
        activity.details_json = details
    if splits is not None:
        activity.splits_json = splits
    db.add(activity)
    return activity
