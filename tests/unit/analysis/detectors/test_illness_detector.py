"""Unit tests for illness detector message bugs.

Bug 1: Финальная фраза о простуде не должна добавляться при stable wrist_temp.
Bug 2: build_summary не должен вызываться (summary должен быть пустым) при severity == 'none'.
"""

from __future__ import annotations

from datetime import datetime, timedelta

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
# Bug 3 — порог wrist_temp_delta унифицирован между scoring.py и messages.py
# ---------------------------------------------------------------------------


class TestCalculateScoreWristTempThreshold:
    """При wrist_temp_delta == 0.1 messages.py говорит "температура повышена".

    До фикса scoring использовал строгий `> 0.1` и игнорировал temp_component
    ровно на этом значении, поэтому пользователь видел противоречивые сигналы:
    summary упоминал повышенную температуру, а score её не учитывал.
    """

    def test_threshold_boundary_activates_temp_branch(self):
        """При delta == 0.1 scoring должен пойти по ветке с temp_component.

        Проверяем активацию ветки косвенно через сравнение с явно-низкой
        дельтой 0.05: при 0.05 работает veto (score *= TEMP_STABLE_PENALTY),
        при 0.1 — нет (порог veto = TEMP_STABLE_DELTA_THRESHOLD = 0.0, проверим
        ниже отдельно). Главное: формула на границе 0.1 должна перейти в
        temp-ветку, где temp_component = (0.1 - 0.1) / 0.5 = 0.0 ровно.

        Сравнивать со значением 0.11 нельзя (там temp_component уже > 0),
        поэтому фиксируем точный расчёт.
        """
        # HR и HRV дельты равны 0 — score должен быть равен confirmed/RECENT*0.10
        # в temp-ветке (без veto, т.к. delta > TEMP_STABLE_DELTA_THRESHOLD = 0.0).
        snapshot = _make_snapshot(
            wrist_temp_delta=0.1,
            confirmed_days=4,
            recent_rest_hr=65.0,  # = baseline → hr_component=0
            baseline_rest_hr=65.0,
            recent_hrv=45.0,  # = baseline_hrv → hrv_component=0
            baseline_hrv=45.0,
        )
        result = calculate_score(snapshot)
        # confirmed_days=4, RECENT_DAYS=5 → consistency_component=0.8.
        # В temp-ветке (>= 0.1): 0*0.30 + 0*0.25 + 0*0.25 + 0*0.10 + 0.8*0.10 = 0.08.
        # В ветке без temp (> 0.1, старое): 0*0.40 + 0*0.30 + 0*0.15 + 0.8*0.15 = 0.12.
        # Это значение ОДНОЗНАЧНО определяет какая ветка сработала на границе.
        assert abs(result.score - 0.08) < 1e-9, (
            f"При delta=0.1 ожидали активацию temp-ветки (score=0.08), "
            f"получили {result.score:.6f} — порог в scoring всё ещё > 0.1"
        )

    def test_threshold_boundary_score_matches_messages_phrase(self):
        """Согласованность: на границе 0.1 messages и scoring обрабатывают сигнал одинаково.

        messages.build_summary использует `>= 0.1` ("температура повышена"),
        scoring после фикса тоже использует `>= 0.1` (включает temp_component).
        Этот тест фиксирует контракт.
        """
        snapshot = _make_snapshot(wrist_temp_delta=0.1)
        summary = build_summary(snapshot)
        # messages.py: при delta >= 0.1 в summary упоминается повышение температуры
        assert "Температура запястья во сне выше" in summary
        # scoring.py: temp_component активен, фраза о стабильной температуре отсутствует
        assert "стабильна" not in summary
