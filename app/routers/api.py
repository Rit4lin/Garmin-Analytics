from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import Activity, DailyStat, Hrv, Sleep, TrainingMetric, Weight
from app.services.analytics_service import (
    format_duration,
    format_pace,
    moving_average,
    seconds_per_km,
    weekly_totals,
)
from app.services.sync_service import sync_service

router = APIRouter(prefix="/api", tags=["API"])


def start_for(days: int) -> date:
    if days < 1 or days > 3650:
        raise HTTPException(422, "El periodo debe estar entre 1 y 3650 días")
    return date.today() - timedelta(days=days - 1)


def activity_payload(row: Activity) -> dict[str, object]:
    pace = seconds_per_km(row.distance_meters, row.moving_duration_seconds or row.duration_seconds)
    return {
        "id": row.activity_id,
        "date": row.start_time.isoformat(),
        "name": row.name,
        "type": row.activity_type,
        "duration_seconds": row.duration_seconds,
        "duration": format_duration(row.duration_seconds),
        "distance_meters": row.distance_meters,
        "distance_km": round((row.distance_meters or 0) / 1000, 2),
        "pace_seconds": pace,
        "pace": format_pace(pace),
        "calories": row.calories,
        "avg_hr": row.avg_hr,
        "max_hr": row.max_hr,
        "training_load": row.training_load,
        "aerobic_te": row.aerobic_te,
    }


@router.get("/summary")
def summary(
    days: int = Query(30, ge=1, le=3650), db: Session = Depends(get_db)
) -> dict[str, object]:
    start = start_for(days)
    activities = list(
        db.scalars(
            select(Activity)
            .where(Activity.start_time >= datetime.combine(start, datetime.min.time()))
            .order_by(Activity.start_time)
        )
    )
    stats = list(
        db.scalars(
            select(DailyStat).where(DailyStat.stat_date >= start).order_by(DailyStat.stat_date)
        )
    )
    hrv = list(db.scalars(select(Hrv).where(Hrv.hrv_date >= start).order_by(Hrv.hrv_date)))
    sleep = list(
        db.scalars(select(Sleep).where(Sleep.sleep_date >= start).order_by(Sleep.sleep_date))
    )
    training = list(
        db.scalars(
            select(TrainingMetric)
            .where(TrainingMetric.metric_date >= start)
            .order_by(TrainingMetric.metric_date)
        )
    )
    weekly = weekly_totals(
        (item.start_time.date(), item.duration_seconds, item.distance_meters) for item in activities
    )
    daily = moving_average(
        [
            {
                "date": item.stat_date.isoformat(),
                "steps": item.steps,
                "resting_hr": item.resting_hr,
                "stress": item.stress_avg,
                "body_battery": item.body_battery_high,
            }
            for item in stats
        ],
        "steps",
        7,
    )
    return {
        "cards": {
            "entrenamientos": len(activities),
            "horas_entrenadas": round(sum(a.duration_seconds or 0 for a in activities) / 3600, 1),
            "km": round(sum(a.distance_meters or 0 for a in activities) / 1000, 1),
            "pasos": sum(x.steps or 0 for x in stats),
            "vo2max": next((x.vo2max for x in reversed(training) if x.vo2max is not None), None),
            "fc_reposo": next(
                (x.resting_hr for x in reversed(stats) if x.resting_hr is not None), None
            ),
            "hrv": next(
                (x.overnight_avg for x in reversed(hrv) if x.overnight_avg is not None), None
            ),
            "sueno_horas": round((sleep[-1].duration_seconds or 0) / 3600, 1) if sleep else None,
            "training_load": next(
                (x.training_load for x in reversed(training) if x.training_load is not None), None
            ),
        },
        "weekly": weekly,
        "daily": daily,
        "hrv": [{"date": x.hrv_date.isoformat(), "value": x.overnight_avg} for x in hrv],
        "sleep": [
            {
                "date": x.sleep_date.isoformat(),
                "hours": round((x.duration_seconds or 0) / 3600, 2),
                "score": x.score,
            }
            for x in sleep
        ],
        "training": [
            {
                "date": x.metric_date.isoformat(),
                "vo2max": x.vo2max,
                "load": x.training_load,
                "readiness": x.readiness,
            }
            for x in training
        ],
    }


@router.get("/activities")
def activities(
    days: int = Query(30, ge=1, le=3650),
    activity_type: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    query = select(Activity).where(
        Activity.start_time >= datetime.combine(start_for(days), datetime.min.time())
    )
    if activity_type:
        query = query.where(Activity.activity_type == activity_type)
    rows = list(db.scalars(query.order_by(Activity.start_time.desc())))
    types = list(
        db.scalars(
            select(Activity.activity_type)
            .distinct()
            .where(Activity.activity_type.is_not(None))
            .order_by(Activity.activity_type)
        )
    )
    return {"items": [activity_payload(row) for row in rows], "types": types}


@router.get("/activities/{activity_id}")
def activity(activity_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    row = db.get(Activity, activity_id)
    if not row:
        raise HTTPException(404, "Actividad no encontrada")
    return {
        **activity_payload(row),
        "elevation_gain": row.elevation_gain,
        "elevation_loss": row.elevation_loss,
        "cadence": row.avg_cadence,
        "power": row.avg_power,
        "anaerobic_te": row.anaerobic_te,
        "raw_details": row.details_json,
        "splits": row.splits_json,
    }


@router.get("/health")
def health(
    days: int = Query(30, ge=1, le=3650), db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    return [
        {
            "date": x.stat_date.isoformat(),
            "steps": x.steps,
            "resting_hr": x.resting_hr,
            "stress": x.stress_avg,
            "body_battery": x.body_battery_high,
            "spo2": x.spo2_avg,
            "respiration": x.respiration_avg,
        }
        for x in db.scalars(
            select(DailyStat)
            .where(DailyStat.stat_date >= start_for(days))
            .order_by(DailyStat.stat_date)
        )
    ]


@router.get("/sleep")
def sleep(
    days: int = Query(30, ge=1, le=3650), db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    return [
        {
            "date": x.sleep_date.isoformat(),
            "hours": round((x.duration_seconds or 0) / 3600, 2),
            "score": x.score,
            "deep": x.deep_seconds,
            "light": x.light_seconds,
            "rem": x.rem_seconds,
        }
        for x in db.scalars(
            select(Sleep).where(Sleep.sleep_date >= start_for(days)).order_by(Sleep.sleep_date)
        )
    ]


@router.get("/training")
def training(
    days: int = Query(30, ge=1, le=3650), db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    return [
        {
            "date": x.metric_date.isoformat(),
            "vo2max": x.vo2max,
            "training_load": x.training_load,
            "acute_load": x.acute_load,
            "status": x.training_status,
            "readiness": x.readiness,
        }
        for x in db.scalars(
            select(TrainingMetric)
            .where(TrainingMetric.metric_date >= start_for(days))
            .order_by(TrainingMetric.metric_date)
        )
    ]


@router.get("/weight")
def weight(
    days: int = Query(365, ge=1, le=3650), db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    since = datetime.combine(start_for(days), datetime.min.time())
    return [
        {
            "date": x.recorded_at.isoformat(),
            "weight_kg": x.weight_kg,
            "bmi": x.bmi,
            "body_fat": x.body_fat,
            "muscle_mass": x.muscle_mass,
            "body_water": x.body_water,
        }
        for x in db.scalars(
            select(Weight).where(Weight.recorded_at >= since).order_by(Weight.recorded_at)
        )
    ]


@router.get("/sync/status")
def sync_status() -> dict[str, object]:
    return sync_service.status()


@router.post("/sync", status_code=202)
def start_sync() -> dict[str, object]:
    if not sync_service.request_sync(force=True):
        return {"started": False, "message": "Ya hay una sincronización en curso."}
    return {"started": True, "message": "Sincronización iniciada en segundo plano."}
