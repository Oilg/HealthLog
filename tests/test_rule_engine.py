from datetime import datetime, timedelta

from health_log.analysis.models import TimeWindow
from health_log.analysis.rules import (
    assess_illness_onset_risk,
    assess_sleep_apnea_risk,
    assess_tachycardia_risk,
    build_sleep_apnea_event_rows,
)


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

    for i in range(120):
        ts = now - timedelta(minutes=120 - i)
        if i < 84:
            heart_val = 62 + (i % 3)
            hrv_val = 58 - (i % 2)
        else:
            heart_val = 73 + (i % 3)
            hrv_val = 40 - (i % 2)
        heart.append((ts, heart_val))
        hrv.append((ts, hrv_val))

    assessment = assess_illness_onset_risk(heart, hrv, window=TimeWindow.WEEK)

    assert assessment.score >= 0.5
    assert assessment.confidence > 0.5
    assert assessment.severity in {"medium", "high"}
