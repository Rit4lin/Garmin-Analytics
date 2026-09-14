from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.all_models import DailyStat, Hrv, Sleep, TrainingMetric, Weight


def first(data: dict[str, Any], *names: str) -> Any:
    for name in names:
        if data.get(name) is not None:
            return data[name]
    return None


def mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def primary_device(values: Any) -> dict[str, Any]:
    """Return the primary device payload from Garmin's device-id keyed objects."""
    devices = [item for item in mapping(values).values() if isinstance(item, dict)]
    return next(
        (item for item in devices if item.get("primaryTrainingDevice")),
        devices[0] if devices else {},
    )


def current_training_values(status: dict[str, Any]) -> dict[str, Any]:
    """Normalize both legacy and current Garmin training-status response shapes."""
    vo2 = mapping(mapping(status.get("mostRecentVO2Max")).get("generic"))
    training_status = primary_device(
        mapping(status.get("mostRecentTrainingStatus")).get("latestTrainingStatusData")
    )
    acute = mapping(training_status.get("acuteTrainingLoadDTO"))

    vo2max = first(status, "vo2Max")
    training_load = first(status, "trainingLoad")
    acute_load = first(status, "acuteTrainingLoad")
    status_value = first(status, "trainingStatus")
    weekly_load = first(training_status, "weeklyTrainingLoad")

    return {
        "vo2max": vo2max
        if vo2max is not None
        else first(vo2, "vo2MaxValue", "vo2MaxPreciseValue"),
        "training_load": training_load
        if training_load is not None
        else weekly_load if weekly_load is not None else first(acute, "dailyTrainingLoadAcute"),
        "acute_load": acute_load
        if acute_load is not None
        else first(acute, "dailyTrainingLoadAcute"),
        "training_status": status_value
        if status_value is not None
        else first(training_status, "trainingStatusFeedbackPhrase", "trainingStatus"),
    }


def epoch_datetime(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000 if value > 100_000_000_000 else value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def body_battery_extremes(
    payload: list[dict[str, Any]] | None,
) -> tuple[float | None, float | None]:
    """Extrae valores 0-100 de las series devueltas por get_body_battery()."""
    values: list[float] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            if len(value) == 2 and isinstance(value[1], (int, float)) and 0 <= value[1] <= 100:
                values.append(float(value[1]))
            else:
                for child in value:
                    visit(child)

    visit(payload or [])
    return (max(values), min(values)) if values else (None, None)


def normalize_sleep_score(summary: dict[str, Any]) -> float | None:
    """Normaliza los formatos conocidos del sleep score de Garmin a un número."""
    sleep_scores = first(summary, "sleepScores")
    candidate: Any = first(summary, "overallScore")

    if isinstance(sleep_scores, dict):
        overall = first(sleep_scores, "overall", "overallScore")
        if isinstance(overall, dict):
            candidate = overall.get("value")
        elif overall is not None:
            candidate = overall
    elif sleep_scores is not None:
        candidate = sleep_scores

    if isinstance(candidate, bool) or not isinstance(candidate, (int, float)):
        return None
    return float(candidate)


def upsert_daily(
    db: Session,
    day: date,
    stats: dict[str, Any],
    heart: dict[str, Any] | None = None,
    stress: dict[str, Any] | None = None,
    spo2: dict[str, Any] | None = None,
    respiration: dict[str, Any] | None = None,
    body_battery: list[dict[str, Any]] | None = None,
) -> None:
    row = db.get(DailyStat, day) or DailyStat(stat_date=day, raw_json={})
    row.steps = first(stats, "totalSteps", "steps")
    row.distance_meters = first(stats, "totalDistanceMeters", "totalDistance")
    row.active_calories = first(stats, "activeKilocalories", "totalKilocalories")
    row.floors = first(stats, "floorsAscended")
    row.intensity_minutes = first(stats, "moderateIntensityMinutes")
    row.resting_hr = first(stats, "restingHeartRate") or first(heart or {}, "restingHeartRate")
    row.avg_hr = first(heart or {}, "averageHeartRateInBeatsPerMinute", "averageHeartRate")
    row.stress_avg = first(stress or {}, "avgStressLevel", "averageStressLevel")
    row.spo2_avg = first(spo2 or {}, "averageSpO2", "avgSpO2")
    row.respiration_avg = first(
        respiration or {}, "avgWakingRespirationValue", "avgRespirationValue"
    )
    high, low = body_battery_extremes(body_battery)
    stats_high = first(stats, "bodyBatteryHighestValue")
    stats_low = first(stats, "bodyBatteryLowestValue")
    row.body_battery_high = stats_high if stats_high is not None else high
    row.body_battery_low = stats_low if stats_low is not None else low
    row.raw_json = {
        "stats": stats,
        "heart": heart or {},
        "stress": stress or {},
        "spo2": spo2 or {},
        "respiration": respiration or {},
        "body_battery": body_battery or [],
    }
    db.add(row)


def upsert_sleep(db: Session, day: date, data: dict[str, Any]) -> None:
    summary = data.get("dailySleepDTO") or data
    row = db.get(Sleep, day) or Sleep(sleep_date=day, raw_json={})
    row.start_time = epoch_datetime(
        first(summary, "sleepStartTimestampGMT", "sleepStartTimestampLocal")
    )
    row.end_time = epoch_datetime(first(summary, "sleepEndTimestampGMT", "sleepEndTimestampLocal"))
    row.duration_seconds = first(summary, "sleepTimeSeconds", "sleepDurationInSeconds")
    row.score = normalize_sleep_score(summary)
    row.deep_seconds = first(summary, "deepSleepSeconds")
    row.light_seconds = first(summary, "lightSleepSeconds")
    row.rem_seconds = first(summary, "remSleepSeconds")
    row.awake_seconds = first(summary, "awakeSleepSeconds")
    row.raw_json = data
    db.add(row)


def upsert_hrv(db: Session, day: date, data: dict[str, Any]) -> None:
    summary = data.get("hrvSummary") or data
    row = db.get(Hrv, day) or Hrv(hrv_date=day, raw_json={})
    row.overnight_avg = first(summary, "lastNightAvg", "weeklyAvg", "avgHrv")
    row.status = first(summary, "status")
    row.baseline_low = first(summary, "baselineLow")
    row.baseline_high = first(summary, "baselineHigh")
    row.raw_json = data
    db.add(row)


def upsert_training(
    db: Session,
    day: date,
    status: dict[str, Any],
    readiness: list[dict[str, Any]],
    endurance: dict[str, Any] | None = None,
    hill: dict[str, Any] | None = None,
) -> None:
    row = db.get(TrainingMetric, day) or TrainingMetric(metric_date=day, raw_json={})
    values = current_training_values(status)
    row.vo2max = values["vo2max"]
    row.training_load = values["training_load"]
    row.acute_load = values["acute_load"]
    row.training_status = values["training_status"]
    row.recovery_time_hours = first(status, "recoveryTime", "recoveryTimeInHours")
    if readiness:
        row.readiness = first(readiness[0], "score", "trainingReadinessScore")
    row.endurance_score = first(endurance or {}, "enduranceScore")
    row.hill_score = first(hill or {}, "hillScore")
    row.raw_json = {
        "status": status,
        "readiness": readiness,
        "endurance": endurance or {},
        "hill": hill or {},
    }
    db.add(row)


def upsert_weights(db: Session, payload: dict[str, Any]) -> int:
    rows = payload.get("dateWeightList") or payload.get("weightSamples") or []
    count = 0
    for item in rows:
        recorded_at = epoch_datetime(first(item, "calendarDate", "timestampGMT", "timestamp"))
        if not recorded_at:
            continue
        row = db.get(Weight, recorded_at) or Weight(recorded_at=recorded_at, raw_json={})
        value = first(item, "weight")
        row.weight_kg = value / 1000 if isinstance(value, (int, float)) and value > 500 else value
        row.bmi = first(item, "bmi")
        row.body_fat = first(item, "bodyFat")
        row.muscle_mass = first(item, "muscleMass")
        row.body_water = first(item, "bodyWater")
        row.raw_json = item
        db.add(row)
        count += 1
    return count
