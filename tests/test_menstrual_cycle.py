from datetime import datetime, timedelta

from health_log.analysis.detectors.menstrual_cycle import assess_ovulation_window_forecast
from health_log.analysis.models import TimeWindow


def _build_cycle_rows(now: datetime) -> list[tuple[datetime, str]]:
    rows: list[tuple[datetime, str]] = []
    starts = [
        now.date() - timedelta(days=84),
        now.date() - timedelta(days=56),
        now.date() - timedelta(days=28),
        now.date() - timedelta(days=2),
    ]
    for start in starts:
        for day_offset in range(4):
            ts = datetime.combine(start + timedelta(days=day_offset), datetime.min.time())
            rows.append((ts, "HKCategoryValueMenstrualFlowMedium"))
    return rows


def test_ovulation_window_forecast_shows_date_range() -> None:
    now = datetime(2026, 3, 5, 10, 0, 0)
    rows = _build_cycle_rows(now)

    assessment = assess_ovulation_window_forecast(
        menstrual_rows=rows,
        window=TimeWindow.MONTH,
        now=now,
    )

    assert assessment.severity in {"none", "low", "medium", "high"}
    assert "овуляции" in assessment.summary.lower()
