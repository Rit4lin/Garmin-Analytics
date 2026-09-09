from datetime import date

from app.services.analytics_service import (
    format_duration,
    format_pace,
    seconds_per_km,
    weekly_totals,
)


def test_conversions() -> None:
    assert seconds_per_km(5000, 1500) == 300
    assert format_pace(300) == "5:00 min/km"
    assert format_duration(3661) == "1:01:01"


def test_weekly_aggregation() -> None:
    result = weekly_totals([(date(2026, 1, 5), 3600, 5000), (date(2026, 1, 6), 1800, 3000)])
    assert result == [
        {"week": "2026-01-05", "activities": 2.0, "duration": 5400.0, "distance": 8000.0}
    ]
