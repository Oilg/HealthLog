from __future__ import annotations

from datetime import datetime, timedelta

from health_log.analysis.detectors.vitals import (
    assess_hypertension_risk,
    assess_hypotension_risk,
    assess_low_oxygen_saturation_risk,
    assess_temperature_shift_risk,
)
from health_log.analysis.models import TimeWindow

_WINDOW = TimeWindow.MONTH
_NOW = datetime(2026, 3, 15, 12, 0, 0)


def _ts(days_ago: float) -> datetime:
    return _NOW - timedelta(days=days_ago)


class TestLowOxygenSaturation:
    def test_insufficient_data_returns_unknown(self):
        result = assess_low_oxygen_saturation_risk([], window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"
        assert result.score == 0.0

    def test_normal_spo2_returns_none(self):
        rows = [(_ts(i), 97.0) for i in range(12)]
        result = assess_low_oxygen_saturation_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "none"
        assert result.score == 0.0

    def test_two_readings_below_94_returns_low(self):
        rows = [(_ts(i), 97.0) for i in range(10)]
        rows[2] = (_ts(2), 93.0)
        rows[5] = (_ts(5), 93.0)
        result = assess_low_oxygen_saturation_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "low"
        assert result.score > 0

    def test_three_readings_below_92_returns_medium(self):
        rows = [(_ts(i), 97.0) for i in range(12)]
        for idx in [1, 3, 5]:
            rows[idx] = (_ts(idx), 91.0)
        result = assess_low_oxygen_saturation_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity in {"medium", "high"}

    def test_two_readings_below_90_returns_high(self):
        rows = [(_ts(i), 97.0) for i in range(12)]
        rows[2] = (_ts(2), 88.0)
        rows[4] = (_ts(4), 89.0)
        result = assess_low_oxygen_saturation_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "high"

    def test_sleep_context_boosts_confidence(self):
        rows = [(_ts(i), 97.0) for i in range(12)]
        rows[2] = (_ts(2), 93.0)
        rows[5] = (_ts(5), 93.0)
        sleep_segs = [
            (_ts(2 + 0.4), _ts(2 - 0.1)),
            (_ts(5 + 0.4), _ts(5 - 0.1)),
        ]
        with_sleep = assess_low_oxygen_saturation_risk(rows, sleep_segments=sleep_segs, window=_WINDOW, now=_NOW)
        without_sleep = assess_low_oxygen_saturation_risk(rows, window=_WINDOW, now=_NOW)
        assert with_sleep.confidence >= without_sleep.confidence

    def test_single_low_point_ignored(self):
        rows = [(_ts(i), 97.0) for i in range(12)]
        rows[3] = (_ts(3), 93.0)
        result = assess_low_oxygen_saturation_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "none"


class TestHypertensionRisk:
    def test_insufficient_returns_unknown(self):
        rows = [(_ts(i), 125.0) for i in range(3)]
        result = assess_hypertension_risk(rows, [], window=_WINDOW)
        assert result.severity == "unknown"

    def test_normal_bp_returns_none(self):
        sbp = [(_ts(i * 3), 118.0) for i in range(7)]
        dbp = [(_ts(i * 3), 76.0) for i in range(7)]
        result = assess_hypertension_risk(sbp, dbp, window=_WINDOW)
        assert result.severity == "none"

    def test_stage1_average_returns_low(self):
        sbp = [(_ts(i * 3), 132.0) for i in range(7)]
        dbp = [(_ts(i * 3), 82.0) for i in range(7)]
        result = assess_hypertension_risk(sbp, dbp, window=_WINDOW)
        assert result.severity in {"low", "medium"}

    def test_stage2_average_returns_medium(self):
        sbp = [(_ts(i * 3), 145.0) for i in range(8)]
        dbp = [(_ts(i * 3), 92.0) for i in range(8)]
        result = assess_hypertension_risk(sbp, dbp, window=_WINDOW)
        assert result.severity in {"medium", "high"}

    def test_high_average_returns_high(self):
        sbp = [(_ts(i * 3), 165.0) for i in range(8)]
        dbp = [(_ts(i * 3), 102.0) for i in range(8)]
        result = assess_hypertension_risk(sbp, dbp, window=_WINDOW)
        assert result.severity == "high"

    def test_single_high_day_no_signal(self):
        sbp = [
            (_ts(0), 160.0),
            (_ts(3), 118.0),
            (_ts(6), 118.0),
            (_ts(9), 118.0),
            (_ts(12), 118.0),
            (_ts(15), 118.0),
        ]
        dbp = [(_ts(i * 3), 78.0) for i in range(6)]
        result = assess_hypertension_risk(sbp, dbp, window=_WINDOW)
        assert result.severity == "none"


class TestHypotensionRisk:
    def test_insufficient_returns_unknown(self):
        rows = [(_ts(i), 95.0) for i in range(3)]
        result = assess_hypotension_risk(rows, window=_WINDOW)
        assert result.severity == "unknown"

    def test_normal_sbp_returns_none(self):
        sbp = [(_ts(i * 3), 115.0) for i in range(7)]
        result = assess_hypotension_risk(sbp, window=_WINDOW)
        assert result.severity == "none"

    def test_low_sbp_returns_low(self):
        sbp = [(_ts(i * 3), 97.0) for i in range(7)]
        result = assess_hypotension_risk(sbp, window=_WINDOW)
        assert result.severity == "low"

    def test_very_low_sbp_with_tachycardia_returns_high(self):
        sbp = [(_ts(i), 87.0) for i in range(8)]
        hr = [(_ts(i), 95.0) for i in range(8)]
        result = assess_hypotension_risk(sbp, heart_rows=hr, window=_WINDOW)
        assert result.severity == "high"


class TestTemperatureShiftRisk:
    def _build_wrist_temp(self, baseline_c: float, recent_c: float) -> list[tuple[datetime, float]]:
        rows = []
        for day in range(16, 2, -1):
            rows.append((_NOW - timedelta(days=day), baseline_c + (day % 3) * 0.01))
        for day in range(2, 0, -1):
            rows.append((_NOW - timedelta(days=day), recent_c))
        return rows

    def test_insufficient_baseline_returns_unknown(self):
        rows = [(_NOW - timedelta(days=1), 36.5)]
        result = assess_temperature_shift_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_no_shift_returns_none(self):
        rows = self._build_wrist_temp(36.5, 36.5)
        result = assess_temperature_shift_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_shift_0_3_returns_low(self):
        rows = self._build_wrist_temp(36.5, 36.85)
        result = assess_temperature_shift_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "low"
        assert result.score > 0

    def test_shift_0_5_returns_medium(self):
        rows = self._build_wrist_temp(36.5, 37.05)
        result = assess_temperature_shift_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity in {"medium", "high"}

    def test_shift_0_7_returns_high(self):
        rows = self._build_wrist_temp(36.5, 37.25)
        result = assess_temperature_shift_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "high"

    def test_hr_boost_increases_score(self):
        temp_rows = self._build_wrist_temp(36.5, 37.0)
        baseline_hr = [(_NOW - timedelta(days=d), 62.0) for d in range(5, 17)]
        recent_hr = [(_NOW - timedelta(days=d), 70.0) for d in range(1, 3)]
        without = assess_temperature_shift_risk(temp_rows, window=_WINDOW, now=_NOW)
        with_hr = assess_temperature_shift_risk(
            temp_rows, heart_rows=baseline_hr + recent_hr, window=_WINDOW, now=_NOW
        )
        assert with_hr.score >= without.score

    def test_supporting_metrics_delta(self):
        rows = self._build_wrist_temp(36.5, 37.1)
        result = assess_temperature_shift_risk(rows, window=_WINDOW, now=_NOW)
        if result.severity != "none":
            assert "delta_c" in result.supporting_metrics
            assert result.supporting_metrics["delta_c"] > 0
