from __future__ import annotations

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow


def _severity_from_score(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    if score > 0:
        return "low"
    return "none"


def _insufficient(condition: str, window: TimeWindow, n: int, what: str) -> RiskAssessment:
    return RiskAssessment(
        condition=condition,
        window=window,
        score=0.0,
        confidence=0.0,
        severity="unknown",
        interpretation=f"Недостаточно данных для оценки: {what}.",
        summary=f"Найдено {n} измерений — недостаточно для сигнала.",
        recommendation="Проверь синхронизацию данных в Apple Health.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={"measurements_count": n},
    )
