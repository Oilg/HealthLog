from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from health_log.analysis.engine import HealthRiskAnalyzer, serialize_assessment
from health_log.analysis.models import TimeWindow
from tests.integration.conftest import requires_db

pytestmark = [pytest.mark.asyncio, requires_db]

_NOW = datetime(2026, 3, 15, 12, 0, 0)
_SOURCE = "TestDevice"

_WEEK_START = _NOW - timedelta(days=7)
_NIGHT_START = _NOW - timedelta(hours=12)
_FITNESS_BASELINE_START = _NOW - timedelta(days=74)
_TEMPERATURE_START = _NOW - timedelta(days=16)
_MOBILITY_START = _NOW - timedelta(days=90)


async def _insert(conn, table_name: str, row: dict) -> None:
    from sqlalchemy import text
    cols = ", ".join(f'"{k}"' for k in row.keys())
    params = ", ".join(f":{k}" for k in row.keys())
    await conn.execute(
        text(f'INSERT INTO {table_name} ({cols}) VALUES ({params}) ON CONFLICT DO NOTHING').bindparams(**row)
    )


def _make_rows(
    uid: int,
    val: float,
    timestamps: list[datetime],
    unit: str = "",
    duration: timedelta = timedelta(minutes=5),
) -> list[dict]:
    return [
        {
            "user_id": uid, "sourceName": _SOURCE, "unit": unit,
            "value": str(val), "creationDate": ts,
            "startDate": ts, "endDate": ts + duration,
        }
        for ts in timestamps
    ]


def _daily_timestamps(start: datetime, n_days: int, hour: int = 10) -> list[datetime]:
    return [start + timedelta(days=i, hours=hour) for i in range(n_days)]


def _hr_records(uid: int, n: int = 40, bpm: float = 65.0) -> list[dict]:
    rows = []
    for i in range(n):
        ts = _NOW - timedelta(hours=i * 2)
        rows.append({
            "user_id": uid, "sourceName": _SOURCE, "unit": "count/min",
            "value": str(bpm), "creationDate": ts,
            "startDate": ts, "endDate": ts + timedelta(seconds=30),
        })
    return rows


def _sleep_records(uid: int, n: int = 14, hours: float = 7.0) -> list[dict]:
    rows = []
    for i in range(n):
        s = _NOW - timedelta(days=i + 1) + timedelta(hours=22)
        rows.append({
            "user_id": uid, "sourceName": _SOURCE, "creationDate": s,
            "startDate": s, "endDate": s + timedelta(hours=hours),
        })
    return rows


def _qty_records(uid: int, table: str, val: float, n: int = 20, unit: str = "") -> list[dict]:
    rows = []
    for i in range(n):
        ts = _NOW - timedelta(days=i)
        rows.append({
            "user_id": uid, "sourceName": _SOURCE, "unit": unit,
            "value": str(val), "creationDate": ts,
            "startDate": ts, "endDate": ts + timedelta(minutes=5),
        })
    return rows


def _menstrual_records(uid: int, n_cycles: int = 5, cycle_len: int = 28) -> list[dict]:
    rows = []
    for cycle in range(n_cycles):
        s = _NOW - timedelta(days=cycle_len * (n_cycles - cycle))
        for day in range(4):
            ts = s + timedelta(days=day)
            rows.append({
                "user_id": uid, "sourceName": _SOURCE,
                "value": "HKCategoryValueMenstrualFlowMedium",
                "creationDate": ts, "startDate": ts, "endDate": ts + timedelta(hours=23),
            })
    return rows


async def _populate_hr_sleep(conn, uid: int, n_hr: int = 40, bpm: float = 65.0, n_sleep: int = 14) -> None:
    for r in _hr_records(uid, n=n_hr, bpm=bpm):
        await _insert(conn, "heart_rate", r)
    for r in _sleep_records(uid, n=n_sleep):
        await _insert(conn, "sleep_analysis", r)


async def _insert_range(conn, uid: int, table: str, val: float, start: datetime, n_days: int, unit: str = "") -> None:
    for r in _make_rows(uid, val, _daily_timestamps(start, n_days), unit=unit):
        await _insert(conn, table, r)


async def _insert_sleep_range(conn, uid: int, start: datetime, n_days: int, hours: float = 7.0) -> None:
    for i in range(n_days):
        night_start = start + timedelta(days=i) + timedelta(hours=22)
        await _insert(conn, "sleep_analysis", {
            "user_id": uid, "sourceName": _SOURCE, "creationDate": night_start,
            "startDate": night_start, "endDate": night_start + timedelta(hours=hours),
        })


async def test_analyze_window_returns_new_cardiac_assessments(db_conn, test_user_id):
    uid = test_user_id
    await _populate_hr_sleep(db_conn, uid, n_hr=80, bpm=65.0, n_sleep=20)

    episode_start = _NOW - timedelta(hours=1)
    for i in range(5):
        ts = episode_start + timedelta(seconds=i * 90)
        await _insert(db_conn, "heart_rate", {
            "user_id": uid, "sourceName": _SOURCE, "unit": "count/min",
            "value": "42.0", "creationDate": ts, "startDate": ts, "endDate": ts + timedelta(seconds=30),
        })

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.MONTH, now=_NOW)

    bradycardia = next(a for a in result["assessments"] if a.condition == "bradycardia_risk")
    assert bradycardia.severity != "unknown"
    assert bradycardia.supporting_metrics["rest_points_count"] >= 20
    assert bradycardia.supporting_metrics.get("episode_count", 0) >= 1

    irregular = next(a for a in result["assessments"] if a.condition == "irregular_rhythm_risk")
    assert "events_90d" in irregular.supporting_metrics

    afib = next(a for a in result["assessments"] if a.condition == "atrial_fibrillation_risk")
    assert "afib_burden_records" in afib.supporting_metrics


async def test_analyze_window_returns_new_vitals_assessments(db_conn, test_user_id):
    uid = test_user_id

    for r in _qty_records(uid, "oxygen_saturation", 91.0, n=5, unit="%"):
        await _insert(db_conn, "oxygen_saturation", r)
    for r in _qty_records(uid, "oxygen_saturation", 96.0, n=15, unit="%"):
        await _insert(db_conn, "oxygen_saturation", r)
    for r in _qty_records(uid, "blood_pressure_systolic", 125.0, n=10, unit="mmHg"):
        await _insert(db_conn, "blood_pressure_systolic", r)
    for r in _qty_records(uid, "blood_pressure_diastolic", 80.0, n=10, unit="mmHg"):
        await _insert(db_conn, "blood_pressure_diastolic", r)

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.MONTH, now=_NOW)

    spo2 = next(a for a in result["assessments"] if a.condition == "low_oxygen_saturation_risk")
    assert spo2.severity in {"medium", "high"}
    assert spo2.score > 0
    assert spo2.supporting_metrics["count_below_92"] >= 3

    hypert = next(a for a in result["assessments"] if a.condition == "hypertension_risk")
    assert "sbp_readings" in hypert.supporting_metrics or hypert.severity != "unknown"

    temp = next(a for a in result["assessments"] if a.condition == "temperature_shift_risk")
    assert "baseline_nights" in temp.supporting_metrics


async def test_analyze_window_returns_new_fitness_assessments(db_conn, test_user_id):
    uid = test_user_id

    baseline_start = _FITNESS_BASELINE_START
    await _insert_sleep_range(db_conn, uid, start=baseline_start, n_days=60, hours=7.0)
    await _insert_sleep_range(db_conn, uid, start=_NOW - timedelta(days=14), n_days=14, hours=5.0)

    await _insert_range(db_conn, uid, "heart_rate", 60.0, baseline_start, 60, unit="count/min")
    await _insert_range(db_conn, uid, "heart_rate", 72.0, _NOW - timedelta(days=14), 14, unit="count/min")
    await _insert_range(db_conn, uid, "heart_rate_variability", 50.0, baseline_start, 60, unit="ms")
    await _insert_range(db_conn, uid, "heart_rate_variability", 35.0, _NOW - timedelta(days=14), 14, unit="ms")

    for r in _qty_records(uid, "vo_2_max", 40.0, n=10, unit="mL/min·kg"):
        await _insert(db_conn, "vo_2_max", r)
    for r in _qty_records(uid, "walking_heart_rate_average", 110.0, n=30, unit="count/min"):
        await _insert(db_conn, "walking_heart_rate_average", r)

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.MONTH, now=_NOW)

    overload = next(a for a in result["assessments"] if a.condition == "overload_recovery_risk")
    assert overload.severity != "unknown"
    assert "signal_days_14d" in overload.supporting_metrics
    assert "recent_valid_days" in overload.supporting_metrics

    vo2 = next(a for a in result["assessments"] if a.condition == "vo2max_decline_risk")
    assert vo2.condition == "vo2max_decline_risk"


async def test_analyze_window_returns_new_mobility_assessments(db_conn, test_user_id):
    uid = test_user_id

    baseline_start = _MOBILITY_START
    await _insert_range(db_conn, uid, "walking_steadiness", 0.90, baseline_start, 30)
    await _insert_range(db_conn, uid, "walking_speed", 1.4, baseline_start, 30, unit="m/s")
    await _insert_range(db_conn, uid, "walking_step_length", 0.70, baseline_start, 30, unit="m")

    recent_start = _NOW - timedelta(days=30)
    await _insert_range(db_conn, uid, "walking_steadiness", 0.62, recent_start, 30)
    await _insert_range(db_conn, uid, "walking_speed", 0.95, recent_start, 30, unit="m/s")
    await _insert_range(db_conn, uid, "walking_step_length", 0.45, recent_start, 30, unit="m")

    for r in _qty_records(uid, "environmental_audio_exposure", 75.0, n=10, unit="dBASPL"):
        await _insert(db_conn, "environmental_audio_exposure", r)

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.MONTH, now=_NOW)

    fall = next(a for a in result["assessments"] if a.condition == "fall_risk")
    assert fall.severity != "unknown"
    assert fall.score > 0
    assert fall.supporting_metrics.get("step_length_decline_pct") is not None
    assert fall.supporting_metrics["step_length_decline_pct"] > 0

    noise = next(a for a in result["assessments"] if a.condition == "noise_exposure_risk")
    assert noise.condition == "noise_exposure_risk"


async def test_analyze_window_returns_new_weight_activity_assessments(db_conn, test_user_id):
    uid = test_user_id

    for r in _qty_records(uid, "body_mass", 85.0, n=10, unit="kg"):
        await _insert(db_conn, "body_mass", r)
    for r in _qty_records(uid, "body_mass_index", 27.5, n=10, unit="kg/m²"):
        await _insert(db_conn, "body_mass_index", r)
    for r in _qty_records(uid, "step_count", 4000, n=20, unit="count"):
        await _insert(db_conn, "step_count", r)

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.MONTH, now=_NOW)

    overweight = next(a for a in result["assessments"] if a.condition == "overweight_risk")
    assert overweight.severity in {"low", "medium", "high"}
    assert overweight.score > 0

    sedentary = next(a for a in result["assessments"] if a.condition == "sedentary_lifestyle_risk")
    assert "step_days_count" in sedentary.supporting_metrics or sedentary.severity != "unknown"


def _intermenstrual_records(uid: int, timestamps: list[datetime]) -> list[dict]:
    return [
        {
            "user_id": uid, "sourceName": _SOURCE,
            "value": "HKCategoryValueNotApplicable",
            "creationDate": ts, "startDate": ts, "endDate": ts + timedelta(hours=24),
        }
        for ts in timestamps
    ]


def _prolonged_menstrual_records(uid: int) -> list[dict]:
    rows: list[dict] = []
    # Period 1: 10 consecutive days — prolonged (> 8-day threshold).
    p1_start = _NOW - timedelta(days=66)
    for d in range(10):
        ts = p1_start + timedelta(days=d)
        rows.append({
            "user_id": uid, "sourceName": _SOURCE,
            "value": "HKCategoryValueMenstrualFlowMedium",
            "creationDate": ts, "startDate": ts, "endDate": ts + timedelta(hours=23),
        })
    # Period 2: 4 days — normal.
    p2_start = _NOW - timedelta(days=38)
    for d in range(4):
        ts = p2_start + timedelta(days=d)
        rows.append({
            "user_id": uid, "sourceName": _SOURCE,
            "value": "HKCategoryValueMenstrualFlowMedium",
            "creationDate": ts, "startDate": ts, "endDate": ts + timedelta(hours=23),
        })
    # Period 3: 4 days — normal.
    p3_start = _NOW - timedelta(days=10)
    for d in range(4):
        ts = p3_start + timedelta(days=d)
        rows.append({
            "user_id": uid, "sourceName": _SOURCE,
            "value": "HKCategoryValueMenstrualFlowMedium",
            "creationDate": ts, "startDate": ts, "endDate": ts + timedelta(hours=23),
        })
    return rows


async def test_analyze_window_returns_new_menstrual_assessments_for_female_user(
    db_conn, test_female_user_id
):
    uid = test_female_user_id

    for r in _menstrual_records(uid):
        await _insert(db_conn, "menstrual_flow", r)
    for r in _qty_records(uid, "apple_sleeping_wrist_temperature", 36.4, n=30, unit="degC"):
        await _insert(db_conn, "apple_sleeping_wrist_temperature", r)

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.MONTH, now=_NOW)

    irregularity = next(a for a in result["assessments"] if a.condition == "menstrual_irregularity_risk")
    assert irregularity.severity != "unknown"
    assert "cycle_count" in irregularity.supporting_metrics or irregularity.score >= 0

    # No intermenstrual events inserted → both signal sources are absent → unknown.
    atypical = next(a for a in result["assessments"] if a.condition == "atypical_menstrual_bleeding_risk")
    assert "intermenstrual_events" in atypical.supporting_metrics
    assert "prolonged_period_events" in atypical.supporting_metrics
    assert atypical.supporting_metrics["intermenstrual_events"] == 0
    assert atypical.supporting_metrics["prolonged_period_events"] == 0
    assert atypical.severity == "unknown"

    temp_forecast = next(
        a for a in result["assessments"] if a.condition == "menstrual_start_forecast_with_temp"
    )
    assert temp_forecast.condition == "menstrual_start_forecast_with_temp"


async def test_analyze_window_returns_atypical_menstrual_bleeding_signal_from_intermenstrual_events(
    db_conn, test_female_user_id
):
    uid = test_female_user_id

    for r in _menstrual_records(uid):
        await _insert(db_conn, "menstrual_flow", r)

    event_timestamps = [_NOW - timedelta(days=45), _NOW - timedelta(days=15)]
    for r in _intermenstrual_records(uid, event_timestamps):
        await _insert(db_conn, "intermenstrual_bleeding", r)

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.MONTH, now=_NOW)

    assessment = next(
        a for a in result["assessments"] if a.condition == "atypical_menstrual_bleeding_risk"
    )
    assert assessment.score > 0
    assert assessment.severity in {"low", "medium", "high"}
    assert assessment.supporting_metrics["intermenstrual_events"] == 2
    assert "prolonged_period_events" in assessment.supporting_metrics


async def test_analyze_window_returns_unknown_atypical_menstrual_bleeding_without_events(
    db_conn, test_female_user_id
):
    uid = test_female_user_id

    for r in _menstrual_records(uid):
        await _insert(db_conn, "menstrual_flow", r)

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.MONTH, now=_NOW)

    assessment = next(
        a for a in result["assessments"] if a.condition == "atypical_menstrual_bleeding_risk"
    )
    assert assessment.severity == "unknown"
    assert assessment.score == 0.0
    assert assessment.supporting_metrics["intermenstrual_events"] == 0
    assert assessment.supporting_metrics["prolonged_period_events"] == 0


async def test_analyze_window_detects_prolonged_period_in_atypical_bleeding_assessment(
    db_conn, test_female_user_id
):
    uid = test_female_user_id

    for r in _prolonged_menstrual_records(uid):
        await _insert(db_conn, "menstrual_flow", r)

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.MONTH, now=_NOW)

    assessment = next(
        a for a in result["assessments"] if a.condition == "atypical_menstrual_bleeding_risk"
    )
    assert assessment.supporting_metrics["prolonged_period_events"] > 0
    assert assessment.severity != "unknown"
    assert assessment.score > 0


async def test_analyze_window_does_not_crash_with_empty_data(db_conn, test_user_id):
    uid = test_user_id
    analyzer = HealthRiskAnalyzer(db_conn, uid)

    for window in (TimeWindow.NIGHT, TimeWindow.WEEK, TimeWindow.MONTH):
        result = await analyzer.analyze_window(window, now=_NOW)
        assert "assessments" in result
        assert len(result["assessments"]) > 0


async def test_serialize_assessment_includes_supporting_metrics_and_lifestyle_recommendations(
    db_conn, test_user_id
):
    uid = test_user_id

    for r in _qty_records(uid, "body_mass", 92.0, n=10, unit="kg"):
        await _insert(db_conn, "body_mass", r)
    for r in _qty_records(uid, "body_mass_index", 31.5, n=10, unit="kg/m²"):
        await _insert(db_conn, "body_mass_index", r)

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.MONTH, now=_NOW)

    for assessment in result["assessments"]:
        serialized = serialize_assessment(assessment)
        assert "supporting_metrics" in serialized, f"Missing supporting_metrics for {assessment.condition}"
        assert "condition" in serialized
        assert "severity" in serialized

    obesity = next((a for a in result["assessments"] if a.condition == "obesity_risk"), None)
    if obesity and obesity.severity not in {"unknown", "none"}:
        serialized = serialize_assessment(obesity)
        assert "lifestyle_recommendations" in serialized
        assert len(serialized["lifestyle_recommendations"]) > 0


async def test_analyze_window_week_uses_extended_history_for_temperature_shift(db_conn, test_user_id):
    uid = test_user_id

    # Baseline nights: days 3-15 before _NOW — inside 16d fetch but outside 7d week window.
    for i in range(3, 16):
        ts = _NOW - timedelta(days=i)
        await _insert(db_conn, "apple_sleeping_wrist_temperature", {
            "user_id": uid, "sourceName": _SOURCE, "unit": "degC",
            "value": "36.4", "creationDate": ts,
            "startDate": ts, "endDate": ts + timedelta(hours=8),
        })
    # Recent nights: days 0-2 — inside both 16d fetch and week window.
    for i in range(0, 3):
        ts = _NOW - timedelta(days=i)
        await _insert(db_conn, "apple_sleeping_wrist_temperature", {
            "user_id": uid, "sourceName": _SOURCE, "unit": "degC",
            "value": "37.2", "creationDate": ts,
            "startDate": ts, "endDate": ts + timedelta(hours=8),
        })

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.WEEK, now=_NOW)

    assessment = next(a for a in result["assessments"] if a.condition == "temperature_shift_risk")
    assert assessment.severity != "unknown", (
        "temperature_shift_risk returned 'unknown' — engine may be using start..end "
        "instead of the 16-day extended fetch"
    )
    assert assessment.severity in {"low", "medium", "high"}
    assert assessment.supporting_metrics["baseline_nights"] >= 7
    assert assessment.supporting_metrics["delta_c"] >= 0.3


async def test_analyze_window_week_uses_extended_history_for_overload_recovery(db_conn, test_user_id):
    uid = test_user_id

    # Baseline: 60 days of normal sleep+HR+HRV ending ~14 days before _NOW (outside week window).
    baseline_start = _FITNESS_BASELINE_START
    recent_start = _NOW - timedelta(days=14)
    await _insert_sleep_range(db_conn, uid, start=baseline_start, n_days=60, hours=7.0)
    await _insert_range(db_conn, uid, "heart_rate", 60.0, baseline_start, 60, unit="count/min")
    await _insert_range(db_conn, uid, "heart_rate_variability", 55.0, baseline_start, 60, unit="ms")

    # Recent stressed data (March 1-14): data lands in recent period but mostly OUTSIDE the week window.
    await _insert_sleep_range(db_conn, uid, start=recent_start, n_days=7, hours=4.5)
    await _insert_range(db_conn, uid, "heart_rate", 72.0, recent_start, 7, unit="count/min")
    await _insert_range(db_conn, uid, "heart_rate_variability", 32.0, recent_start, 7, unit="ms")

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.WEEK, now=_NOW)

    assessment = next(a for a in result["assessments"] if a.condition == "overload_recovery_risk")
    assert assessment.severity != "unknown", (
        "overload_recovery_risk returned 'unknown' — engine may be using start..end "
        "instead of the 74-day extended fetch for sleep/HR/HRV"
    )
    assert assessment.supporting_metrics["signal_days_14d"] >= 2
    assert assessment.supporting_metrics["recent_valid_days"] >= 7


async def test_analyze_window_week_uses_extended_history_for_fall_risk(db_conn, test_user_id):
    uid = test_user_id

    # Baseline mobility (good): days 61-90 before _NOW — inside 90d fetch, outside week.
    baseline_start = _MOBILITY_START
    await _insert_range(db_conn, uid, "walking_steadiness", 0.92, baseline_start, 30)
    await _insert_range(db_conn, uid, "walking_speed", 1.45, baseline_start, 30, unit="m/s")
    await _insert_range(db_conn, uid, "walking_step_length", 0.72, baseline_start, 30, unit="m")

    # Degraded mobility (recent): days 15-44 before _NOW — inside 90d + 30d recent, outside week.
    degraded_start = _NOW - timedelta(days=44)
    await _insert_range(db_conn, uid, "walking_steadiness", 0.62, degraded_start, 30)
    await _insert_range(db_conn, uid, "walking_speed", 0.88, degraded_start, 30, unit="m/s")
    await _insert_range(db_conn, uid, "walking_step_length", 0.45, degraded_start, 30, unit="m")

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.WEEK, now=_NOW)

    assessment = next(a for a in result["assessments"] if a.condition == "fall_risk")
    assert assessment.severity != "unknown", (
        "fall_risk returned 'unknown' — engine may be using start..end "
        "instead of the 90-day extended fetch for mobility rows"
    )
    assert assessment.supporting_metrics.get("step_length_decline_pct") is not None
    assert assessment.supporting_metrics["step_length_decline_pct"] > 10


async def test_analyze_window_night_uses_extended_history_for_respiratory_function(db_conn, test_user_id):
    uid = test_user_id

    # Baseline RR: 60 days of normal breathing — mostly outside the 12h night window.
    baseline_start = _FITNESS_BASELINE_START
    await _insert_range(db_conn, uid, "respiratory_rate", 14.0, baseline_start, 60, unit="breaths/min")

    # Recent elevated RR: 14 days — outside the 12h night window but inside 74d fetch.
    recent_start = _NOW - timedelta(days=14)
    await _insert_range(db_conn, uid, "respiratory_rate", 18.0, recent_start, 14, unit="breaths/min")

    # Load metric required by detector.
    await _insert_range(db_conn, uid, "walking_heart_rate_average", 115.0, recent_start, 14, unit="count/min")
    await _insert_range(db_conn, uid, "walking_heart_rate_average", 100.0, baseline_start, 60, unit="count/min")

    # SpO2 to satisfy detector's alternative data path.
    for r in _qty_records(uid, "oxygen_saturation", 96.0, n=10, unit="%"):
        await _insert(db_conn, "oxygen_saturation", r)

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.NIGHT, now=_NOW)

    assessment = next(a for a in result["assessments"] if a.condition == "respiratory_function_decline_risk")
    assert assessment.severity != "unknown", (
        "respiratory_function_decline_risk returned 'unknown' — engine may be using start..end "
        "instead of the 74-day extended fetch for respiratory_rate"
    )
    assert assessment.supporting_metrics["rr_recent_days"] >= 7


async def test_analyze_window_fitness_assessment_uses_baseline_history(db_conn, test_user_id):
    uid = test_user_id

    baseline_start = _FITNESS_BASELINE_START
    await _insert_sleep_range(db_conn, uid, start=baseline_start, n_days=60, hours=7.5)
    await _insert_range(db_conn, uid, "heart_rate", 58.0, baseline_start, 60, unit="count/min")
    await _insert_range(db_conn, uid, "heart_rate_variability", 60.0, baseline_start, 60, unit="ms")

    stressed_start = _NOW - timedelta(days=14)
    await _insert_sleep_range(db_conn, uid, start=stressed_start, n_days=14, hours=4.0)
    await _insert_range(db_conn, uid, "heart_rate", 75.0, stressed_start, 14, unit="count/min")
    await _insert_range(db_conn, uid, "heart_rate_variability", 28.0, stressed_start, 14, unit="ms")

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.MONTH, now=_NOW)

    overload = next(a for a in result["assessments"] if a.condition == "overload_recovery_risk")
    assert overload.severity in {"low", "medium", "high"}
    assert overload.supporting_metrics["signal_days_14d"] >= 2
    assert overload.supporting_metrics.get("baseline_resting_hr") is not None


async def test_analyze_window_mobility_assessment_uses_step_length_signal(db_conn, test_user_id):
    uid = test_user_id

    baseline_start = _MOBILITY_START
    await _insert_range(db_conn, uid, "walking_step_length", 0.75, baseline_start, 30, unit="m")
    await _insert_range(db_conn, uid, "walking_speed", 1.5, baseline_start, 30, unit="m/s")

    recent_start = _NOW - timedelta(days=30)
    await _insert_range(db_conn, uid, "walking_step_length", 0.48, recent_start, 30, unit="m")
    await _insert_range(db_conn, uid, "walking_speed", 0.90, recent_start, 30, unit="m/s")

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.MONTH, now=_NOW)

    fall = next(a for a in result["assessments"] if a.condition == "fall_risk")
    assert fall.severity != "unknown"
    assert fall.score > 0
    step_decline = fall.supporting_metrics.get("step_length_decline_pct")
    assert step_decline is not None
    assert step_decline > 20


async def test_analyze_window_vitals_assessment_uses_sleep_overlap_metrics(db_conn, test_user_id):
    uid = test_user_id

    # Insert SpO2 low measurements during sleep time.
    for i in range(5):
        night_start = _NOW - timedelta(days=i + 1) + timedelta(hours=23)
        ts = night_start + timedelta(hours=2)
        await _insert(db_conn, "oxygen_saturation", {
            "user_id": uid, "sourceName": _SOURCE, "unit": "%",
            "value": "90.5", "creationDate": ts,
            "startDate": ts, "endDate": ts + timedelta(minutes=1),
        })
        await _insert(db_conn, "sleep_analysis", {
            "user_id": uid, "sourceName": _SOURCE, "creationDate": night_start,
            "startDate": night_start, "endDate": night_start + timedelta(hours=8),
        })

    for r in _qty_records(uid, "oxygen_saturation", 97.0, n=15, unit="%"):
        await _insert(db_conn, "oxygen_saturation", r)

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    result = await analyzer.analyze_window(TimeWindow.MONTH, now=_NOW)

    spo2 = next(a for a in result["assessments"] if a.condition == "low_oxygen_saturation_risk")
    assert spo2.severity in {"medium", "high"}
    assert spo2.supporting_metrics["sleep_overlap_low_spo2_count"] > 0
    assert spo2.supporting_metrics["sleep_context_used"] is True


async def test_analyze_all_windows_preserves_full_detector_contract(db_conn, test_user_id):
    uid = test_user_id

    # Minimal data so that all windows execute without crashing.
    await _populate_hr_sleep(db_conn, uid, n_hr=40, bpm=65.0, n_sleep=14)

    # Provide enough mobility baseline to avoid unknown in fall_risk on all windows.
    await _insert_range(db_conn, uid, "walking_steadiness", 0.85, _MOBILITY_START, 30)
    await _insert_range(db_conn, uid, "walking_speed", 1.2, _MOBILITY_START, 30, unit="m/s")

    # Provide wrist temp baseline for temperature_shift_risk.
    await _insert_range(db_conn, uid, "apple_sleeping_wrist_temperature", 36.5, _TEMPERATURE_START, 14, unit="degC")

    analyzer = HealthRiskAnalyzer(db_conn, uid)
    all_results = await analyzer.analyze_all_windows(now=_NOW)

    required_conditions = {
        "temperature_shift_risk",
        "overload_recovery_risk",
        "fall_risk",
        "respiratory_function_decline_risk",
        "overweight_risk",
        "sedentary_lifestyle_risk",
    }

    for window, window_result in all_results.items():
        conditions = {a.condition for a in window_result["assessments"]}
        missing = required_conditions - conditions
        assert not missing, (
            f"Window {window.value} is missing detector(s): {missing}. "
            "Detectors must be present for all windows even if severity is 'unknown'."
        )
