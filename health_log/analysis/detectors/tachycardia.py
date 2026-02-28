from __future__ import annotations

from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import build_score_confidence_interpretation, to_points


def assess_tachycardia_risk(
    heart_rows: Iterable[tuple],
    *,
    window: TimeWindow,
) -> RiskAssessment:
    heart = to_points(heart_rows)

    if not heart:
        return RiskAssessment(
            condition="tachycardia_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных для интерпретации уровня риска и достоверности сигнала.",
            summary="Недостаточно данных пульса для оценки.",
            recommendation="Проверь синхронизацию данных пульса из Apple Health.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    episodes = 0
    for point in heart:
        if point.value >= 100:
            episodes += 1

    score = min(1.0, episodes * 0.03)
    confidence = min(1.0, len(heart) / 300.0)

    if score >= 0.7:
        severity = "high"
    elif score >= 0.35:
        severity = "medium"
    elif score > 0:
        severity = "low"
    else:
        severity = "none"

    summary = f"Обнаружено случаев пульса >= 100 уд/мин: {episodes}."
    recommendation = (
        "Если такие эпизоды частые или есть симптомы (одышка, слабость, боль в груди), "
        "обратись к кардиологу."
    )

    return RiskAssessment(
        condition="tachycardia_risk",
        window=window,
        score=round(score, 3),
        confidence=round(confidence, 3),
        severity=severity,
        interpretation=build_score_confidence_interpretation(score, confidence),
        summary=summary,
        recommendation=recommendation,
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
    )
