"""Backfill current Garmin training-status fields from the stored raw payloads."""

import json
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "0003_backfill_nested_training_metrics"
down_revision = "0002_sync_backfill_state"
branch_labels = None
depends_on = None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first(data: dict[str, Any], *names: str) -> Any:
    for name in names:
        if data.get(name) is not None:
            return data[name]
    return None


def _primary_device(values: Any) -> dict[str, Any]:
    devices = [item for item in _mapping(values).values() if isinstance(item, dict)]
    return next(
        (item for item in devices if item.get("primaryTrainingDevice")),
        devices[0] if devices else {},
    )


def _nested_values(raw_json: str | None) -> dict[str, Any]:
    try:
        status = _mapping(_mapping(json.loads(raw_json or "{}")).get("status"))
    except (TypeError, json.JSONDecodeError):
        return {}

    vo2 = _mapping(_mapping(status.get("mostRecentVO2Max")).get("generic"))
    latest = _primary_device(
        _mapping(status.get("mostRecentTrainingStatus")).get("latestTrainingStatusData")
    )
    acute = _mapping(latest.get("acuteTrainingLoadDTO"))
    return {
        "vo2max": _first(vo2, "vo2MaxValue", "vo2MaxPreciseValue"),
        "training_load": _first(latest, "weeklyTrainingLoad")
        if _first(latest, "weeklyTrainingLoad") is not None
        else _first(acute, "dailyTrainingLoadAcute"),
        "acute_load": _first(acute, "dailyTrainingLoadAcute"),
        "training_status": _first(latest, "trainingStatusFeedbackPhrase", "trainingStatus"),
    }


def upgrade() -> None:
    connection = op.get_bind()
    if "training_metrics" not in sa.inspect(connection).get_table_names():
        return
    rows = connection.execute(
        sa.text("SELECT metric_date, raw_json FROM training_metrics")
    ).mappings()
    statement = sa.text(
        """
        UPDATE training_metrics
        SET vo2max = COALESCE(vo2max, :vo2max),
            training_load = COALESCE(training_load, :training_load),
            acute_load = COALESCE(acute_load, :acute_load),
            training_status = COALESCE(training_status, :training_status)
        WHERE metric_date = :metric_date
        """
    )
    for row in rows:
        values = _nested_values(row["raw_json"])
        if any(value is not None for value in values.values()):
            connection.execute(statement, {"metric_date": row["metric_date"], **values})


def downgrade() -> None:
    # The migration only fills previously NULL values and deliberately preserves source data.
    pass
