from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean, median
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.all_models import (
    Activity,
    DailyStat,
    Hrv,
    PerformanceMetric,
    PersonalRecord,
    Sleep,
    TrainingMetric,
    Weight,
)

RUN_TYPES = {
    "running",
    "trail_running",
    "treadmill_running",
    "track_running",
    "virtual_running",
}
STRENGTH_TYPES = {"strength_training", "cardio", "hiit", "crossfit"}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _safe_mean(values: Iterable[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return mean(clean) if clean else None


def _pct_change(
    current: float | None,
    baseline: float | None,
    *,
    lower_is_better: bool = False,
) -> float | None:
    if current is None or baseline in (None, 0):
        return None
    raw = ((current - baseline) / abs(baseline)) * 100
    return -raw if lower_is_better else raw


def _trend_label(change: float | None, threshold: float = 1.5) -> str:
    if change is None:
        return "sin_datos"
    if change > threshold:
        return "mejorando"
    if change < -threshold:
        return "empeorando"
    return "estable"


def _confidence(samples: int) -> str:
    if samples >= 12:
        return "alta"
    if samples >= 6:
        return "media"
    return "baja"


def trend(
    values: list[tuple[date, float | None]],
    *,
    recent_days: int = 14,
    baseline_days: int = 42,
    lower_is_better: bool = False,
) -> dict[str, Any]:
    if not values:
        return {
            "current": None,
            "baseline": None,
            "change_pct": None,
            "status": "sin_datos",
            "samples": 0,
            "confidence": "baja",
        }
    available_days = [day for day, value in values if value is not None]
    last_day = max(available_days) if available_days else values[-1][0]
    recent_start = last_day - timedelta(days=recent_days - 1)
    baseline_start = recent_start - timedelta(days=baseline_days)
    recent = [
        float(value)
        for day, value in values
        if value is not None and day >= recent_start
    ]
    baseline = [
        float(value)
        for day, value in values
        if value is not None and baseline_start <= day < recent_start
    ]
    if not baseline:
        older = [
            float(value)
            for day, value in values
            if value is not None and day < recent_start
        ]
        baseline = older[-baseline_days:]
    current_value = mean(recent) if recent else None
    baseline_value = mean(baseline) if baseline else None
    change = _pct_change(
        current_value,
        baseline_value,
        lower_is_better=lower_is_better,
    )
    samples = len(recent) + len(baseline)
    return {
        "current": round(current_value, 2) if current_value is not None else None,
        "baseline": round(baseline_value, 2) if baseline_value is not None else None,
        "change_pct": round(change, 2) if change is not None else None,
        "status": _trend_label(change),
        "samples": samples,
        "confidence": _confidence(samples),
    }


def activity_efficiency(activity: Activity) -> float | None:
    if not activity.avg_hr or activity.avg_hr <= 0 or not activity.distance_meters:
        return None
    duration = activity.moving_duration_seconds or activity.duration_seconds
    if not duration or duration <= 0:
        return None
    speed_mps = activity.distance_meters / duration
    return speed_mps / activity.avg_hr * 1000


def _extract_split_rows(value: Any, out: list[dict[str, float]]) -> None:
    if isinstance(value, dict):
        distance = _number(value.get("distance") or value.get("distanceMeters"))
        duration = _number(
            value.get("movingDuration")
            or value.get("duration")
            or value.get("elapsedDuration")
            or value.get("durationSeconds")
        )
        hr = _number(
            value.get("averageHR")
            or value.get("avgHR")
            or value.get("averageHeartRate")
            or value.get("averageHeartRateInBeatsPerMinute")
        )
        if distance and duration and hr and distance > 0 and duration > 0 and hr > 0:
            out.append({"distance": distance, "duration": duration, "hr": hr})
        for child in value.values():
            _extract_split_rows(child, out)
    elif isinstance(value, list):
        for child in value:
            _extract_split_rows(child, out)


def aerobic_decoupling(splits: Any) -> float | None:
    rows: list[dict[str, float]] = []
    _extract_split_rows(splits, rows)
    if len(rows) < 2:
        return None
    total_distance = sum(row["distance"] for row in rows)
    if total_distance <= 0:
        return None
    midpoint = total_distance / 2
    first: list[dict[str, float]] = []
    second: list[dict[str, float]] = []
    covered = 0.0
    for row in rows:
        (first if covered < midpoint else second).append(row)
        covered += row["distance"]
    if not first or not second:
        return None

    def efficiency(group: list[dict[str, float]]) -> float:
        distance = sum(row["distance"] for row in group)
        duration = sum(row["duration"] for row in group)
        weighted_hr = sum(
            row["hr"] * row["duration"] for row in group
        ) / duration
        return (distance / duration) / weighted_hr

    first_eff = efficiency(first)
    second_eff = efficiency(second)
    if first_eff == 0:
        return None
    return round(((first_eff - second_eff) / first_eff) * 100, 2)


def _ewma_load(loads: dict[date, float], end: date, days: int) -> float:
    alpha = 2 / (days + 1)
    value = 0.0
    start = end - timedelta(days=max(days * 3, 60))
    day = start
    while day <= end:
        value = alpha * loads.get(day, 0.0) + (1 - alpha) * value
        day += timedelta(days=1)
    return value


def load_balance(activities: list[Activity]) -> dict[str, Any]:
    empty = {
        "acute": 0.0,
        "chronic": 0.0,
        "ratio": None,
        "form": 0.0,
        "fatigue_index": None,
        "status": "sin_datos",
    }
    if not activities:
        return empty
    loads: dict[date, float] = defaultdict(float)
    for activity in activities:
        if activity.training_load is not None:
            loads[activity.start_time.date()] += float(activity.training_load)
    if not loads:
        return empty
    end = max(loads)
    acute = _ewma_load(loads, end, 7)
    chronic = _ewma_load(loads, end, 42)
    ratio = acute / chronic if chronic > 0 else None
    form = chronic - acute
    if ratio is None:
        status = "sin_datos"
    elif ratio > 1.5:
        status = "carga_muy_alta"
    elif ratio > 1.25:
        status = "carga_alta"
    elif ratio < 0.7:
        status = "descarga"
    else:
        status = "equilibrada"
    fatigue = (
        max(0.0, min(100.0, 50 + (ratio - 1) * 60))
        if ratio is not None
        else None
    )
    return {
        "acute": round(acute, 1),
        "chronic": round(chronic, 1),
        "ratio": round(ratio, 2) if ratio is not None else None,
        "form": round(form, 1),
        "fatigue_index": round(fatigue) if fatigue is not None else None,
        "status": status,
    }


def recovery_summary(
    stats: list[DailyStat],
    hrv_rows: list[Hrv],
    sleep_rows: list[Sleep],
    training_rows: list[TrainingMetric],
) -> dict[str, Any]:
    components = {
        "hrv": trend([(x.hrv_date, x.overnight_avg) for x in hrv_rows]),
        "resting_hr": trend(
            [(x.stat_date, x.resting_hr) for x in stats],
            lower_is_better=True,
        ),
        "sleep": trend(
            [
                (
                    x.sleep_date,
                    x.duration_seconds / 3600 if x.duration_seconds else None,
                )
                for x in sleep_rows
            ]
        ),
        "stress": trend(
            [(x.stat_date, x.stress_avg) for x in stats],
            lower_is_better=True,
        ),
        "body_battery": trend(
            [(x.stat_date, x.body_battery_high) for x in stats]
        ),
        "readiness": trend(
            [(x.metric_date, x.readiness) for x in training_rows]
        ),
    }
    weights = {
        "hrv": 0.24,
        "resting_hr": 0.18,
        "sleep": 0.18,
        "stress": 0.12,
        "body_battery": 0.10,
        "readiness": 0.18,
    }
    weighted_delta = 0.0
    used_weight = 0.0
    for name, item in components.items():
        change = item["change_pct"]
        if change is not None:
            weighted_delta += max(-25.0, min(25.0, float(change))) * weights[name]
            used_weight += weights[name]
    score = 50.0
    if used_weight:
        score += (weighted_delta / used_weight) * 2
    score = max(0, min(100, score))
    status = "buena" if score >= 65 else "comprometida" if score < 40 else "normal"
    return {"score": round(score), "status": status, "components": components}


def similar_activity_comparison(
    activity: Activity,
    candidates: list[Activity],
) -> dict[str, Any] | None:
    if not activity.distance_meters or not activity.avg_hr:
        return None
    comparable = []
    for candidate in candidates:
        if (
            candidate.activity_id == activity.activity_id
            or candidate.activity_type != activity.activity_type
            or not candidate.distance_meters
            or not candidate.avg_hr
        ):
            continue
        ratio = candidate.distance_meters / activity.distance_meters
        if 0.75 <= ratio <= 1.25:
            comparable.append(candidate)
    comparable = sorted(comparable, key=lambda row: row.start_time)[-12:]
    if not comparable:
        return None
    paces = [
        (row.moving_duration_seconds or row.duration_seconds)
        / (row.distance_meters / 1000)
        for row in comparable
        if (row.moving_duration_seconds or row.duration_seconds)
        and row.distance_meters
    ]
    efficiencies = [
        value
        for row in comparable
        if (value := activity_efficiency(row)) is not None
    ]
    if not paces or not efficiencies:
        return None
    duration = activity.moving_duration_seconds or activity.duration_seconds
    current_pace = duration / (activity.distance_meters / 1000) if duration else None
    pace_change = _pct_change(current_pace, median(paces), lower_is_better=True)
    hr_change = _pct_change(
        float(activity.avg_hr),
        median(float(row.avg_hr) for row in comparable if row.avg_hr),
        lower_is_better=True,
    )
    eff_change = _pct_change(activity_efficiency(activity), median(efficiencies))
    signals = [x for x in (pace_change, hr_change, eff_change) if x is not None]
    overall = mean(signals) if signals else None
    return {
        "samples": len(comparable),
        "pace_change_pct": round(pace_change, 2) if pace_change is not None else None,
        "hr_change_pct": round(hr_change, 2) if hr_change is not None else None,
        "efficiency_change_pct": (
            round(eff_change, 2) if eff_change is not None else None
        ),
        "status": _trend_label(overall),
    }


def discipline_summary(activities: list[Activity]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Activity]] = defaultdict(list)
    for activity in activities:
        key = activity.activity_type or "other"
        if key in RUN_TYPES:
            group = "running"
        elif key in STRENGTH_TYPES:
            group = "strength_cardio"
        else:
            group = key
        grouped[group].append(activity)
    result = []
    for name, rows in grouped.items():
        rows.sort(key=lambda item: item.start_time)
        efficiency_rows = [
            (row.start_time.date(), activity_efficiency(row))
            for row in rows
            if activity_efficiency(row) is not None
        ]
        load_rows = [
            (row.start_time.date(), row.training_load)
            for row in rows
            if row.training_load is not None
        ]
        aerobic_rows = [
            (row.start_time.date(), row.aerobic_te)
            for row in rows
            if row.aerobic_te is not None
        ]
        result.append(
            {
                "discipline": name,
                "sessions": len(rows),
                "hours": round(
                    sum(row.duration_seconds or 0 for row in rows) / 3600,
                    1,
                ),
                "distance_km": round(
                    sum(row.distance_meters or 0 for row in rows) / 1000,
                    1,
                ),
                "avg_hr": round(_safe_mean([row.avg_hr for row in rows]) or 0, 1),
                "efficiency": trend(efficiency_rows) if efficiency_rows else None,
                "training_load": trend(load_rows) if load_rows else None,
                "aerobic_te": trend(aerobic_rows) if aerobic_rows else None,
            }
        )
    return sorted(result, key=lambda item: item["sessions"], reverse=True)


def _local_running_records(activities: list[Activity]) -> list[dict[str, Any]]:
    runs = [
        row
        for row in activities
        if row.activity_type in RUN_TYPES
        and row.distance_meters
        and (row.moving_duration_seconds or row.duration_seconds)
    ]
    records = []
    for target_m, label in ((1000, "1 km"), (5000, "5 km"), (10000, "10 km")):
        candidates = [
            row
            for row in runs
            if row.distance_meters and row.distance_meters >= target_m * 0.95
        ]
        if not candidates:
            continue
        best = min(
            candidates,
            key=lambda row: (
                (row.moving_duration_seconds or row.duration_seconds)
                / row.distance_meters
            ),
        )
        duration = best.moving_duration_seconds or best.duration_seconds
        estimate = duration * (target_m / best.distance_meters)
        records.append(
            {
                "type": label,
                "value_seconds": round(estimate),
                "date": best.start_time.date().isoformat(),
                "activity_id": best.activity_id,
                "source": "local_estimate",
            }
        )
    return records


def build_performance_report(db: Session, days: int = 180) -> dict[str, Any]:
    start = date.today() - timedelta(days=max(days, 60) - 1)
    dt_start = datetime.combine(start, datetime.min.time())
    activities = list(
        db.scalars(
            select(Activity)
            .where(Activity.start_time >= dt_start)
            .order_by(Activity.start_time)
        )
    )
    stats = list(
        db.scalars(
            select(DailyStat)
            .where(DailyStat.stat_date >= start)
            .order_by(DailyStat.stat_date)
        )
    )
    hrv_rows = list(
        db.scalars(select(Hrv).where(Hrv.hrv_date >= start).order_by(Hrv.hrv_date))
    )
    sleep_rows = list(
        db.scalars(
            select(Sleep).where(Sleep.sleep_date >= start).order_by(Sleep.sleep_date)
        )
    )
    training_rows = list(
        db.scalars(
            select(TrainingMetric)
            .where(TrainingMetric.metric_date >= start)
            .order_by(TrainingMetric.metric_date)
        )
    )
    perf_rows = list(
        db.scalars(
            select(PerformanceMetric)
            .where(PerformanceMetric.metric_date >= start)
            .order_by(PerformanceMetric.metric_date)
        )
    )
    weight_rows = list(
        db.scalars(
            select(Weight)
            .where(Weight.recorded_at >= dt_start)
            .order_by(Weight.recorded_at)
        )
    )
    efficiency_t = trend(
        [
            (row.start_time.date(), activity_efficiency(row))
            for row in activities
            if row.activity_type in RUN_TYPES
        ]
    )
    vo2_t = trend([(x.metric_date, x.vo2max) for x in training_rows])
    endurance_t = trend([(x.metric_date, x.endurance_score) for x in training_rows])
    hill_t = trend([(x.metric_date, x.hill_score) for x in training_rows])
    lactate_t = trend([(x.metric_date, x.lactate_speed_mps) for x in perf_rows])
    tolerance_t = trend([(x.metric_date, x.running_tolerance) for x in perf_rows])
    race_5k_t = trend(
        [(x.metric_date, x.race_5k_seconds) for x in perf_rows],
        lower_is_better=True,
    )
    weight_t = trend([(x.recorded_at.date(), x.weight_kg) for x in weight_rows])
    recovery = recovery_summary(stats, hrv_rows, sleep_rows, training_rows)
    load = load_balance(activities)
    signals = [
        item["change_pct"]
        for item in (efficiency_t, vo2_t, endurance_t, lactate_t, race_5k_t)
        if item["change_pct"] is not None
    ]
    fitness_change = mean(signals) if signals else None
    state = _trend_label(fitness_change)
    headline = {
        "mejorando": "Tu rendimiento está mejorando",
        "empeorando": "Tu rendimiento muestra una tendencia a peor",
        "estable": "Tu rendimiento está estable",
    }.get(state, "Aún no hay datos suficientes para establecer una tendencia")
    alerts: list[dict[str, str]] = []
    for metric, label in (
        (recovery["components"]["hrv"], "HRV"),
        (recovery["components"]["resting_hr"], "FC en reposo"),
        (recovery["components"]["sleep"], "Sueño"),
    ):
        if metric["change_pct"] is not None and metric["change_pct"] < -8:
            alerts.append(
                {
                    "level": "warning",
                    "message": (
                        f"{label}: {metric['change_pct']:+.1f}% "
                        "frente a tu línea base."
                    ),
                }
            )
    if load["ratio"] is not None and load["ratio"] > 1.5:
        alerts.append(
            {
                "level": "warning",
                "message": (
                    f"Carga aguda elevada: ratio {load['ratio']:.2f} "
                    "respecto a tu carga crónica."
                ),
            }
        )
    if efficiency_t["change_pct"] is not None and efficiency_t["change_pct"] > 3:
        alerts.append(
            {
                "level": "positive",
                "message": (
                    f"Eficiencia aeróbica: +{efficiency_t['change_pct']:.1f}% "
                    "frente a tu línea base."
                ),
            }
        )
    if vo2_t["status"] == "estable" and load["ratio"] is not None:
        if load["ratio"] > 1.15:
            alerts.append(
                {
                    "level": "info",
                    "message": (
                        "El VO₂max está plano mientras la carga reciente "
                        "ha aumentado."
                    ),
                }
            )
    insights = [headline + "."]
    if efficiency_t["change_pct"] is not None:
        insights.append(
            "Tu eficiencia aeróbica está "
            f"{efficiency_t['change_pct']:+.1f}% frente a la línea base."
        )
    insights.append(
        f"Recuperación actual: {recovery['score']}/100 ({recovery['status']})."
    )
    if load["ratio"] is not None:
        insights.append(
            f"Balance de carga: {load['status']} "
            f"(aguda/crónica {load['ratio']:.2f})."
        )
    latest = perf_rows[-1] if perf_rows else None
    garmin_records = [
        {
            "type": row.record_type,
            "value": row.value,
            "unit": row.unit,
            "date": row.record_date.isoformat() if row.record_date else None,
            "activity_id": row.activity_id,
            "source": "garmin",
        }
        for row in db.scalars(select(PersonalRecord).order_by(PersonalRecord.record_type))
    ]
    return {
        "status": {
            "headline": headline,
            "trend": state,
            "change_pct": round(fitness_change, 2) if fitness_change is not None else None,
            "confidence": _confidence(len(signals) * 3),
        },
        "fitness": {
            "aerobic_efficiency": efficiency_t,
            "vo2max": vo2_t,
            "endurance": endurance_t,
            "hill": hill_t,
            "lactate_speed": lactate_t,
            "running_tolerance": tolerance_t,
            "race_5k": race_5k_t,
            "weight": weight_t,
        },
        "recovery": recovery,
        "load": load,
        "disciplines": discipline_summary(activities),
        "alerts": alerts,
        "insights": insights,
        "predictions": {
            "5k_seconds": latest.race_5k_seconds if latest else None,
            "10k_seconds": latest.race_10k_seconds if latest else None,
            "half_seconds": latest.race_half_seconds if latest else None,
            "marathon_seconds": latest.race_marathon_seconds if latest else None,
            "history": [
                {
                    "date": row.metric_date.isoformat(),
                    "5k_seconds": row.race_5k_seconds,
                    "10k_seconds": row.race_10k_seconds,
                    "half_seconds": row.race_half_seconds,
                    "marathon_seconds": row.race_marathon_seconds,
                }
                for row in perf_rows
                if any(
                    (
                        row.race_5k_seconds,
                        row.race_10k_seconds,
                        row.race_half_seconds,
                        row.race_marathon_seconds,
                    )
                )
            ],
        },
        "threshold": {
            "hr": latest.lactate_hr if latest else None,
            "speed_mps": latest.lactate_speed_mps if latest else None,
            "pace_seconds_km": (
                1000 / latest.lactate_speed_mps
                if latest and latest.lactate_speed_mps
                else None
            ),
        },
        "records": garmin_records or _local_running_records(activities),
    }


def performance_timeseries(db: Session, days: int = 365) -> dict[str, Any]:
    start = date.today() - timedelta(days=days - 1)
    rows = list(
        db.scalars(
            select(PerformanceMetric)
            .where(PerformanceMetric.metric_date >= start)
            .order_by(PerformanceMetric.metric_date)
        )
    )
    return {
        "race_predictions": [
            {
                "date": row.metric_date.isoformat(),
                "5k": row.race_5k_seconds,
                "10k": row.race_10k_seconds,
                "half": row.race_half_seconds,
                "marathon": row.race_marathon_seconds,
            }
            for row in rows
        ],
        "lactate": [
            {
                "date": row.metric_date.isoformat(),
                "hr": row.lactate_hr,
                "speed_mps": row.lactate_speed_mps,
            }
            for row in rows
        ],
        "running_tolerance": [
            {"date": row.metric_date.isoformat(), "value": row.running_tolerance}
            for row in rows
        ],
    }


def _first_recursive(value: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        for key in keys:
            if value.get(key) is not None:
                return value[key]
        for child in value.values():
            found = _first_recursive(child, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _first_recursive(child, keys)
            if found is not None:
                return found
    return None


def normalize_performance_payloads(
    day: date,
    race: Any = None,
    lactate: Any = None,
    tolerance: Any = None,
    fitness_age: Any = None,
) -> dict[str, Any]:
    race_payload = race[-1] if isinstance(race, list) and race else race
    race_payload = race_payload if isinstance(race_payload, dict) else {}
    return {
        "metric_date": day,
        "race_5k_seconds": _number(
            _first_recursive(race_payload, ("time5K", "racePrediction5k"))
        ),
        "race_10k_seconds": _number(
            _first_recursive(race_payload, ("time10K", "racePrediction10k"))
        ),
        "race_half_seconds": _number(
            _first_recursive(
                race_payload,
                ("timeHalfMarathon", "racePredictionHalf"),
            )
        ),
        "race_marathon_seconds": _number(
            _first_recursive(race_payload, ("timeMarathon", "racePredictionMarathon"))
        ),
        "lactate_hr": _number(
            _first_recursive(
                lactate,
                ("heartRate", "hearRate", "lactateThresholdHeartRate"),
            )
        ),
        "lactate_speed_mps": _number(
            _first_recursive(lactate, ("speed", "lactateThresholdSpeed"))
        ),
        "running_tolerance": _number(
            _first_recursive(
                tolerance,
                ("runningTolerance", "tolerance", "toleranceScore", "score"),
            )
        ),
        "fitness_age": _number(
            _first_recursive(fitness_age, ("fitnessAge", "fitnessAgeYears"))
        ),
        "raw_json": {
            key: value
            for key, value in {
                "race_predictions": race,
                "lactate_threshold": lactate,
                "running_tolerance": tolerance,
                "fitness_age": fitness_age,
            }.items()
            if value is not None
        },
    }


def upsert_performance_metric(
    db: Session,
    day: date,
    race: Any = None,
    lactate: Any = None,
    tolerance: Any = None,
    fitness_age: Any = None,
) -> PerformanceMetric:
    values = normalize_performance_payloads(
        day,
        race,
        lactate,
        tolerance,
        fitness_age,
    )
    row = db.get(PerformanceMetric, day) or PerformanceMetric(
        metric_date=day,
        raw_json={},
    )
    for field in (
        "race_5k_seconds",
        "race_10k_seconds",
        "race_half_seconds",
        "race_marathon_seconds",
        "lactate_hr",
        "lactate_speed_mps",
        "running_tolerance",
        "fitness_age",
    ):
        if values[field] is not None:
            setattr(row, field, values[field])
    current_raw = row.raw_json if isinstance(row.raw_json, dict) else {}
    row.raw_json = {**current_raw, **values["raw_json"]}
    db.add(row)
    return row


def _as_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
    return None


def _dated_items(payload: Any) -> dict[date, Any]:
    result: dict[date, Any] = {}
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            when = _as_date(
                item.get("calendarDate")
                or item.get("date")
                or item.get("startDate")
            )
            if when:
                result[when] = item
    elif isinstance(payload, dict):
        for key in ("racePredictions", "values", "stats", "data", "items"):
            if isinstance(payload.get(key), list):
                result.update(_dated_items(payload[key]))
        when = _as_date(payload.get("calendarDate") or payload.get("date"))
        if when:
            result[when] = payload
    return result


def _lactate_dated_items(payload: Any) -> dict[date, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    result: dict[date, dict[str, Any]] = {}

    def add_series(series: Any, target_key: str) -> None:
        if not isinstance(series, list):
            return
        for item in series:
            if not isinstance(item, dict):
                continue
            when = _as_date(
                item.get("calendarDate") or item.get("date") or item.get("startDate")
            )
            if not when:
                continue
            value = _number(
                item.get("value")
                or item.get("metricValue")
                or item.get(target_key)
            )
            if value is not None:
                result.setdefault(when, {})[target_key] = value

    add_series(payload.get("speed"), "speed")
    add_series(payload.get("heart_rate"), "heartRate")
    return result


def upsert_performance_range(
    db: Session,
    start: date,
    end: date,
    race: Any = None,
    tolerance: Any = None,
    lactate: Any = None,
) -> int:
    race_by_day = _dated_items(race)
    tolerance_by_day = _dated_items(tolerance)
    lactate_by_day = _lactate_dated_items(lactate)
    days = sorted(set(race_by_day) | set(tolerance_by_day) | set(lactate_by_day))
    count = 0
    for day in days:
        if day < start or day > end:
            continue
        upsert_performance_metric(
            db,
            day,
            race=race_by_day.get(day),
            tolerance=tolerance_by_day.get(day),
            lactate=lactate_by_day.get(day),
        )
        count += 1
    return count


def upsert_personal_records(db: Session, payload: Any) -> int:
    if isinstance(payload, dict):
        candidates = (
            payload.get("records")
            or payload.get("personalRecords")
            or payload.get("personalRecordList")
            or []
        )
        if not candidates and any(
            key in payload for key in ("type", "recordType", "personalRecordType")
        ):
            candidates = [payload]
    elif isinstance(payload, list):
        candidates = payload
    else:
        candidates = []
    count = 0
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            continue
        record_type = str(
            item.get("type")
            or item.get("recordType")
            or item.get("personalRecordType")
            or item.get("name")
            or f"record_{index}"
        )
        value = _number(
            item.get("value")
            or item.get("recordValue")
            or item.get("time")
            or item.get("distance")
        )
        record_date = _as_date(
            item.get("date")
            or item.get("recordDate")
            or item.get("activityDate")
            or item.get("calendarDate")
        )
        raw_activity_id = (
            item.get("activityId")
            or item.get("activityID")
            or item.get("garminActivityId")
        )
        activity_id = str(raw_activity_id) if raw_activity_id is not None else None
        unit = item.get("unit") or item.get("valueUnit")
        record_id = f"{record_type}:{record_date}:{activity_id}:{value}"
        row = db.get(PersonalRecord, record_id) or PersonalRecord(
            record_id=record_id,
            record_type=record_type,
            raw_json={},
        )
        row.record_type = record_type
        row.value = value
        row.unit = str(unit) if unit is not None else None
        row.record_date = record_date
        row.activity_id = activity_id
        row.raw_json = item
        db.add(row)
        count += 1
    return count
