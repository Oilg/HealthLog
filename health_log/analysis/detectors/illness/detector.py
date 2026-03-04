from __future__ import annotations

from datetime import datetime
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.detectors.illness.features import (
    build_trend_snapshot,
    trend_days_available,
)
from health_log.analysis.detectors.illness.messages import (
    build_insufficient_data_summary,
    build_recommendation,
    build_summary,
)
from health_log.analysis.detectors.illness.scoring import calculate_score
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import build_score_confidence_interpretation, to_points


def assess_illness_onset_risk(
    heart_rows: Iterable[tuple],
    hrv_rows: Iterable[tuple],
    respiratory_rows: Iterable[tuple] | None = None,
    sleep_rows: Iterable[tuple[datetime, datetime]] | None = None,
    *,
    window: TimeWindow,
) -> RiskAssessment:
    if window == TimeWindow.NIGHT:
        return RiskAssessment(
            condition="illness_onset_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="not_applicable",
            interpretation="Для этого сигнала нужно минимум несколько дней данных, а не только одна ночь.",
            summary="Окно 'ночь' не подходит для оценки раннего риска болезни по тренду метрик.",
            recommendation="Смотри оценки по окнам 'week' и 'month'.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    heart = to_points(heart_rows)
    hrv = to_points(hrv_rows)
    respiratory = to_points(respiratory_rows or [])

    snapshot = build_trend_snapshot(
        heart=heart,
        hrv=hrv,
        respiratory=respiratory,
        sleep_rows=sleep_rows or [],
    )

    if snapshot is None:
        days_available = trend_days_available(heart, hrv)
        return RiskAssessment(
            condition="illness_onset_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных для интерпретации уровня риска и достоверности сигнала.",
            summary=build_insufficient_data_summary(days_available),
            recommendation=(
                "Продолжай синхронизацию данных. Сигнал станет надежнее после накопления 63+ дней HR и HRV."
            ),
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    score_result = calculate_score(snapshot)
    return RiskAssessment(
        condition="illness_onset_risk",
        window=window,
        score=round(score_result.score, 3),
        confidence=round(score_result.confidence, 3),
        severity=score_result.severity,
        interpretation=build_score_confidence_interpretation(score_result.score, score_result.confidence),
        summary=build_summary(snapshot),
        recommendation=build_recommendation(),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
    )
