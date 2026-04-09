from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.detectors.menstrual_cycle.constants import MIN_PERIOD_STARTS, MIN_VALID_CYCLE_INTERVALS
from health_log.analysis.detectors.menstrual_cycle.features import (
    MenstrualModel,
    build_cycle_lengths,
    build_menstrual_model,
    build_period_starts,
    extract_flow_days,
)
from health_log.analysis.detectors.menstrual_cycle.messages import (
    CALENDAR_DISCLAIMER,
    build_insufficient_intervals_summary,
    build_insufficient_starts_summary,
)
from health_log.analysis.detectors.menstrual_cycle.scoring import (
    delay_score_and_severity,
    menstrual_confidence,
    score_menstrual_start,
)
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import build_score_confidence_interpretation


def _night_placeholder(condition: str) -> RiskAssessment:
    return RiskAssessment(
        condition=condition,
        window=TimeWindow.NIGHT,
        score=0.0,
        confidence=0.0,
        severity="not_applicable",
        interpretation="Для прогноза цикла нужны длинные периоды наблюдения.",
        summary="Окно 'ночь' не подходит для прогноза цикла.",
        recommendation="Смотри прогноз по окнам 'week' или 'month'.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
    )


def _insufficient(
    condition: str,
    window: TimeWindow,
    *,
    summary: str,
    interpretation: str = "Недостаточно истории для прогноза цикла.",
) -> RiskAssessment:
    return RiskAssessment(
        condition=condition,
        window=window,
        score=0.0,
        confidence=0.0,
        severity="unknown",
        interpretation=interpretation,
        summary=summary,
        recommendation="Продолжай синхронизацию данных цикла в Apple Health.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
    )


def _shared_model(
    menstrual_rows: Iterable[tuple[datetime, object]],
    *,
    now: datetime,
) -> tuple[MenstrualModel | None, str | None, int]:
    flow_days = extract_flow_days(menstrual_rows)
    starts = build_period_starts(flow_days)
    n_starts = len(starts)
    if n_starts < MIN_PERIOD_STARTS:
        return None, "starts", n_starts
    cycle_lengths = build_cycle_lengths(starts)
    if len(cycle_lengths) < MIN_VALID_CYCLE_INTERVALS:
        return None, "intervals", n_starts
    model = build_menstrual_model(menstrual_rows, now=now)
    if model is None:
        return None, "intervals", n_starts
    return model, None, n_starts


def assess_menstrual_cycle_start_forecast(
    menstrual_rows: Iterable[tuple[datetime, object]],
    *,
    window: TimeWindow,
    now: datetime,
) -> RiskAssessment:
    if window == TimeWindow.NIGHT:
        return _night_placeholder("menstrual_cycle_start_forecast")

    model, reason, n_starts = _shared_model(menstrual_rows, now=now)
    if reason == "starts":
        return _insufficient(
            "menstrual_cycle_start_forecast",
            window,
            summary=build_insufficient_starts_summary(n_starts),
        )
    if reason == "intervals" or model is None:
        return _insufficient(
            "menstrual_cycle_start_forecast",
            window,
            summary=build_insufficient_intervals_summary(),
        )

    sr = score_menstrual_start(model.days_to_next)
    conf = menstrual_confidence(model)
    summary = (
        f"Ожидаемое начало менструации: между {model.predicted_earliest.isoformat()} и "
        f"{model.predicted_latest.isoformat()}."
    )
    interpretation = (
        f"{CALENDAR_DISCLAIMER} {build_score_confidence_interpretation(sr.score, conf)}"
    )
    return RiskAssessment(
        condition="menstrual_cycle_start_forecast",
        window=window,
        score=round(sr.score, 3),
        confidence=round(conf, 3),
        severity=sr.severity,
        interpretation=interpretation,
        summary=summary,
        recommendation="При сильных болях, нерегулярности или сомнениях обратись к гинекологу.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
    )


def assess_menstrual_cycle_delay_risk(
    menstrual_rows: Iterable[tuple[datetime, object]],
    *,
    window: TimeWindow,
    now: datetime,
) -> RiskAssessment:
    if window == TimeWindow.NIGHT:
        return _night_placeholder("menstrual_cycle_delay_risk")

    model, reason, n_starts = _shared_model(menstrual_rows, now=now)
    if reason == "starts":
        return _insufficient(
            "menstrual_cycle_delay_risk",
            window,
            summary=build_insufficient_starts_summary(n_starts),
        )
    if reason == "intervals" or model is None:
        return _insufficient(
            "menstrual_cycle_delay_risk",
            window,
            summary=build_insufficient_intervals_summary(),
        )

    today = now.date()
    if today <= model.predicted_latest:
        return RiskAssessment(
            condition="menstrual_cycle_delay_risk",
            window=window,
            score=0.0,
            confidence=round(menstrual_confidence(model), 3),
            severity="none",
            interpretation=(
                f"{CALENDAR_DISCLAIMER} Текущие даты не выходят за верхнюю границу прогнозного окна."
            ),
            summary="Задержка менструации относительно прогноза сейчас не фиксируется.",
            recommendation="Продолжай наблюдение по календарному прогнозу.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    delay_days = (today - model.predicted_latest).days
    score, severity = delay_score_and_severity(delay_days)
    conf = menstrual_confidence(model)
    summary = f"Текущий цикл выходит за ожидаемые границы на {delay_days} дн."
    interpretation = f"{CALENDAR_DISCLAIMER} {build_score_confidence_interpretation(score, conf)}"
    return RiskAssessment(
        condition="menstrual_cycle_delay_risk",
        window=window,
        score=round(score, 3),
        confidence=round(conf, 3),
        severity=severity,
        interpretation=interpretation,
        summary=summary,
        recommendation="При длительной задержке или симптомах беременности/здоровья обратись к гинекологу.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
    )


def assess_ovulation_window_forecast(
    menstrual_rows: Iterable[tuple[datetime, object]],
    *,
    window: TimeWindow,
    now: datetime,
) -> RiskAssessment:
    if window == TimeWindow.NIGHT:
        return _night_placeholder("ovulation_window_forecast")

    model, reason, n_starts = _shared_model(menstrual_rows, now=now)
    if reason == "starts":
        return _insufficient(
            "ovulation_window_forecast",
            window,
            summary=build_insufficient_starts_summary(n_starts),
        )
    if reason == "intervals" or model is None:
        return _insufficient(
            "ovulation_window_forecast",
            window,
            summary=build_insufficient_intervals_summary(),
        )

    if model.variability > 10:
        return RiskAssessment(
            condition="ovulation_window_forecast",
            window=window,
            score=0.0,
            confidence=round(menstrual_confidence(model), 3),
            severity="none",
            interpretation=f"{CALENDAR_DISCLAIMER} Окно овуляции скрыто из‑за высокой вариабельности длины цикла.",
            summary="Вероятное окно овуляции не показывается: вариабельность цикла слишком высокая.",
            recommendation="Собери больше ровных циклов для более узкого прогноза.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    center = model.predicted_next - timedelta(days=14)
    ov_from = center - timedelta(days=model.band)
    ov_to = center + timedelta(days=model.band)
    conf = menstrual_confidence(model)
    summary = f"Вероятное окно овуляции: {ov_from.isoformat()}–{ov_to.isoformat()}."
    interpretation = (
        f"{CALENDAR_DISCLAIMER} Оценка ориентировочная; достоверность сигнала: {conf:.2f}."
    )
    return RiskAssessment(
        condition="ovulation_window_forecast",
        window=window,
        score=round(conf, 3),
        confidence=round(conf, 3),
        severity="low",
        interpretation=interpretation,
        summary=summary,
        recommendation="Используй только как ориентир; подтверждение возможно тестами овуляции у врача.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
    )
