from __future__ import annotations

from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import (
    build_score_confidence_interpretation,
    resting_like_median,
    split_baseline_recent,
    to_points,
)


def assess_illness_onset_risk(
    heart_rows: Iterable[tuple],
    hrv_rows: Iterable[tuple],
    *,
    window: TimeWindow,
) -> RiskAssessment:
    heart = to_points(heart_rows)
    hrv = to_points(hrv_rows)

    if len(heart) < 20 or len(hrv) < 10:
        return RiskAssessment(
            condition="illness_onset_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных для интерпретации уровня риска и достоверности сигнала.",
            summary="Недостаточно данных по пульсу в покое и HRV для оценки раннего риска болезни.",
            recommendation="Продолжай регулярно носить часы, особенно ночью, чтобы собрать больше данных для тренда.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    heart_base, heart_recent = split_baseline_recent(heart)
    hrv_base, hrv_recent = split_baseline_recent(hrv)

    base_rest_hr = resting_like_median([p.value for p in heart_base])
    recent_rest_hr = resting_like_median([p.value for p in heart_recent])
    base_hrv = median([p.value for p in hrv_base]) if hrv_base else None
    recent_hrv = median([p.value for p in hrv_recent]) if hrv_recent else None

    if (
        base_rest_hr is None
        or recent_rest_hr is None
        or base_hrv is None
        or recent_hrv is None
        or base_hrv == 0
    ):
        return RiskAssessment(
            condition="illness_onset_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных для интерпретации уровня риска и достоверности сигнала.",
            summary="Не удалось устойчиво посчитать тренды пульса в покое и HRV.",
            recommendation="Проверь полноту синхронизации и повтори анализ позже.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    base_rest_hr_value = float(base_rest_hr)
    recent_rest_hr_value = float(recent_rest_hr)
    base_hrv_value = float(base_hrv)
    recent_hrv_value = float(recent_hrv)

    hr_increase = recent_rest_hr_value - base_rest_hr_value
    hrv_drop_pct = max(0.0, (base_hrv_value - recent_hrv_value) / base_hrv_value)

    score = min(
        1.0,
        max(0.0, min(1.0, hr_increase / 10.0)) * 0.5
        + max(0.0, min(1.0, hrv_drop_pct / 0.35)) * 0.5,
    )
    confidence = min(1.0, (len(heart) / 180.0) * 0.6 + (len(hrv) / 90.0) * 0.4)

    if score >= 0.7:
        severity = "high"
    elif score >= 0.4:
        severity = "medium"
    elif score > 0:
        severity = "low"
    else:
        severity = "none"

    summary = (
        f"Оценка по тренду: пульс в состоянии покоя вырос на {hr_increase:.1f} уд/мин; "
        f"HRV изменился на {((recent_hrv_value - base_hrv_value) / base_hrv_value) * 100:.1f}%. "
        "Такое сочетание может быть ранним признаком начала простуды или другого воспалительного процесса."
    )
    recommendation = (
        "Если сигнал растет 2-3 дня подряд и есть симптомы (слабость, ломота, температура), "
        "снизь нагрузку, следи за самочувствием и при необходимости обратись к врачу."
    )

    return RiskAssessment(
        condition="illness_onset_risk",
        window=window,
        score=round(score, 3),
        confidence=round(confidence, 3),
        severity=severity,
        interpretation=build_score_confidence_interpretation(score, confidence),
        summary=summary,
        recommendation=recommendation,
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
    )
