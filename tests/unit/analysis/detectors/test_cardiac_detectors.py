from __future__ import annotations

from datetime import datetime, timedelta

from health_log.analysis.detectors.cardiac import (
    assess_atrial_fibrillation_risk,
    assess_bradycardia_risk,
    assess_irregular_rhythm_risk,
)
from health_log.analysis.models import TimeWindow

_WINDOW = TimeWindow.MONTH
_NOW = datetime(2026, 3, 1, 12, 0, 0)


def _sleep_seg(base: datetime, hours: float = 7.0) -> tuple[datetime, datetime]:
    return base, base + timedelta(hours=hours)


def _hr_series(base: datetime, value: float, count: int, interval_min: int = 5) -> list[tuple[datetime, float]]:
    return [(base + timedelta(minutes=i * interval_min), value) for i in range(count)]


class TestBradycardiaRisk:
    def test_insufficient_data_returns_unknown(self):
        result = assess_bradycardia_risk([], window=_WINDOW)
        assert result.severity == "unknown"
        assert result.score == 0.0
        assert result.confidence == 0.0

    def test_normal_resting_hr_returns_none(self):
        base = _NOW - timedelta(hours=8)
        sleep = [_sleep_seg(base)]
        hr = _hr_series(base, 62.0, 25)
        result = assess_bradycardia_risk(hr, sleep_segments=sleep, window=_WINDOW)
        assert result.severity == "none"
        assert result.score == 0.0

    def test_episodes_below_50_detected(self):
        base = _NOW - timedelta(hours=8)
        sleep = [_sleep_seg(base)]
        hr = _hr_series(base, 62.0, 25)
        ep_start = base + timedelta(hours=3)
        for i in range(5):
            hr.append((ep_start + timedelta(minutes=i * 2), 44.0))
        result = assess_bradycardia_risk(hr, sleep_segments=sleep, window=_WINDOW)
        assert result.score > 0
        assert result.severity in {"low", "medium", "high"}
        assert result.supporting_metrics["episode_count"] >= 1

    def test_low_hr_event_boosts_score(self):
        base = _NOW - timedelta(hours=8)
        sleep = [_sleep_seg(base)]
        hr = _hr_series(base, 62.0, 25)
        ep_start = base + timedelta(hours=3)
        for i in range(5):
            hr.append((ep_start + timedelta(minutes=i * 2), 44.0))

        without_event = assess_bradycardia_risk(hr, sleep_segments=sleep, window=_WINDOW)
        with_event = assess_bradycardia_risk(hr, sleep_segments=sleep, low_hr_event_count=2, window=_WINDOW)
        assert with_event.score > without_event.score

    def test_medium_high_severity_recommends_cardiologist(self):
        base = _NOW - timedelta(hours=8)
        sleep = [_sleep_seg(base)]
        hr = _hr_series(base, 62.0, 25)
        for cycle in range(3):
            ep_start = base + timedelta(hours=1 + cycle * 2)
            for i in range(6):
                hr.append((ep_start + timedelta(minutes=i * 2), 42.0))
        result = assess_bradycardia_risk(hr, sleep_segments=sleep, low_hr_event_count=1, window=_WINDOW)
        assert result.severity in {"medium", "high"}
        assert "кардиолог" in result.recommendation.lower()

    def test_fallback_uses_bottom_20_pct_without_sleep(self):
        base = _NOW - timedelta(hours=8)
        hr = _hr_series(base, 65.0, 25)
        for i in range(6):
            hr.append((base + timedelta(hours=4, minutes=i * 2), 43.0))
        result = assess_bradycardia_risk(hr, sleep_segments=None, window=_WINDOW)
        assert result.severity not in {"not_applicable"}

    def test_episodes_at_55_bpm_now_detected(self):
        """HR=55 bpm is clinical bradycardia (< 60 bpm) — must be flagged with correct threshold."""
        base = _NOW - timedelta(hours=8)
        sleep = [_sleep_seg(base)]
        hr = _hr_series(base, 65.0, 25)
        ep_start = base + timedelta(hours=3)
        for i in range(5):
            hr.append((ep_start + timedelta(minutes=i * 2), 55.0))
        result = assess_bradycardia_risk(hr, sleep_segments=sleep, window=_WINDOW)
        assert result.score > 0
        assert result.severity in {"low", "medium", "high"}

    def test_supporting_metrics_present(self):
        base = _NOW - timedelta(hours=8)
        sleep = [_sleep_seg(base)]
        hr = _hr_series(base, 65.0, 25)
        result = assess_bradycardia_risk(hr, sleep_segments=sleep, window=_WINDOW)
        assert "rest_points_count" in result.supporting_metrics


class TestIrregularRhythmRisk:
    def test_no_events_returns_unknown(self):
        result = assess_irregular_rhythm_risk([], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"
        assert result.score == 0.0

    def test_one_event_90d_returns_low(self):
        events = [(_NOW - timedelta(days=60), "event")]
        result = assess_irregular_rhythm_risk(events, window=_WINDOW, now=_NOW)
        assert result.severity == "low"
        assert abs(result.score - 0.3) < 0.01

    def test_two_events_90d_returns_medium(self):
        events = [
            (_NOW - timedelta(days=80), "event"),
            (_NOW - timedelta(days=40), "event"),
        ]
        result = assess_irregular_rhythm_risk(events, window=_WINDOW, now=_NOW)
        assert result.severity == "medium"
        assert abs(result.score - 0.6) < 0.01

    def test_three_events_30d_returns_high(self):
        events = [
            (_NOW - timedelta(days=25), "event"),
            (_NOW - timedelta(days=15), "event"),
            (_NOW - timedelta(days=5), "event"),
        ]
        result = assess_irregular_rhythm_risk(events, window=_WINDOW, now=_NOW)
        assert result.severity == "high"
        assert result.score >= 0.8

    def test_ecg_abnormal_boosts_score(self):
        events = [(_NOW - timedelta(days=60), "event")]
        without_ecg = assess_irregular_rhythm_risk(events, window=_WINDOW, now=_NOW)
        with_ecg = assess_irregular_rhythm_risk(events, ecg_abnormal_count=1, window=_WINDOW, now=_NOW)
        assert with_ecg.score > without_ecg.score

    def test_afib_burden_boost(self):
        events = [(_NOW - timedelta(days=60), "event")]
        without_burden = assess_irregular_rhythm_risk(events, window=_WINDOW, now=_NOW)
        with_burden = assess_irregular_rhythm_risk(events, afib_burden_pct=3.0, window=_WINDOW, now=_NOW)
        assert with_burden.score > without_burden.score

    def test_score_capped_at_1(self):
        events = [(_NOW - timedelta(days=i * 5), "event") for i in range(10)]
        result = assess_irregular_rhythm_risk(
            events, afib_burden_pct=5.0, ecg_abnormal_count=2, window=_WINDOW, now=_NOW
        )
        assert result.score <= 1.0

    def test_supporting_metrics_include_event_counts(self):
        events = [(_NOW - timedelta(days=10), "event")]
        result = assess_irregular_rhythm_risk(events, window=_WINDOW, now=_NOW)
        assert "events_90d" in result.supporting_metrics
        assert "events_30d" in result.supporting_metrics


class TestAtrialFibrillationRisk:
    def test_no_data_returns_unknown(self):
        result = assess_atrial_fibrillation_risk(window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_low_burden_returns_low(self):
        burden = [(_NOW - timedelta(days=5), 0.5)]
        result = assess_atrial_fibrillation_risk(afib_burden_rows=burden, window=_WINDOW, now=_NOW)
        assert result.severity == "low"

    def test_medium_burden_returns_medium(self):
        burden = [(_NOW - timedelta(days=5), 2.5)]
        result = assess_atrial_fibrillation_risk(afib_burden_rows=burden, window=_WINDOW, now=_NOW)
        assert result.severity == "medium"

    def test_high_burden_returns_high(self):
        burden = [(_NOW - timedelta(days=5), 6.0)]
        result = assess_atrial_fibrillation_risk(afib_burden_rows=burden, window=_WINDOW, now=_NOW)
        assert result.severity == "high"

    def test_ecg_boost(self):
        events = [(_NOW - timedelta(days=10), "event")]
        without = assess_atrial_fibrillation_risk(
            irregular_rhythm_event_rows=events, window=_WINDOW, now=_NOW
        )
        with_ecg = assess_atrial_fibrillation_risk(
            irregular_rhythm_event_rows=events, ecg_afib_count=1, window=_WINDOW, now=_NOW
        )
        assert with_ecg.score > without.score

    def test_cardiologist_always_recommended(self):
        burden = [(_NOW - timedelta(days=5), 2.0)]
        result = assess_atrial_fibrillation_risk(afib_burden_rows=burden, window=_WINDOW, now=_NOW)
        assert "кардиолог" in result.recommendation.lower()

    def test_score_not_exceed_1(self):
        burden = [(_NOW - timedelta(days=i), 8.0) for i in range(10)]
        events = [(_NOW - timedelta(days=i * 3), "event") for i in range(5)]
        result = assess_atrial_fibrillation_risk(
            afib_burden_rows=burden,
            irregular_rhythm_event_rows=events,
            ecg_afib_count=3,
            window=_WINDOW,
            now=_NOW,
        )
        assert result.score <= 1.0
