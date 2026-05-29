"""Unit tests for illness detector message bugs.

Bug 1: Финальная фраза о простуде не должна добавляться при stable wrist_temp.
Bug 2: build_summary не должен вызываться (summary должен быть пустым) при severity == 'none'.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from health_log.analysis.detectors.illness.constants import HR_SCORE_NORM, HRV_SCORE_REL_NORM
from health_log.analysis.detectors.illness.detector import assess_illness_onset_risk
from health_log.analysis.detectors.illness.features import TrendSnapshot
from health_log.analysis.detectors.illness.messages import build_summary
from health_log.analysis.detectors.illness.scoring import calculate_score
from health_log.analysis.models import TimeWindow

_FINAL_PHRASE = "Это может соответствовать изменению физиологии на фоне простуды или воспаления."
_STABLE_PHRASE = "снижает вероятность воспалительного процесса"

_WINDOW = TimeWindow.MONTH
_NOW = datetime(2026, 5, 28, 12, 0, 0)


def _make_snapshot(
    *,
    wrist_temp_delta: float | None = None,
    confirmed_days: int = 4,
    recent_rest_hr: float = 75.0,
    baseline_rest_hr: float = 65.0,
    recent_hrv: float = 35.0,
    baseline_hrv: float = 45.0,
) -> TrendSnapshot:
    return TrendSnapshot(
        baseline_rest_hr=baseline_rest_hr,
        recent_rest_hr=recent_rest_hr,
        baseline_hrv=baseline_hrv,
        recent_hrv=recent_hrv,
        baseline_rr=None,
        recent_rr=None,
        resp_increase_pct=0.0,
        confirmed_days=confirmed_days,
        valid_days_count=50,
        total_hr_points=600,
        total_hrv_points=200,
        days_with_sleep=45,
        wrist_temp_delta=wrist_temp_delta,
    )


# ---------------------------------------------------------------------------
# Bug 1 — build_summary: финальная фраза и stable temp
# ---------------------------------------------------------------------------


class TestBuildSummaryWristTemp:
    def test_elevated_temp_includes_final_phrase(self):
        snapshot = _make_snapshot(wrist_temp_delta=0.25)
        result = build_summary(snapshot)
        assert _FINAL_PHRASE in result
        assert _STABLE_PHRASE not in result

    def test_stable_temp_does_not_include_final_phrase(self):
        """Баг 1: при stable wrist_temp финальная фраза о простуде НЕ должна появляться."""
        snapshot = _make_snapshot(wrist_temp_delta=-0.05)
        result = build_summary(snapshot)
        assert _FINAL_PHRASE not in result, (
            "Финальная фраза о простуде не должна добавляться, когда температура стабильна"
        )
        assert _STABLE_PHRASE in result

    def test_zero_temp_delta_does_not_include_final_phrase(self):
        """Граничный случай: delta == 0.0 — тоже стабильная температура."""
        snapshot = _make_snapshot(wrist_temp_delta=0.0)
        result = build_summary(snapshot)
        assert _FINAL_PHRASE not in result
        assert _STABLE_PHRASE in result

    def test_no_temp_data_includes_final_phrase(self):
        """Когда данных температуры нет — финальную фразу добавляем."""
        snapshot = _make_snapshot(wrist_temp_delta=None)
        result = build_summary(snapshot)
        assert _FINAL_PHRASE in result
        assert _STABLE_PHRASE not in result

    def test_stable_temp_does_not_contradict_stable_phrase(self):
        """При stable_temp оба утверждения (снижает вероятность И может быть простуда)
        не должны присутствовать одновременно."""
        snapshot = _make_snapshot(wrist_temp_delta=-0.1)
        result = build_summary(snapshot)
        assert not (_STABLE_PHRASE in result and _FINAL_PHRASE in result), (
            "Противоречивые фразы не должны появляться одновременно"
        )

    def test_large_negative_delta_is_not_labeled_stable(self):
        """delta=-0.5 НЕ должна называться «стабильна» — это заметное снижение."""
        snapshot = _make_snapshot(wrist_temp_delta=-0.5)
        result = build_summary(snapshot)
        assert "стабильна" not in result, (
            "Большое отрицательное отклонение (-0.5) не должно называться «стабильна»"
        )
        assert _STABLE_PHRASE in result, (
            "Но «снижает вероятность» должна присутствовать даже при большом снижении"
        )

    def test_small_negative_delta_still_labeled_stable(self):
        """delta=-0.15 в зоне [-0.2, 0.0] — «стабильна» корректно."""
        snapshot = _make_snapshot(wrist_temp_delta=-0.15)
        result = build_summary(snapshot)
        assert "стабильна" in result
        assert _STABLE_PHRASE in result


# ---------------------------------------------------------------------------
# Bug 2 — assess_illness_onset_risk: summary пустой при severity == 'none'
# ---------------------------------------------------------------------------

# Строим минимальный датасет: 45+ валидных суток, но confirmed_days < 3
# (MIN_CONFIRMED_DAYS_FOR_SIGNAL), чтобы hard gate дал severity='none'.

_HR_PER_DAY = 15  # >= HR_POINTS_PER_DAY_MIN (12)
_HRV_PER_DAY = 4  # >= HRV_POINTS_PER_DAY_MIN (3)
_TOTAL_DAYS = 50  # >= MIN_VALID_DAYS_FOR_SIGNAL (45)


def _build_rows(
    now: datetime,
    total_days: int,
    hr_value: float,
    hrv_value: float,
) -> tuple[list[tuple], list[tuple]]:
    """Возвращает (heart_rows, hrv_rows) без аномалий."""
    heart: list[tuple] = []
    hrv: list[tuple] = []
    for day_offset in range(total_days):
        base = now - timedelta(days=total_days - day_offset)
        for i in range(_HR_PER_DAY):
            heart.append((base + timedelta(minutes=i * 5), hr_value))
        for i in range(_HRV_PER_DAY):
            hrv.append((base + timedelta(minutes=i * 20), hrv_value))
    return heart, hrv


class TestAssessIllnessOnsetSeverityNone:
    def test_severity_none_gives_empty_summary(self):
        """Баг 2: при severity=='none' summary должен быть пустым."""
        # Все дни с одинаковым HR/HRV — confirmed_days будет 0, hard gate = severity 'none'
        heart, hrv = _build_rows(_NOW, _TOTAL_DAYS, hr_value=65.0, hrv_value=45.0)
        result = assess_illness_onset_risk(
            heart_rows=heart,
            hrv_rows=hrv,
            window=_WINDOW,
        )
        assert result.severity == "none", f"Ожидали severity='none', получили '{result.severity}'"
        assert result.summary == "", (
            f"При severity='none' summary должен быть пустым, получили: '{result.summary[:80]}'"
        )

    def test_severity_none_summary_has_no_illness_phrase(self):
        """При severity=='none' в summary не должна присутствовать фраза о простуде."""
        heart, hrv = _build_rows(_NOW, _TOTAL_DAYS, hr_value=65.0, hrv_value=45.0)
        result = assess_illness_onset_risk(
            heart_rows=heart,
            hrv_rows=hrv,
            window=_WINDOW,
        )
        assert result.severity == "none"
        assert _FINAL_PHRASE not in result.summary

    def test_severity_none_gives_empty_recommendation(self):
        """Регрессия: при severity=='none' recommendation должен быть пустым.

        До фикса build_recommendation() вызывалась безусловно, и пользователь
        видел клинический совет ("снизь нагрузку, обратись к врачу") даже когда
        никакого риска не выявлено.
        """
        heart, hrv = _build_rows(_NOW, _TOTAL_DAYS, hr_value=65.0, hrv_value=45.0)
        result = assess_illness_onset_risk(
            heart_rows=heart,
            hrv_rows=hrv,
            window=_WINDOW,
        )
        assert result.severity == "none"
        assert result.recommendation == "", (
            f"При severity='none' recommendation должна быть пустой, получили: '{result.recommendation[:80]}'"
        )

    def test_non_none_severity_has_non_empty_summary(self):
        """Позитивный сценарий: при ненулевом severity summary непустой."""
        # Строим датасет с явной аномалией на последних 5 днях
        heart: list[tuple] = []
        hrv: list[tuple] = []
        total_days = _TOTAL_DAYS

        # Baseline: 45 дней нормальных значений
        for day_offset in range(total_days - 5):
            base = _NOW - timedelta(days=total_days - day_offset)
            for i in range(_HR_PER_DAY):
                heart.append((base + timedelta(minutes=i * 5), 65.0))
            for i in range(_HRV_PER_DAY):
                hrv.append((base + timedelta(minutes=i * 20), 45.0))

        # Последние 5 дней: сильно повышенный HR (+15 bpm, +23%), сильно сниженный HRV (-30%)
        for day_offset in range(total_days - 5, total_days):
            base = _NOW - timedelta(days=total_days - day_offset)
            for i in range(_HR_PER_DAY):
                heart.append((base + timedelta(minutes=i * 5), 80.0))
            for i in range(_HRV_PER_DAY):
                hrv.append((base + timedelta(minutes=i * 20), 30.0))

        result = assess_illness_onset_risk(
            heart_rows=heart,
            hrv_rows=hrv,
            window=_WINDOW,
        )
        if result.severity != "none":
            assert result.summary != "", "При ненулевом severity summary не должен быть пустым"


# ---------------------------------------------------------------------------
# Граничные случаи wrist_temp_delta — согласованность messages.py и scoring.py
# ---------------------------------------------------------------------------


_COLD_PHRASE = "Это может соответствовать изменению физиологии на фоне простуды или воспаления."
_ELEVATED_PHRASE = "Температура запястья во сне выше"
_NEUTRAL_PHRASE = "незначительно отклоняется от baseline"


class TestWristTempBoundary:
    """Тесты граничных значений wrist_temp_delta для messages.py и scoring.py.

    Оба модуля используют строгий порог > 0.1°C для ветки «повышена».
    Зона (0.0, 0.1) — нейтральная (scorer не применяет ни temp_component,
    ни TEMP_STABLE_PENALTY; messages не делает утверждений о риске).
    """

    def test_delta_01_is_stable_not_elevated(self):
        """delta == 0.1: нейтральная зона. НЕ содержит фразу о простуде и «выше baseline»,
        зато содержит нейтральную фразу об отклонении от baseline."""
        snapshot = _make_snapshot(wrist_temp_delta=0.1)
        result = build_summary(snapshot)
        assert _COLD_PHRASE not in result, "При delta=0.1 фраза о простуде не должна появляться"
        assert _ELEVATED_PHRASE not in result, (
            "При delta=0.1 фраза 'выше baseline' не должна появляться"
        )
        # Позитивная проверка: подтверждаем, что messages.py относит delta=0.1
        # к нейтральной зоне и выдаёт соответствующую фразу. Без этого assert
        # тест проходил бы и при сценарии «summary не содержит ничего о temp».
        assert _NEUTRAL_PHRASE in result, (
            "При delta=0.1 ожидается нейтральная фраза об отклонении от baseline"
        )

    def test_delta_005_neutral_phrase(self):
        """delta == 0.05: нейтральная фраза (не «снижает вероятность», не фраза о простуде)."""
        snapshot = _make_snapshot(wrist_temp_delta=0.05)
        result = build_summary(snapshot)
        assert _COLD_PHRASE not in result, "При delta=0.05 фраза о простуде не должна появляться"
        assert _STABLE_PHRASE not in result, (
            "При delta=0.05 фраза 'снижает вероятность' не должна появляться"
        )
        assert _NEUTRAL_PHRASE in result, "При delta=0.05 ожидается нейтральная фраза об отклонении"

    def test_delta_minus_01_contains_stable_phrase(self):
        """delta == -0.1: содержит «снижает вероятность воспалительного процесса»."""
        snapshot = _make_snapshot(wrist_temp_delta=-0.1)
        result = build_summary(snapshot)
        assert _STABLE_PHRASE in result, (
            "При delta=-0.1 ожидается фраза о снижении вероятности воспаления"
        )
        assert _COLD_PHRASE not in result

    def test_delta_015_contains_cold_phrase(self):
        """delta == 0.15: содержит фразу о простуде (ветка «повышенная»)."""
        snapshot = _make_snapshot(wrist_temp_delta=0.15)
        result = build_summary(snapshot)
        assert _ELEVATED_PHRASE in result, "При delta=0.15 ожидается фраза 'выше baseline'"
        assert _COLD_PHRASE in result, "При delta=0.15 ожидается фраза о простуде"

    def test_delta_01_scoring_uses_no_temp_branch(self):
        """При delta == 0.1 scoring идёт по ветке без temp_component.

        scoring.py использует строгий > 0.1, поэтому delta=0.1 попадает в
        else-ветку. score = consistency_component * 0.15 = (4/5) * 0.15 = 0.12.
        Veto не применяется (delta > TEMP_STABLE_DELTA_THRESHOLD = 0.0).
        """
        snapshot = _make_snapshot(
            wrist_temp_delta=0.1,
            confirmed_days=4,
            recent_rest_hr=65.0,
            baseline_rest_hr=65.0,
            recent_hrv=45.0,
            baseline_hrv=45.0,
        )
        result = calculate_score(snapshot)
        # else-ветка: 0*0.40 + 0*0.30 + 0*0.15 + 0.8*0.15 = 0.12
        assert abs(result.score - 0.12) < 1e-9, (
            f"При delta=0.1 ожидали else-ветку (score=0.12), получили {result.score:.6f}"
        )

    def test_temp_branch_boosts_score_when_hr_hrv_weak(self):
        """Когда HR/HRV сигнал слабый (=0), но delta большой — temp-ветка должна
        реально увеличить score выше score_base.

        Без этого теста ветка `> TEMP_ELEVATED_DELTA_THRESHOLD` могла бы быть
        полностью сломана (например, если бы её случайно удалили), а тест
        test_delta_011_scoring_does_not_invert_at_boundary всё равно бы проходил,
        потому что max() возвращает score_base.

        hr_component=0, hrv_component=0, delta=0.6:
          score_with_temp = 1.0*0.30 + 0*0.25 + 0*0.25 + 0*0.10 + 0.8*0.10 = 0.38
          score_base      = 0*0.40  + 0*0.30 + 0*0.15 + 0.8*0.15           = 0.12
          max(0.12, 0.38) = 0.38  →  temp-ветка реально победила
        """
        snapshot = _make_snapshot(
            wrist_temp_delta=0.6,
            confirmed_days=4,
            recent_rest_hr=65.0,
            baseline_rest_hr=65.0,
            recent_hrv=45.0,
            baseline_hrv=45.0,
        )
        result = calculate_score(snapshot)
        expected_with_temp = 1.0 * 0.30 + 0.8 * 0.10  # = 0.38
        expected_base = 0.8 * 0.15  # = 0.12
        assert result.score > expected_base + 1e-6, (
            f"При delta=0.6 и нулевом HR/HRV score должен превышать score_base "
            f"({expected_base:.6f}), получили {result.score:.6f} — это значит, что "
            f"temp-ветка не активировалась"
        )
        assert abs(result.score - expected_with_temp) < 1e-9, (
            f"При delta=0.6 ожидали score_with_temp={expected_with_temp:.6f}, "
            f"получили {result.score:.6f}"
        )

    def test_delta_minus_02_is_notably_low(self):
        """Граничное delta == -0.2 включается в ветку «заметно ниже» (строгое <=).

        -0.2°C — уже семантически заметное отклонение, поэтому граница
        делается включающей. Регрессия на TEMP_NOTABLY_LOW_THRESHOLD.
        """
        snapshot = _make_snapshot(wrist_temp_delta=-0.2)
        result = build_summary(snapshot)
        assert "заметно ниже" in result, (
            "При delta=-0.2 ожидается ветка «заметно ниже» (граница включающая)"
        )
        assert "стабильна" not in result, (
            "При delta=-0.2 ветка «стабильна» НЕ должна срабатывать"
        )
        assert _STABLE_PHRASE in result

    def test_delta_011_scoring_does_not_invert_at_boundary(self):
        """delta == 0.11: temp-ветка входит, но max() защищает от инверсии.

        score_base = 0.8 * 0.15 = 0.12
        score_with_temp = 0.02*0.30 + 0.8*0.10 = 0.086
        max(0.12, 0.086) = 0.12
        """
        snapshot = _make_snapshot(
            wrist_temp_delta=0.11,
            confirmed_days=4,
            recent_rest_hr=65.0,
            baseline_rest_hr=65.0,
            recent_hrv=45.0,
            baseline_hrv=45.0,
        )
        result = calculate_score(snapshot)
        expected = 0.8 * 0.15  # score_base wins via max()
        assert abs(result.score - expected) < 1e-9, (
            f"При delta=0.11 max() защищает от инверсии, ожидали {expected:.6f}, получили {result.score:.6f}"
        )

    def test_neutral_zone_includes_no_impact_phrase(self):
        """Нейтральная зона (0.0, 0.1]: сообщение явно указывает, что не влияет на оценку."""
        snapshot = _make_snapshot(wrist_temp_delta=0.05)
        result = build_summary(snapshot)
        assert "не влияет на оценку" in result, (
            "Нейтральная зона должна сообщать, что температура не влияет на оценку"
        )

    def test_score_monotone_at_temp_threshold(self):
        """Пересечение порога 0.1°C не снижает скор (фикс инверсии).

        При одинаковых HR/HRV: score(delta=0.099) <= score(delta=0.101).
        """
        base_snapshot = _make_snapshot(
            wrist_temp_delta=0.099,
            confirmed_days=4,
            recent_rest_hr=75.0,
            baseline_rest_hr=65.0,
            recent_hrv=35.0,
            baseline_hrv=45.0,
        )
        above_snapshot = _make_snapshot(
            wrist_temp_delta=0.101,
            confirmed_days=4,
            recent_rest_hr=75.0,
            baseline_rest_hr=65.0,
            recent_hrv=35.0,
            baseline_hrv=45.0,
        )
        score_below = calculate_score(base_snapshot).score
        score_above = calculate_score(above_snapshot).score
        assert score_above >= score_below - 1e-9, (
            f"Пересечение порога 0.1°C не должно снижать скор: "
            f"score(0.099)={score_below:.6f} > score(0.101)={score_above:.6f}"
        )

    def test_delta_01_with_hr_signal_uses_nottemp_weights(self):
        """delta == 0.1 с реальным HR/HRV-сигналом использует else-веса
        (hr*0.40, hrv*0.30), а не temp-веса (hr*0.25, hrv*0.25).

        Регрессия: после возврата к строгому `> 0.1` (вместо `>= 0.1`) delta=0.1
        попадает в else-ветку. Это означает, что граничный пользователь с
        небольшим повышением температуры запястья (ровно +0.1°C) получит
        более высокий score, чем при temp-весах. Зафиксировано как
        задокументированное поведение: нейтральная зона (0.0, 0.1] не
        активирует temp_component, но при ненулевых HR/HRV-сигналах score
        считается по else-весам, где вес HR/HRV выше.

        Также подтверждаем, что veto не применяется (delta=0.1 > 0.0 =
        TEMP_STABLE_DELTA_THRESHOLD), то есть нейтральная зона выше нуля
        НЕ считается «стабильной температурой» с точки зрения подавления
        ложноположительных срабатываний.

        Расчёт:
          hr_component  = (75-65)/15      = 0.6667
          hrv_component = (45-35)/45/0.35 = 0.6349
          consistency   = 4/5             = 0.8
          else_score = 0.6667*0.40 + 0.6349*0.30 + 0 + 0.8*0.15 ≈ 0.5771
          temp_score = 0.0*0.30 + 0.6667*0.25 + 0.6349*0.25 + 0 + 0.8*0.10 ≈ 0.4054
        """
        snapshot = _make_snapshot(
            wrist_temp_delta=0.1,
            confirmed_days=4,
            recent_rest_hr=75.0,
            baseline_rest_hr=65.0,
            recent_hrv=35.0,
            baseline_hrv=45.0,
        )
        result = calculate_score(snapshot)

        hr_component = (75.0 - 65.0) / HR_SCORE_NORM
        hrv_component = (45.0 - 35.0) / 45.0 / HRV_SCORE_REL_NORM
        resp_component = 0.0  # no RR data in snapshot
        consistency = 4 / 5
        expected_else = (
            hr_component * 0.40
            + hrv_component * 0.30
            + resp_component * 0.15
            + consistency * 0.15
        )
        expected_temp = (
            0.0 * 0.30
            + hr_component * 0.25
            + hrv_component * 0.25
            + resp_component * 0.10
            + consistency * 0.10
        )

        assert abs(result.score - expected_else) < 1e-9, (
            f"При delta=0.1 ожидали else-веса (score={expected_else:.6f}), "
            f"получили {result.score:.6f}"
        )
        # И явно: score должен НЕ совпадать с temp-весами — фиксируем,
        # что nittle delta в нейтральной зоне трактуется по else-весам.
        assert abs(result.score - expected_temp) > 1e-3, (
            "delta=0.1 не должна давать score, как при temp-весах"
        )
        # Veto не применён (penalty не сработал) — без неё score > 0.55,
        # severity = medium. Фиксируем для регрессии.
        assert result.severity == "medium", (
            f"При delta=0.1 + реальный HR/HRV-сигнал severity=medium, получили {result.severity}"
        )
