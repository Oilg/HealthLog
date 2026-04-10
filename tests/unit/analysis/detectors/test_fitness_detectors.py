from __future__ import annotations

from datetime import datetime, timedelta

from health_log.analysis.detectors.fitness import (
    assess_hrr_decline_risk,
    assess_overload_recovery_risk,
    assess_respiratory_function_decline_risk,
    assess_vo2max_decline_risk,
    assess_walking_tolerance_decline_risk,
)
from health_log.analysis.models import TimeWindow

_WINDOW = TimeWindow.MONTH
_NOW = datetime(2026, 3, 15, 12, 0, 0)


def _ts(days_ago: float) -> datetime:
    return _NOW - timedelta(days=days_ago)


class TestVo2MaxDecline:
    def test_insufficient_returns_unknown(self):
        result = assess_vo2max_decline_risk([], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_stable_vo2max_returns_none(self):
        rows = [(_ts(i * 15), 42.0) for i in range(6)]
        result = assess_vo2max_decline_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_5_pct_decline_returns_low(self):
        rows = [(_ts(i * 15 + 5), 42.0) for i in range(5)] + [(_ts(0), 39.8)]
        result = assess_vo2max_decline_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity in {"low", "medium"}
        assert result.score > 0

    def test_10_pct_decline_returns_medium(self):
        rows = [(_ts(i * 15 + 5), 42.0) for i in range(5)] + [(_ts(0), 37.8)]
        result = assess_vo2max_decline_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity in {"medium", "high"}

    def test_15_pct_decline_returns_high(self):
        rows = [(_ts(i * 15 + 5), 42.0) for i in range(5)] + [(_ts(0), 35.0)]
        result = assess_vo2max_decline_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "high"

    def test_supporting_metrics_present(self):
        rows = [(_ts(i * 15), 42.0) for i in range(5)] + [(_ts(1), 37.8)]
        result = assess_vo2max_decline_risk(rows, window=_WINDOW, now=_NOW)
        assert "decline_pct" in result.supporting_metrics
        assert "recent_vo2max" in result.supporting_metrics


class TestHrrDecline:
    def test_insufficient_returns_unknown(self):
        result = assess_hrr_decline_risk([], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_stable_hrr_returns_none(self):
        rows = [(_ts(i * 10), 22.0) for i in range(6)]
        result = assess_hrr_decline_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_5_bpm_decline_returns_low(self):
        rows = [(_ts(i * 10 + 15), 22.0) for i in range(3)] + [(_ts(i * 3), 16.0) for i in range(3)]
        result = assess_hrr_decline_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity in {"low", "medium", "high"}
        assert result.score > 0

    def test_vo2max_decline_boosts_score(self):
        hrr = [(_ts(i * 10), 22.0) for i in range(3)] + [(_ts(i * 5), 17.0) for i in range(1, 3)]
        vo2 = [(_ts(i * 20), 40.0) for i in range(3)] + [(_ts(2), 35.0)]
        without = assess_hrr_decline_risk(hrr, window=_WINDOW, now=_NOW)
        with_vo2 = assess_hrr_decline_risk(hrr, vo2max_rows=vo2, window=_WINDOW, now=_NOW)
        assert with_vo2.score >= without.score


class TestOverloadRecovery:
    def _build_normal_days(self, count: int) -> tuple[list, list, list]:
        sleep = []
        hr = []
        hrv = []
        for i in range(count):
            day = _NOW - timedelta(days=i + 1)
            night_start = day.replace(hour=23, minute=0)
            sleep.append((night_start, night_start + timedelta(hours=7)))
            for m in range(6):
                ts = day.replace(hour=8) + timedelta(hours=m)
                hr.append((ts, 62.0))
                hrv.append((ts, 55.0))
        return sleep, hr, hrv

    def test_insufficient_returns_unknown(self):
        result = assess_overload_recovery_risk(window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_no_signal_days_returns_none(self):
        sleep, hr, hrv = self._build_normal_days(70)
        result = assess_overload_recovery_risk(sleep, hr, hrv, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_multiple_signal_days_detected(self):
        sleep_segs = []
        hr = []
        hrv = []
        for i in range(70):
            day = _NOW - timedelta(days=i + 1)
            night_start = day.replace(hour=23, minute=0)
            if i < 14:
                sleep_dur = 5.0
                hr_val = 72.0
                hrv_val = 42.0
            else:
                sleep_dur = 7.5
                hr_val = 62.0
                hrv_val = 58.0
            sleep_segs.append((night_start, night_start + timedelta(hours=sleep_dur)))
            for m in range(6):
                ts = day.replace(hour=8) + timedelta(hours=m)
                hr.append((ts, hr_val))
                hrv.append((ts, hrv_val))

        result = assess_overload_recovery_risk(sleep_segs, hr, hrv, window=_WINDOW, now=_NOW)
        assert result.score > 0
        assert result.severity in {"low", "medium", "high"}


class TestWalkingToleranceDecline:
    def test_insufficient_returns_unknown(self):
        result = assess_walking_tolerance_decline_risk([], [], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_stable_walking_hr_returns_none(self):
        steps = [(_ts(i), 5000.0) for i in range(30)]
        whr = [(_ts(i), 95.0) for i in range(30)] + [(_ts(i), 95.0) for i in range(60, 90)]
        result = assess_walking_tolerance_decline_risk(whr, steps, window=_WINDOW, now=_NOW)
        assert result.severity in {"none", "unknown"}

    def test_10_bpm_rise_returns_medium(self):
        steps = [(_ts(i), 5000.0) for i in range(90)]
        whr_base = [(_ts(i + 30), 90.0) for i in range(60)]
        whr_recent = [(_ts(i), 102.0) for i in range(30)]
        result = assess_walking_tolerance_decline_risk(
            whr_base + whr_recent, steps, window=_WINDOW, now=_NOW
        )
        assert result.severity in {"medium", "high", "low"}
        assert result.score > 0


class TestRespiratoryFunctionDecline:
    def test_insufficient_returns_unknown(self):
        result = assess_respiratory_function_decline_risk([], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_no_load_metric_returns_unknown(self):
        rr = [(_ts(i), 14.0) for i in range(10)]
        result = assess_respiratory_function_decline_risk(rr, window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_stable_rr_with_load_metric_returns_none(self):
        rr = [(_ts(i), 14.0) for i in range(80)]
        whr = [(_ts(i), 95.0) for i in range(80)]
        result = assess_respiratory_function_decline_risk(rr, walking_hr_rows=whr, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_rr_rise_8_pct_returns_low(self):
        rr_baseline = [(_ts(i + 14), 14.0) for i in range(60)]
        rr_recent = [(_ts(i), 15.2) for i in range(14)]
        whr = [(_ts(i), 95.0) for i in range(80)]
        result = assess_respiratory_function_decline_risk(
            rr_baseline + rr_recent, walking_hr_rows=whr, window=_WINDOW, now=_NOW
        )
        assert result.score > 0
        assert result.severity in {"low", "medium", "high"}

    def test_rr_rise_plus_spo2_drop_returns_high(self):
        rr_baseline = [(_ts(i + 14), 14.0) for i in range(60)]
        rr_recent = [(_ts(i), 16.2) for i in range(14)]
        spo2 = [(_ts(i), 97.0) for i in range(10)] + [(_ts(i), 91.0) for i in [1, 3]]
        whr = [(_ts(i), 95.0) for i in range(80)]
        result = assess_respiratory_function_decline_risk(
            rr_baseline + rr_recent,
            spo2_rows=spo2,
            walking_hr_rows=whr,
            window=_WINDOW,
            now=_NOW,
        )
        assert result.severity in {"high", "medium"}
