import asyncio
from datetime import datetime, timedelta

from health_log.analysis.engine import HealthRiskAnalyzer
from health_log.analysis.models import TimeWindow
from health_log.analysis.rules import (
    assess_illness_onset_risk,
    assess_sleep_apnea_risk,
    assess_tachycardia_risk,
    build_sleep_apnea_event_rows,
)
from health_log.repositories.v1 import tables


def test_sleep_apnea_risk_uses_multi_signal_evidence():
    now = datetime(2026, 2, 26, 2, 0, 0)
    respiratory = []
    heart = []
    hrv = []

    for i in range(60):
        ts = now - timedelta(minutes=60 - i)
        rr = 13 if i % 10 else 7
        hr = 72 if i % 10 else 95
        hrv_v = 40 if i % 10 else 24
        respiratory.append((ts, rr))
        heart.append((ts, hr))
        hrv.append((ts, hrv_v))

    assessment = assess_sleep_apnea_risk(respiratory, heart, hrv, window=TimeWindow.NIGHT)

    assert assessment.score > 0.4
    assert assessment.confidence > 0.3
    assert assessment.severity in {"medium", "high"}


def test_tachycardia_risk_detects_frequent_high_hr():
    now = datetime(2026, 2, 26, 10, 0, 0)
    heart = [(now - timedelta(minutes=i), 105 if i < 20 else 78) for i in range(80)]

    assessment = assess_tachycardia_risk(heart, window=TimeWindow.WEEK)

    assert assessment.score > 0.2
    assert assessment.severity in {"low", "medium", "high"}


def test_sleep_apnea_event_builder_returns_insertable_rows():
    base = datetime(2026, 2, 26, 1, 0, 0)
    respiratory = [
        (base, 12),
        (base + timedelta(seconds=15), 7),
        (base + timedelta(seconds=45), 13),
    ]
    heart = [
        (base + timedelta(seconds=15), 95),
        (base + timedelta(seconds=45), 72),
    ]
    hrv = [
        (base + timedelta(seconds=15), 25),
        (base + timedelta(seconds=45), 40),
    ]

    events = build_sleep_apnea_event_rows(respiratory, heart, hrv)

    assert len(events) == 1
    event = events[0]
    assert event["start_time"] == base
    assert event["end_time"] == base + timedelta(seconds=15)
    assert event["detected_by"] == "rule_engine_v1"


def test_illness_onset_risk_detects_hr_up_and_hrv_down_trend():
    now = datetime(2026, 2, 26, 10, 0, 0)
    heart = []
    hrv = []
    resp = []
    sleep = []

    for day_idx in range(70):
        day = now - timedelta(days=69 - day_idx)
        sleep_start = day.replace(hour=23, minute=0, second=0, microsecond=0) - timedelta(days=1)
        sleep_end = day.replace(hour=7, minute=0, second=0, microsecond=0)
        sleep.append((sleep_start, sleep_end))
        for m in range(24):
            ts = day + timedelta(minutes=20 * m)
            if day_idx < 67:
                heart_val = 62 + (m % 3)
                hrv_val = 58 - (m % 2)
                resp_val = 13 + (m % 2) * 0.2
            else:
                heart_val = 72 + (m % 3)
                hrv_val = 40 - (m % 2)
                resp_val = 15 + (m % 2) * 0.2
            heart.append((ts, heart_val))
            hrv.append((ts, hrv_val))
            resp.append((ts, resp_val))

    assessment = assess_illness_onset_risk(
        heart,
        hrv,
        respiratory_rows=resp,
        sleep_rows=sleep,
        window=TimeWindow.WEEK,
    )

    assert assessment.score >= 0.5
    assert assessment.confidence > 0.5
    assert assessment.severity in {"medium", "high"}


def test_health_risk_analyzer_uses_extended_history_for_illness_onset():
    now = datetime(2026, 2, 26, 10, 0, 0)
    heart = []
    hrv = []
    resp = []
    sleep = []

    for day_idx in range(70):
        day = now - timedelta(days=69 - day_idx)
        sleep_start = day.replace(hour=23, minute=0, second=0, microsecond=0) - timedelta(days=1)
        sleep_end = day.replace(hour=7, minute=0, second=0, microsecond=0)
        sleep.append((sleep_start, sleep_end))
        for m in range(24):
            ts = day + timedelta(minutes=20 * m)
            if day_idx < 67:
                heart_val = 62 + (m % 3)
                hrv_val = 58 - (m % 2)
                resp_val = 13 + (m % 2) * 0.2
            else:
                heart_val = 72 + (m % 3)
                hrv_val = 40 - (m % 2)
                resp_val = 15 + (m % 2) * 0.2
            heart.append((ts, heart_val))
            hrv.append((ts, hrv_val))
            resp.append((ts, resp_val))

    analyzer = HealthRiskAnalyzer(connection=None, user_id=1)  # type: ignore[arg-type]
    call_ranges: list[tuple[str, datetime, datetime]] = []

    async def fake_fetch_rows(table, start: datetime, end: datetime):
        call_ranges.append((table.name, start, end))
        if table.name == tables.heart_rate.name:
            return heart
        if table.name == tables.heart_rate_variability.name:
            return hrv
        if table.name == tables.respiratory_rate.name:
            return resp
        return []

    async def fake_sleep_segments(start: datetime, end: datetime):
        call_ranges.append((tables.sleep_analysis.name, start, end))
        return sleep

    analyzer._fetch_rows = fake_fetch_rows  # type: ignore[assignment]
    analyzer._fetch_sleep_segments = fake_sleep_segments  # type: ignore[assignment]

    result = asyncio.run(analyzer.analyze_window(TimeWindow.WEEK, now=now))
    illness = next(a for a in result["assessments"] if a.condition == "illness_onset_risk")

    min_required_start = now - timedelta(days=63)
    assert any(
        name == tables.heart_rate.name and start <= min_required_start for name, start, _ in call_ranges
    )
    assert illness.severity in {"medium", "high"}
