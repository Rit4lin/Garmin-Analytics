from collections.abc import Iterable
from datetime import date, timedelta


def seconds_per_km(distance_meters: float | None, seconds: float | None) -> float | None:
    if not distance_meters or not seconds or distance_meters <= 0:
        return None
    return seconds / (distance_meters / 1000)


def format_duration(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    seconds = round(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:d}:{seconds:02d}"


def format_pace(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    minutes, remaining = divmod(round(seconds), 60)
    return f"{minutes}:{remaining:02d} min/km"


def moving_average(
    values: list[dict[str, object]], field: str, days: int
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    window: list[float] = []
    for row in values:
        value = row.get(field)
        if isinstance(value, (int, float)):
            window.append(float(value))
        if len(window) > days:
            window.pop(0)
        result.append(
            {**row, f"{field}_ma{days}": round(sum(window) / len(window), 2) if window else None}
        )
    return result


def week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def weekly_totals(
    rows: Iterable[tuple[date, float | None, float | None]],
) -> list[dict[str, object]]:
    totals: dict[date, dict[str, float]] = {}
    for when, duration, distance in rows:
        bucket = totals.setdefault(
            week_start(when), {"activities": 0.0, "duration": 0.0, "distance": 0.0}
        )
        bucket["activities"] += 1
        bucket["duration"] += duration or 0
        bucket["distance"] += distance or 0
    return [{"week": key.isoformat(), **value} for key, value in sorted(totals.items())]
