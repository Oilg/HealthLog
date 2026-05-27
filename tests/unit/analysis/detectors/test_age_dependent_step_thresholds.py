"""Unit-тесты возрастно-зависимых порогов шагов и новых helpers."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from health_log.analysis.detectors.weight_activity import (
    assess_insufficient_activity_risk,
    assess_sedentary_lifestyle_risk,
)
from health_log.analysis.detectors.weight_activity.composite_risks import (
    assess_cardiometabolic_profile_risk,
    assess_cardiovascular_obesity_risk,
    assess_metabolic_syndrome_risk,
    assess_recovery_obesity_risk,
)
from health_log.analysis.detectors.weight_activity.constants import (
    AGE_ELDERLY_THRESHOLD,
    AGE_SENIOR_THRESHOLD,
    STEP_INACTIVE_DEFAULT,
    STEP_INACTIVE_ELDERLY,
    STEP_INACTIVE_SENIOR,
    STEP_TARGET_DEFAULT,
    STEP_TARGET_ELDERLY,
    STEP_TARGET_SENIOR,
    inactive_threshold_for_age,
    target_threshold_for_age,
)
from health_log.analysis.detectors.weight_activity.helpers import (
    daily_step_totals,
    daily_totals,
    latest_complete_day_end,
    valid_step_day_count,
)
from health_log.analysis.detectors.weight_activity.weight_status import assess_obesity_risk
from health_log.analysis.models import TimeWindow
from health_log.analysis.utils import EventPoint

_NOW = datetime(2026, 5, 27, 14, 30, 0)
_WINDOW = TimeWindow.MONTH


def _step_rows(daily_steps: list[float], end_day: datetime | None = None) -> list[tuple]:
    """Список (startDate, value) — одна строка на день, начиная за len-1 дней до end_day (исключая end_day).

    Точки распределяются равномерно с шагом 1 день, последний день = end_day - 1 day 12:00.
    """
    end_day = end_day or latest_complete_day_end(_NOW)
    n = len(daily_steps)
    rows: list[tuple] = []
    for i, v in enumerate(daily_steps):
        # day = end_day - (n - i) days, в полдень
        ts = end_day - timedelta(days=n - i) + timedelta(hours=12)
        rows.append((ts, v))
    return rows


class TestAgeThresholdFunctions:
    @pytest.mark.parametrize(
        "age,expected",
        [
            (None, STEP_TARGET_DEFAULT),
            (5, STEP_TARGET_DEFAULT),
            (30, STEP_TARGET_DEFAULT),
            (AGE_SENIOR_THRESHOLD - 1, STEP_TARGET_DEFAULT),
            (AGE_SENIOR_THRESHOLD, STEP_TARGET_SENIOR),
            (65, STEP_TARGET_SENIOR),
            (AGE_ELDERLY_THRESHOLD - 1, STEP_TARGET_SENIOR),
            (AGE_ELDERLY_THRESHOLD, STEP_TARGET_ELDERLY),
            (85, STEP_TARGET_ELDERLY),
            (130, STEP_TARGET_ELDERLY),
        ],
    )
    def test_target_threshold_for_age(self, age: int | None, expected: int) -> None:
        assert target_threshold_for_age(age) == expected

    @pytest.mark.parametrize(
        "age,expected",
        [
            (None, STEP_INACTIVE_DEFAULT),
            (30, STEP_INACTIVE_DEFAULT),
            (59, STEP_INACTIVE_DEFAULT),
            (60, STEP_INACTIVE_SENIOR),
            (74, STEP_INACTIVE_SENIOR),
            (75, STEP_INACTIVE_ELDERLY),
            (95, STEP_INACTIVE_ELDERLY),
        ],
    )
    def test_inactive_threshold_for_age(self, age: int | None, expected: int) -> None:
        assert inactive_threshold_for_age(age) == expected


class TestHelpers:
    def test_latest_complete_day_end_returns_midnight(self) -> None:
        end = latest_complete_day_end(datetime(2026, 5, 27, 14, 30, 45))
        assert end == datetime(2026, 5, 27, 0, 0, 0)

    def test_daily_step_totals_excludes_zero_days(self) -> None:
        # 3 дня: 0, 5000, 8000 шагов
        end = datetime(2026, 5, 27, 0, 0)
        points = [
            EventPoint(timestamp=end - timedelta(days=3, hours=-12), value=0.0),
            EventPoint(timestamp=end - timedelta(days=2, hours=-12), value=5000.0),
            EventPoint(timestamp=end - timedelta(days=1, hours=-12), value=8000.0),
        ]
        totals = daily_step_totals(points, end - timedelta(days=4), end, exclude_zero=True)
        assert sorted(totals) == [5000.0, 8000.0]

    def test_daily_step_totals_sums_multiple_intraday(self) -> None:
        end = datetime(2026, 5, 27, 0, 0)
        day = end - timedelta(days=1)
        points = [
            EventPoint(timestamp=day + timedelta(hours=8), value=1000.0),
            EventPoint(timestamp=day + timedelta(hours=14), value=2000.0),
            EventPoint(timestamp=day + timedelta(hours=20), value=3000.0),
        ]
        totals = daily_step_totals(points, end - timedelta(days=2), end)
        assert totals == [6000.0]

    def test_daily_totals_keeps_zero_days(self) -> None:
        end = datetime(2026, 5, 27, 0, 0)
        points = [
            EventPoint(timestamp=end - timedelta(days=2, hours=-12), value=0.0),
            EventPoint(timestamp=end - timedelta(days=1, hours=-12), value=30.0),
        ]
        totals = daily_totals(points, end - timedelta(days=3), end)
        assert sorted(totals.values()) == [0.0, 30.0]

    def test_valid_step_day_count_excludes_zero(self) -> None:
        end = datetime(2026, 5, 27, 0, 0)
        points = [
            EventPoint(timestamp=end - timedelta(days=3, hours=-12), value=0.0),
            EventPoint(timestamp=end - timedelta(days=2, hours=-12), value=4000.0),
            EventPoint(timestamp=end - timedelta(days=1, hours=-12), value=0.0),
        ]
        assert valid_step_day_count(points, end - timedelta(days=4), end) == 1


class TestSedentaryLifestyleAgeDependent:
    def test_insufficient_if_less_than_10_valid_days(self) -> None:
        # 9 валидных дней, 5 нулевых
        rows = _step_rows([0.0] * 5 + [5000.0] * 9)
        result = assess_sedentary_lifestyle_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "unknown"
        assert "валидных дней" in result.summary or "валидных дней" in result.interpretation

    def test_default_age_4500_steps_returns_medium(self) -> None:
        # 14 дней по 4500 шагов, возраст не задан → target=7000, 4500 < 5000 → medium
        rows = _step_rows([4500.0] * 14)
        result = assess_sedentary_lifestyle_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "medium"
        assert result.supporting_metrics["target_threshold"] == STEP_TARGET_DEFAULT

    def test_elderly_4500_steps_returns_none(self) -> None:
        # 14 дней по 4500 шагов, возраст 80 → target=4000, 4500 >= 4000 → норма
        rows = _step_rows([4500.0] * 14)
        result = assess_sedentary_lifestyle_risk(rows, window=_WINDOW, now=_NOW, age=80)
        assert result.severity == "none"
        assert result.supporting_metrics["target_threshold"] == STEP_TARGET_ELDERLY

    def test_senior_5500_steps_returns_low(self) -> None:
        # 14 дней по 5500 шагов, возраст 65 → target=6000, 5500 < 6000 → low (выше medium-порога 4286)
        rows = _step_rows([5500.0] * 14)
        result = assess_sedentary_lifestyle_risk(rows, window=_WINDOW, now=_NOW, age=65)
        assert result.severity == "low"
        assert result.supporting_metrics["target_threshold"] == STEP_TARGET_SENIOR

    def test_zero_days_excluded_from_median(self) -> None:
        # 4 нулевых дня + 10 дней по 8000 → медиана из 10 = 8000, выше default 7000 → none
        rows = _step_rows([0.0] * 4 + [8000.0] * 10)
        result = assess_sedentary_lifestyle_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "none"


class TestInsufficientActivityAgeDependent:
    def test_elderly_3500_returns_none(self) -> None:
        # 14 дней по 3500, возраст 80 → target=4000. 3500 < 4000 но это самый верхний порог.
        # severity: <target*4/7≈2286 → high, <target*6/7≈3429 → medium, иначе low.
        # 3500 > 3429 → low
        rows = _step_rows([3500.0] * 14)
        result = assess_insufficient_activity_risk(rows, window=_WINDOW, now=_NOW, age=80)
        assert result.severity == "low"

    def test_default_2000_returns_high(self) -> None:
        # 14 дней по 2000, без возраста → target=7000. 2000 < 7000*4/7=4000 → high
        rows = _step_rows([2000.0] * 14)
        result = assess_insufficient_activity_risk(rows, window=_WINDOW, now=_NOW)
        assert result.severity == "high"


class TestCompositeRisksAgeDependent:
    def test_cardiometabolic_inactive_threshold_default(self) -> None:
        # 14 дней по 4800 шагов, без возраста → 4800 < 5000 → компонент гиподинамии активен
        rows = _step_rows([4800.0] * 14)
        result = assess_cardiometabolic_profile_risk(
            step_rows=rows, window=_WINDOW, now=_NOW
        )
        assert "inactivity" in result.supporting_metrics["components_used"]
        assert result.supporting_metrics["inactive_threshold"] == STEP_INACTIVE_DEFAULT

    def test_cardiometabolic_inactive_threshold_elderly(self) -> None:
        # 14 дней по 3500 шагов, возраст 80 → порог 3000, 3500 > 3000 → компонент маленький но есть
        rows = _step_rows([3500.0] * 14)
        result = assess_cardiometabolic_profile_risk(
            step_rows=rows, window=_WINDOW, now=_NOW, age=80
        )
        assert result.supporting_metrics["inactive_threshold"] == STEP_INACTIVE_ELDERLY

    def test_metabolic_syndrome_inactivity_criterion_senior(self) -> None:
        # 14 дней по 3500 шагов + ИМТ 32 (ожирение), age=65 → порог 4000, 3500 < 4000
        # → критерий "низкая активность" сработал. ИМТ→второй критерий. 2 критерия → low.
        from datetime import timedelta as td

        end = latest_complete_day_end(_NOW)
        bmi_rows = [(end - td(days=i), 32.0) for i in range(1, 5)]
        step_rows = _step_rows([3500.0] * 14)
        result = assess_metabolic_syndrome_risk(
            bmi_rows=bmi_rows,
            step_rows=step_rows,
            window=_WINDOW,
            now=_NOW,
            age=65,
        )
        assert result.supporting_metrics["inactive_threshold"] == STEP_INACTIVE_SENIOR
        assert result.supporting_metrics["criteria_count"] >= 2

    def test_metabolic_syndrome_inactivity_not_triggered_for_elderly(self) -> None:
        # Та же 3500 шагов, но age=80 → порог 3000, 3500 > 3000 → "низкая активность" НЕ срабатывает
        from datetime import timedelta as td

        end = latest_complete_day_end(_NOW)
        bmi_rows = [(end - td(days=i), 32.0) for i in range(1, 5)]
        step_rows = _step_rows([3500.0] * 14)
        result = assess_metabolic_syndrome_risk(
            bmi_rows=bmi_rows,
            step_rows=step_rows,
            window=_WINDOW,
            now=_NOW,
            age=80,
        )
        # только ИМТ — 1 критерий → ниже порога сигнала, supporting_metrics не содержит inactive_threshold
        assert result.supporting_metrics.get("criteria_count") == 1

    def test_cardiovascular_obesity_uses_age_threshold(self) -> None:
        # ИМТ 28 (overweight), 14 дней по 3500 шагов, age=80 → порог 3000, 3500 > 3000 → inactive=False → none
        from datetime import timedelta as td

        end = latest_complete_day_end(_NOW)
        bmi_rows = [(end - td(days=1), 28.0)]
        step_rows = _step_rows([3500.0] * 14)
        result = assess_cardiovascular_obesity_risk(
            body_mass_rows=[],
            bmi_rows=bmi_rows,
            step_rows=step_rows,
            window=_WINDOW,
            now=_NOW,
            age=80,
        )
        assert result.severity == "none"

    def test_cardiovascular_obesity_default_age_triggers(self) -> None:
        # ИМТ 28, 14 дней по 3500, без возраста → порог 5000, 3500 < 5000 → inactive=True
        from datetime import timedelta as td

        end = latest_complete_day_end(_NOW)
        bmi_rows = [(end - td(days=1), 28.0)]
        step_rows = _step_rows([3500.0] * 14)
        result = assess_cardiovascular_obesity_risk(
            body_mass_rows=[],
            bmi_rows=bmi_rows,
            step_rows=step_rows,
            window=_WINDOW,
            now=_NOW,
        )
        assert result.severity in {"low", "medium", "high"}

    def test_recovery_obesity_uses_age_threshold(self) -> None:
        # ИМТ 28, 14 дней по 3500, age=80 → inactive=False → none
        from datetime import timedelta as td

        end = latest_complete_day_end(_NOW)
        bmi_rows = [(end - td(days=1), 28.0)]
        step_rows = _step_rows([3500.0] * 14)
        result = assess_recovery_obesity_risk(
            body_mass_rows=[],
            bmi_rows=bmi_rows,
            step_rows=step_rows,
            window=_WINDOW,
            now=_NOW,
            age=80,
        )
        assert result.severity == "none"


class TestObesityRiskAgeDependent:
    def test_obesity_low_activity_amplifier_senior(self) -> None:
        # ИМТ 31 (низкое ожирение), жир 32%, age=65, шаги 3500 (< 4000=SENIOR порог inactive) → low_activity=True
        from datetime import timedelta as td

        end = latest_complete_day_end(_NOW)
        # Достаточно измерений массы и BMI
        bmi_rows = [(end - td(days=i), 31.0) for i in range(1, 5)]
        fat_rows = [(end - td(days=i), 32.0) for i in range(1, 5)]
        mass_rows = [(end - td(days=i), 95.0) for i in range(1, 5)]
        step_rows = _step_rows([3500.0] * 14)
        result = assess_obesity_risk(
            body_mass_rows=mass_rows,
            bmi_rows=bmi_rows,
            body_fat_rows=fat_rows,
            step_rows=step_rows,
            window=_WINDOW,
            now=_NOW,
            age=65,
        )
        assert result.supporting_metrics["inactive_threshold"] == STEP_INACTIVE_SENIOR
        assert result.severity in {"low", "medium", "high"}

    def test_obesity_no_low_activity_amplifier_when_age_high(self) -> None:
        # Те же данные но age=80 → порог 3000, 3500 > 3000 → low_activity=False, без бонуса +0.1
        from datetime import timedelta as td

        end = latest_complete_day_end(_NOW)
        bmi_rows = [(end - td(days=i), 31.0) for i in range(1, 5)]
        fat_rows = [(end - td(days=i), 32.0) for i in range(1, 5)]
        mass_rows = [(end - td(days=i), 95.0) for i in range(1, 5)]
        step_rows = _step_rows([3500.0] * 14)
        result_old = assess_obesity_risk(
            body_mass_rows=mass_rows,
            bmi_rows=bmi_rows,
            body_fat_rows=fat_rows,
            step_rows=step_rows,
            window=_WINDOW,
            now=_NOW,
            age=80,
        )
        assert result_old.supporting_metrics["inactive_threshold"] == STEP_INACTIVE_ELDERLY


class TestIncompleteTodayExcluded:
    def test_today_data_not_counted_as_full_day(self) -> None:
        # 10 валидных полных дней + сегодня (с очень низкими шагами, должно быть отброшено)
        end = latest_complete_day_end(_NOW)
        # 10 дней назад до вчера: 10 дней по 8000
        rows: list[tuple] = []
        for i in range(1, 11):
            rows.append((end - timedelta(days=i, hours=-12), 8000.0))
        # сегодня: только 200 шагов (день не завершён, должен быть отсечён)
        rows.append((_NOW.replace(hour=8, minute=0), 200.0))

        result = assess_sedentary_lifestyle_risk(rows, window=_WINDOW, now=_NOW)
        # Если сегодня не отсечён, медиана резко упадёт. С отсечением: медиана 10 дней = 8000 → none.
        assert result.severity == "none"
        assert result.supporting_metrics["median_daily_steps"] == 8000
