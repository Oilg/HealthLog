from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.detectors.menstrual_cycle.constants import MIN_CYCLES_FOR_FORECAST
from health_log.analysis.detectors.menstrual_cycle.features import (
    MenstrualTrend,
    build_cycle_lengths,
    build_period_starts,
    extract_flow_days,
    variability_band,
    weighted_cycle_length,
)
from health_log.analysis.detectors.menstrual_cycle.messages import (
    build_insufficient_cycles_summary,
    build_recommendation,
    build_summary,
)
from health_log.analysis.detectors.menstrual_cycle.scoring import calculate_score
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import build_score_confidence_interpretation


def _build_trend(
    starts_count: int,
    cycle_lengths: list[int],
    *,
    last_start: date,
    now: datetime,
) -> MenstrualTrend:
    typical_cycle = int(round(weighted_cycle_length(cycle_lengths)))
    band = variability_band(cycle_lengths)
    predicted_next = last_start + timedelta(days=typical_cycle)
    predicted_earliest = predicted_next - timedelta(days=band)
    predicted_latest = predicted_next + timedelta(days=band)
    days_to_next = (predicted_next - now.date()).days

    ovulation_from = predicted_earliest - timedelta(days=16)
    ovulation_to = predicted_latest - timedelta(days=12)
    variability = max(cycle_lengths[-8:]) - min(cycle_lengths[-8:])

    return MenstrualTrend(
        starts_count=starts_count,
        cycle_lengths=cycle_lengths,
        typical_cycle=typical_cycle,
        predicted_earliest=predicted_earliest,
        predicted_latest=predicted_latest,
        ovulation_from=ovulation_from,
        ovulation_to=ovulation_to,
        days_to_next=days_to_next,
        variability=variability,
    )


def assess_menstrual_cycle_risk(
    menstrual_rows: Iterable[tuple[datetime, object]],
    *,
    window: TimeWindow,
    now: datetime,
) -> RiskAssessment:
    if window == TimeWindow.NIGHT:
        return RiskAssessment(
            condition="menstrual_cycle_forecast",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="not_applicable",
            interpretation="Для прогноза цикла нужны длинные периоды наблюдения.",
            summary="Окно 'ночь' не подходит для прогноза цикла.",
            recommendation="Смотри прогноз по окнам 'week' или 'month'.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    flow_days = extract_flow_days(menstrual_rows)
    starts = build_period_starts(flow_days)
    if len(starts) < MIN_CYCLES_FOR_FORECAST:
        return RiskAssessment(
            condition="menstrual_cycle_forecast",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно истории для прогноза цикла.",
            summary=build_insufficient_cycles_summary(len(starts)),
            recommendation="Продолжай синхронизацию данных цикла, прогноз станет точнее.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    cycle_lengths = build_cycle_lengths(starts)
    if len(cycle_lengths) < MIN_CYCLES_FOR_FORECAST:
        return RiskAssessment(
            condition="menstrual_cycle_forecast",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно качественной истории для прогноза цикла.",
            summary="Интервалы между циклами пока слишком нестабильны.",
            recommendation="Собери больше данных за следующие месяцы.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )
    trend = _build_trend(
        len(starts),
        cycle_lengths,
        last_start=starts[-1],
        now=now,
    )

    score_result = calculate_score(
        days_to_next=trend.days_to_next,
        variability=trend.variability,
        cycle_count=len(trend.cycle_lengths),
    )
    return RiskAssessment(
        condition="menstrual_cycle_forecast",
        window=window,
        score=round(score_result.score, 3),
        confidence=round(score_result.confidence, 3),
        severity=score_result.severity,
        interpretation=(
            f"{score_result.interpretation} "
            f"{build_score_confidence_interpretation(score_result.score, score_result.confidence)}"
        ),
        summary=build_summary(trend),
        recommendation=build_recommendation(),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
    )
