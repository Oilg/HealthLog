from __future__ import annotations

from datetime import datetime, timedelta

from health_log.analysis.detectors.menstrual_cycle import (
    assess_atypical_menstrual_bleeding_risk,
    assess_menstrual_irregularity_risk,
    assess_menstrual_start_forecast_with_temp,
    assess_ovulation_forecast_with_temp,
)
from health_log.analysis.models import TimeWindow

_WINDOW = TimeWindow.MONTH
_NOW = datetime(2026, 3, 5, 10, 0, 0)


def _build_regular_cycle_rows(now: datetime, cycle_len: int = 28, n_cycles: int = 5) -> list[tuple[datetime, str]]:
    rows: list[tuple[datetime, str]] = []
    for cycle in range(n_cycles):
        start = now.date() - timedelta(days=cycle_len * (n_cycles - cycle))
        for day_offset in range(4):
            ts = datetime.combine(start + timedelta(days=day_offset), datetime.min.time())
            rows.append((ts, "HKCategoryValueMenstrualFlowMedium"))
    return rows


def _build_irregular_cycle_rows(now: datetime) -> list[tuple[datetime, str]]:
    lengths = [28, 35, 22, 30, 42]
    rows: list[tuple[datetime, str]] = []
    current = now.date() - timedelta(days=sum(lengths))
    for length in lengths:
        for day_offset in range(4):
            ts = datetime.combine(current + timedelta(days=day_offset), datetime.min.time())
            rows.append((ts, "HKCategoryValueMenstrualFlowMedium"))
        current += timedelta(days=length)
    return rows


class TestMenstrualIrregularityRisk:
    def test_night_window_returns_not_applicable(self):
        rows = _build_regular_cycle_rows(_NOW)
        result = assess_menstrual_irregularity_risk(rows, window=TimeWindow.NIGHT, now=_NOW)
        assert result.severity == "not_applicable"

    def test_insufficient_data_returns_unknown(self):
        rows = [(_NOW - timedelta(days=10), "HKCategoryValueMenstrualFlowMedium")]
        result = assess_menstrual_irregularity_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"
        assert result.score == 0.0

    def test_regular_cycle_returns_none(self):
        rows = _build_regular_cycle_rows(_NOW, cycle_len=28, n_cycles=6)
        result = assess_menstrual_irregularity_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "none"
        assert result.score == 0.0

    def test_irregular_cycle_returns_signal(self):
        rows = _build_irregular_cycle_rows(_NOW)
        result = assess_menstrual_irregularity_risk(rows, window=_WINDOW, now=_NOW)
        assert result.score > 0
        assert result.severity in {"low", "medium", "high"}

    def test_high_variability_returns_high(self):
        lengths = [28, 21, 35, 20, 38]
        rows: list[tuple[datetime, str]] = []
        current = _NOW.date() - timedelta(days=sum(lengths))
        for length in lengths:
            for day_offset in range(4):
                ts = datetime.combine(current + timedelta(days=day_offset), datetime.min.time())
                rows.append((ts, "HKCategoryValueMenstrualFlowMedium"))
            current += timedelta(days=length)
        result = assess_menstrual_irregularity_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity in {"medium", "high"}

    def test_supporting_metrics_present(self):
        rows = _build_irregular_cycle_rows(_NOW)
        result = assess_menstrual_irregularity_risk(rows, window=_WINDOW, now=_NOW)
        if result.severity not in {"unknown", "none"}:
            assert "variability_days" in result.supporting_metrics


class TestAtypicalMenstrualBleedingRisk:
    def test_night_window_returns_not_applicable(self):
        result = assess_atypical_menstrual_bleeding_risk(window=TimeWindow.NIGHT)
        assert result.severity == "not_applicable"

    def test_no_data_returns_unknown(self):
        result = assess_atypical_menstrual_bleeding_risk(window=_WINDOW)
        assert result.severity == "unknown"

    def test_one_intermenstrual_event_returns_low(self):
        events = [(_NOW - timedelta(days=10), "intermenstrual")]
        result = assess_atypical_menstrual_bleeding_risk(
            intermenstrual_event_rows=events, window=_WINDOW
        )
        assert result.severity == "low"
        assert result.score > 0

    def test_two_intermenstrual_events_returns_medium(self):
        events = [
            (_NOW - timedelta(days=40), "intermenstrual"),
            (_NOW - timedelta(days=10), "intermenstrual"),
        ]
        result = assess_atypical_menstrual_bleeding_risk(
            intermenstrual_event_rows=events, window=_WINDOW
        )
        assert result.severity in {"medium", "high"}

    def test_prolonged_periods_two_cycles_returns_high(self):
        rows: list[tuple[datetime, str]] = []
        cycle_len = 28
        for cycle in range(4):
            start = _NOW.date() - timedelta(days=cycle_len * (4 - cycle))
            for day_offset in range(10):
                ts = datetime.combine(start + timedelta(days=day_offset), datetime.min.time())
                rows.append((ts, "HKCategoryValueMenstrualFlowMedium"))
        result = assess_atypical_menstrual_bleeding_risk(
            menstrual_rows=rows,
            window=_WINDOW,
        )
        assert result.severity in {"medium", "high"}

    def test_recommendation_mentions_gynecologist(self):
        events = [(_NOW - timedelta(days=10), "event")]
        result = assess_atypical_menstrual_bleeding_risk(
            intermenstrual_event_rows=events, window=_WINDOW
        )
        assert "гинеколог" in result.recommendation.lower()


class TestMenstrualStartForecastWithTemp:
    def _build_wrist_temp(self, cycle_rows: list) -> list[tuple[datetime, float]]:
        temp_rows = []
        for i in range(25):
            d = _NOW - timedelta(days=i + 3)
            if i < 10:
                temp_rows.append((d, 36.3 + i * 0.02))
            else:
                temp_rows.append((d, 36.5))
        return temp_rows

    def test_returns_correct_condition(self):
        cycle = _build_regular_cycle_rows(_NOW)
        temp = self._build_wrist_temp(cycle)
        result = assess_menstrual_start_forecast_with_temp(cycle, temp, window=_WINDOW, now=_NOW)
        assert result.condition == "menstrual_start_forecast_with_temp"

    def test_insufficient_data_propagates_unknown(self):
        result = assess_menstrual_start_forecast_with_temp([], window=_WINDOW, now=_NOW)
        assert result.severity in {"unknown", "not_applicable"}

    def test_temp_shift_boosts_confidence(self):
        cycle = _build_regular_cycle_rows(_NOW)
        temp_no_shift = [(_NOW - timedelta(days=i), 36.5) for i in range(30)]
        temp_with_shift = [(_NOW - timedelta(days=i), 36.5) for i in range(14, 30)]
        predicted_ovulation = _NOW - timedelta(days=14)
        temp_with_shift += [
            (predicted_ovulation + timedelta(days=i), 36.72) for i in range(1, 5)
        ]
        r_no = assess_menstrual_start_forecast_with_temp(cycle, temp_no_shift, window=_WINDOW, now=_NOW)
        r_yes = assess_menstrual_start_forecast_with_temp(cycle, temp_with_shift, window=_WINDOW, now=_NOW)
        assert r_yes.confidence >= r_no.confidence


class TestOvulationForecastWithTemp:
    def test_returns_correct_condition(self):
        cycle = _build_regular_cycle_rows(_NOW)
        temp = [(_NOW - timedelta(days=i), 36.5) for i in range(30)]
        result = assess_ovulation_forecast_with_temp(cycle, temp, window=_WINDOW, now=_NOW)
        assert result.condition == "ovulation_forecast_with_temp"

    def test_temp_confirmed_in_supporting_metrics(self):
        cycle = _build_regular_cycle_rows(_NOW)
        temp = [(_NOW - timedelta(days=i), 36.5) for i in range(30)]
        result = assess_ovulation_forecast_with_temp(cycle, temp, window=_WINDOW, now=_NOW)
        assert "temp_confirmed_ovulation" in result.supporting_metrics

    def test_no_temp_data_propagates_base_result(self):
        cycle = _build_regular_cycle_rows(_NOW)
        result = assess_ovulation_forecast_with_temp(cycle, None, window=_WINDOW, now=_NOW)
        assert result.condition == "ovulation_forecast_with_temp"
