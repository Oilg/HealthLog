from datetime import datetime, timedelta

from health_log.analysis.detectors.menstrual_cycle import assess_menstrual_cycle_risk
from health_log.analysis.models import TimeWindow


def _build_cycle_rows(now: datetime) -> list[tuple[datetime, str]]:
    rows: list[tuple[datetime, str]] = []
    # 4 цикла примерно по 28 дней, по 4 дня кровотечения.
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


def test_menstrual_cycle_forecast_for_female_includes_ovulation_window() -> None:
    now = datetime(2026, 3, 5, 10, 0, 0)
    rows = _build_cycle_rows(now)

    assessment = assess_menstrual_cycle_risk(
        menstrual_rows=rows,
        window=TimeWindow.MONTH,
        now=now,
    )

    assert assessment.severity in {"medium", "high", "low"}
    assert assessment.score > 0
    assert "окно овуляции" in assessment.summary
