from __future__ import annotations

from datetime import datetime
from health_log.utils import utcnow
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.detectors.menstrual_cycle.constants import MIN_PERIOD_STARTS
from health_log.analysis.detectors.menstrual_cycle.features import (
    build_cycle_lengths,
    build_menstrual_model,
    build_period_starts,
    extract_flow_days,
)
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import EventPoint

_MIN_INTERMENSTRUAL_EVENTS = 1
_TEMP_SHIFT_THRESHOLD = 0.2
_TEMP_SHIFT_CONSECUTIVE_NIGHTS = 3


def assess_menstrual_irregularity_risk(
    menstrual_rows: Iterable[tuple[datetime, object]],
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    if window == TimeWindow.NIGHT:
        return RiskAssessment(
            condition="menstrual_irregularity_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="not_applicable",
            interpretation="Для оценки нерегулярности цикла нужны данные за несколько месяцев.",
            summary="Окно 'ночь' не подходит для оценки регулярности цикла.",
            recommendation="Смотри оценку по окнам 'week' или 'month'.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    now = now or utcnow()
    menstrual_list = list(menstrual_rows)
    flow_days = extract_flow_days(menstrual_list)
    starts = build_period_starts(flow_days)

    if len(starts) < MIN_PERIOD_STARTS:
        return RiskAssessment(
            condition="menstrual_irregularity_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных для оценки регулярности цикла.",
            summary=f"Найдено {len(starts)} начал менструации (нужно ≥{MIN_PERIOD_STARTS}).",
            recommendation="Продолжай синхронизацию данных цикла в Apple Health.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"period_starts_count": len(starts)},
        )

    cycle_lengths = build_cycle_lengths(starts)
    if len(cycle_lengths) < 3:
        return RiskAssessment(
            condition="menstrual_irregularity_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно валидных интервалов цикла для анализа.",
            summary="Нет достаточного числа полных циклов для оценки вариабельности.",
            recommendation="Продолжай синхронизацию данных цикла.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"period_starts_count": len(starts), "valid_intervals": len(cycle_lengths)},
        )

    last_six = cycle_lengths[-6:]
    variability = max(last_six) - min(last_six)
    valid_intervals_in_last_six = len(last_six)

    if variability > 14 or valid_intervals_in_last_six < 3:
        severity = "high"
        score_base = 0.85
    elif variability > 10:
        severity = "medium"
        score_base = 0.65
    elif variability > 7:
        severity = "low"
        score_base = 0.35
    else:
        return RiskAssessment(
            condition="menstrual_irregularity_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(cycle_lengths) / 6.0), 3),
            severity="none",
            interpretation="Вариабельность длины цикла в пределах нормы.",
            summary=f"Цикл регулярный: вариабельность {variability} дней (последние {len(last_six)} циклов).",
            recommendation="Продолжай наблюдение.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={
                "variability_days": variability,
                "cycle_count": len(cycle_lengths),
                "median_cycle_length": int(median(last_six)),
            },
        )

    score = round(score_base, 3)
    confidence = round(min(1.0, len(cycle_lengths) / 6.0) * 0.7 + (0.3 if valid_intervals_in_last_six >= 5 else 0.1), 3)

    return RiskAssessment(
        condition="menstrual_irregularity_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Вариабельность длины цикла может быть нормой или признаком гормональных нарушений. "
            "Необходима консультация гинеколога."
        ),
        summary=(
            f"Подозрение на нерегулярность цикла: вариабельность {variability} дней "
            f"(последние {len(last_six)} циклов, медиана {int(median(last_six))} дней)."
        ),
        recommendation="Обратись к гинекологу для оценки регулярности цикла и гормонального фона.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "variability_days": variability,
            "cycle_count": len(cycle_lengths),
            "min_cycle_length": min(last_six),
            "max_cycle_length": max(last_six),
            "median_cycle_length": int(median(last_six)),
        },
    )


def _count_prolonged_periods(menstrual_list: list, threshold_days: int = 8) -> int:
    flow_days = extract_flow_days(menstrual_list)
    starts = build_period_starts(flow_days)
    if len(starts) < 2:
        return 0

    count = 0
    for i in range(len(starts) - 1):
        period_end = starts[i + 1]
        period_start = starts[i]
        days_in_period = 0
        for day in flow_days:
            if period_start <= day < period_end:
                days_in_period += 1
        if days_in_period > threshold_days:
            count += 1

    last_start = starts[-1]
    last_period_days = sum(1 for d in flow_days if d >= last_start)
    if last_period_days > threshold_days:
        count += 1

    return count


def assess_atypical_menstrual_bleeding_risk(
    intermenstrual_event_rows: Iterable[tuple[datetime, object]] | None = None,
    menstrual_rows: Iterable[tuple[datetime, object]] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    if window == TimeWindow.NIGHT:
        return RiskAssessment(
            condition="atypical_menstrual_bleeding_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="not_applicable",
            interpretation="Для оценки атипичных кровотечений нужны данные за несколько циклов.",
            summary="Окно 'ночь' не подходит для оценки атипичных кровотечений.",
            recommendation="Смотри оценку по окнам 'week' или 'month'.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    now = now or utcnow()
    intermenstrual_events = list(intermenstrual_event_rows or [])
    menstrual_list = list(menstrual_rows or [])

    n_intermenstrual = len(intermenstrual_events)
    n_prolonged = _count_prolonged_periods(menstrual_list) if menstrual_list else 0

    if n_intermenstrual == 0 and n_prolonged == 0:
        return RiskAssessment(
            condition="atypical_menstrual_bleeding_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Нет данных о межменструальных кровотечениях или затяжных периодах.",
            summary="Данных для оценки атипичных кровотечений недостаточно.",
            recommendation="При возникновении нетипичных кровотечений отметь их в Apple Health или дневнике цикла.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"intermenstrual_events": 0, "prolonged_period_events": 0},
        )

    if n_prolonged >= 2:
        flow_days = extract_flow_days(menstrual_list)
        starts = build_period_starts(flow_days)
        if len(starts) >= 2:
            severity = "high"
            score = 0.85
        else:
            severity = "medium"
            score = 0.65
    elif n_intermenstrual >= 2:
        severity = "medium"
        score = 0.60
    else:
        severity = "low"
        score = 0.35

    confidence = round(
        min(1.0, (n_intermenstrual + n_prolonged) / 5.0) * 0.8
        + (0.2 if menstrual_list else 0.0),
        3,
    )

    summary_parts = []
    if n_intermenstrual > 0:
        summary_parts.append(f"{n_intermenstrual} межменструальных кровотечений")
    if n_prolonged > 0:
        summary_parts.append(f"{n_prolonged} удлинённых периодов (>8 дней)")

    return RiskAssessment(
        condition="atypical_menstrual_bleeding_risk",
        window=window,
        score=round(score, 3),
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Атипичные кровотечения могут указывать на различные гинекологические состояния. "
            "Требуется консультация гинеколога."
        ),
        summary="Подозрение на атипичные кровотечения: " + ", ".join(summary_parts) + ".",
        recommendation=(
            "Обратись к гинекологу для обследования. "
            "Межменструальные кровотечения и затяжные периоды требуют клинической оценки."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "intermenstrual_events": n_intermenstrual,
            "prolonged_period_events": n_prolonged,
        },
    )


def _detect_postovulation_temp_shift(
    temp_points: list[EventPoint],
    ovulation_date_ordinal: int,
    *,
    shift_threshold: float = _TEMP_SHIFT_THRESHOLD,
    consecutive_nights: int = _TEMP_SHIFT_CONSECUTIVE_NIGHTS,
) -> bool:
    post_ovulation = sorted(
        [p for p in temp_points if p.timestamp.toordinal() > ovulation_date_ordinal],
        key=lambda p: p.timestamp,
    )
    if len(post_ovulation) < consecutive_nights:
        return False

    by_day: dict[int, list[float]] = {}
    for p in post_ovulation:
        by_day.setdefault(p.timestamp.toordinal(), []).append(p.value)

    pre_ovulation = [p.value for p in temp_points if p.timestamp.toordinal() <= ovulation_date_ordinal]
    if not pre_ovulation:
        return False

    baseline = median(pre_ovulation) if pre_ovulation else None
    if baseline is None:
        return False

    sorted_days = sorted(by_day.keys())
    consecutive_count = 0
    for day in sorted_days:
        day_temp = median(by_day[day])
        if day_temp >= baseline + shift_threshold:
            consecutive_count += 1
            if consecutive_count >= consecutive_nights:
                return True
        else:
            consecutive_count = 0
    return False


def assess_menstrual_start_forecast_with_temp(
    menstrual_rows: Iterable[tuple[datetime, object]],
    wrist_temp_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    from health_log.analysis.detectors.menstrual_cycle.detector import (
        assess_menstrual_cycle_start_forecast,
    )

    now = now or utcnow()
    menstrual_list = list(menstrual_rows)

    base_result = assess_menstrual_cycle_start_forecast(
        menstrual_list, window=window, now=now
    )

    if base_result.severity in {"unknown", "not_applicable"} or wrist_temp_rows is None:
        return RiskAssessment(
            condition="menstrual_start_forecast_with_temp",
            window=base_result.window,
            score=base_result.score,
            confidence=base_result.confidence,
            severity=base_result.severity,
            interpretation=base_result.interpretation,
            summary=base_result.summary,
            recommendation=base_result.recommendation,
            clinical_safety_note=base_result.clinical_safety_note,
            supporting_metrics={"temp_shift_detected": False},
        )

    from health_log.analysis.utils import to_points as _to_points
    temp_points = _to_points(wrist_temp_rows)

    model = build_menstrual_model(menstrual_list, now=now)
    if model is None:
        return RiskAssessment(
            condition="menstrual_start_forecast_with_temp",
            window=base_result.window,
            score=base_result.score,
            confidence=base_result.confidence,
            severity=base_result.severity,
            interpretation=base_result.interpretation,
            summary=base_result.summary,
            recommendation=base_result.recommendation,
            clinical_safety_note=base_result.clinical_safety_note,
            supporting_metrics={"temp_shift_detected": False},
        )

    from datetime import timedelta as _timedelta
    ovulation_ordinal = (model.predicted_next - _timedelta(days=14)).toordinal()
    temp_shift_detected = _detect_postovulation_temp_shift(temp_points, ovulation_ordinal)

    boosted_confidence = min(1.0, base_result.confidence + (0.15 if temp_shift_detected else 0.0))

    summary = base_result.summary
    if temp_shift_detected:
        summary += " Температурный сдвиг после овуляции подтверждён (+0.2°C на ≥3 ночи)."

    return RiskAssessment(
        condition="menstrual_start_forecast_with_temp",
        window=window,
        score=round(base_result.score, 3),
        confidence=round(boosted_confidence, 3),
        severity=base_result.severity,
        interpretation=base_result.interpretation,
        summary=summary,
        recommendation=base_result.recommendation,
        clinical_safety_note=base_result.clinical_safety_note,
        supporting_metrics={"temp_shift_detected": temp_shift_detected},
    )


def assess_ovulation_forecast_with_temp(
    menstrual_rows: Iterable[tuple[datetime, object]],
    wrist_temp_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    from health_log.analysis.detectors.menstrual_cycle.detector import (
        assess_ovulation_window_forecast,
    )

    now = now or utcnow()
    menstrual_list = list(menstrual_rows)

    base_result = assess_ovulation_window_forecast(menstrual_list, window=window, now=now)

    if base_result.severity in {"unknown", "not_applicable"} or wrist_temp_rows is None:
        return RiskAssessment(
            condition="ovulation_forecast_with_temp",
            window=base_result.window,
            score=base_result.score,
            confidence=base_result.confidence,
            severity=base_result.severity,
            interpretation=base_result.interpretation,
            summary=base_result.summary,
            recommendation=base_result.recommendation,
            clinical_safety_note=base_result.clinical_safety_note,
            supporting_metrics={"temp_confirmed_ovulation": False},
        )

    from health_log.analysis.utils import to_points as _to_points
    temp_points = _to_points(wrist_temp_rows)

    model = build_menstrual_model(menstrual_list, now=now)
    if model is None:
        return RiskAssessment(
            condition="ovulation_forecast_with_temp",
            window=base_result.window,
            score=base_result.score,
            confidence=base_result.confidence,
            severity=base_result.severity,
            interpretation=base_result.interpretation,
            summary=base_result.summary,
            recommendation=base_result.recommendation,
            clinical_safety_note=base_result.clinical_safety_note,
            supporting_metrics={"temp_confirmed_ovulation": False},
        )

    from datetime import timedelta as _timedelta
    ovulation_ordinal = (model.predicted_next - _timedelta(days=14)).toordinal()
    temp_confirmed = _detect_postovulation_temp_shift(temp_points, ovulation_ordinal)

    boosted_confidence = min(1.0, base_result.confidence + (0.15 if temp_confirmed else 0.0))
    summary = base_result.summary
    if temp_confirmed:
        summary += " Температурный сдвиг ретроспективно подтверждает предполагаемое окно овуляции."

    return RiskAssessment(
        condition="ovulation_forecast_with_temp",
        window=window,
        score=round(base_result.score, 3),
        confidence=round(boosted_confidence, 3),
        severity=base_result.severity,
        interpretation=base_result.interpretation,
        summary=summary,
        recommendation=base_result.recommendation,
        clinical_safety_note=base_result.clinical_safety_note,
        supporting_metrics={"temp_confirmed_ovulation": temp_confirmed},
    )
