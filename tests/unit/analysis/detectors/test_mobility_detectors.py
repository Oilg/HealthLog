from __future__ import annotations

from datetime import datetime, timedelta

from health_log.analysis.detectors.mobility import assess_fall_risk, assess_noise_exposure_risk
from health_log.analysis.models import TimeWindow

_WINDOW = TimeWindow.MONTH
_NOW = datetime(2026, 3, 15, 12, 0, 0)


def _ts(days_ago: float) -> datetime:
    return _NOW - timedelta(days=days_ago)


class TestFallRisk:
    def test_no_data_no_apple_event_returns_unknown(self):
        result = assess_fall_risk(window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_apple_fall_event_returns_high(self):
        result = assess_fall_risk(apple_fall_event_count=1, window=_WINDOW, now=_NOW)
        assert result.severity == "high"
        assert result.score >= 0.9

    def test_stable_steadiness_returns_none(self):
        steadiness = [(_ts(i), 0.85) for i in range(90)]
        result = assess_fall_risk(steadiness_rows=steadiness, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_significant_decline_returns_signal(self):
        baseline_s = [(_ts(i + 30), 0.85) for i in range(60)]
        recent_s = [(_ts(i), 0.65) for i in range(30)]
        result = assess_fall_risk(steadiness_rows=baseline_s + recent_s, window=_WINDOW, now=_NOW)
        assert result.score > 0
        assert result.severity in {"low", "medium", "high"}

    def test_supporting_metrics_present(self):
        steadiness = [(_ts(i), 0.85) for i in range(90)]
        result = assess_fall_risk(steadiness_rows=steadiness, window=_WINDOW, now=_NOW)
        assert len(result.supporting_metrics) > 0


class TestNoiseExposureRisk:
    def test_insufficient_data_returns_unknown(self):
        result = assess_noise_exposure_risk(window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"

    def test_low_noise_returns_none(self):
        env = [(_ts(i), 65.0) for i in range(10)]
        result = assess_noise_exposure_risk(env_audio_rows=env, window=_WINDOW, now=_NOW)
        assert result.severity == "none"

    def test_repeated_80db_returns_low(self):
        env = [(_ts(i), 82.0) for i in range(10)]
        result = assess_noise_exposure_risk(env_audio_rows=env, window=_WINDOW, now=_NOW)
        assert result.severity == "low"
        assert result.score > 0

    def test_repeated_85db_returns_medium(self):
        env = [(_ts(i), 87.0) for i in range(10)]
        result = assess_noise_exposure_risk(env_audio_rows=env, window=_WINDOW, now=_NOW)
        assert result.severity in {"medium", "high"}

    def test_repeated_90db_returns_high(self):
        env = [(_ts(i), 92.0) for i in range(10)]
        result = assess_noise_exposure_risk(env_audio_rows=env, window=_WINDOW, now=_NOW)
        assert result.severity == "high"

    def test_headphone_exposure_combined_with_env(self):
        env = [(_ts(i), 75.0) for i in range(5)]
        hp = [(_ts(i), 91.0) for i in range(5)]
        result = assess_noise_exposure_risk(
            env_audio_rows=env, headphone_audio_rows=hp, window=_WINDOW, now=_NOW
        )
        assert result.severity in {"high", "medium"}

    def test_supporting_metrics_present(self):
        env = [(_ts(i), 85.0) for i in range(10)]
        result = assess_noise_exposure_risk(env_audio_rows=env, window=_WINDOW, now=_NOW)
        assert "max_db_30d" in result.supporting_metrics
