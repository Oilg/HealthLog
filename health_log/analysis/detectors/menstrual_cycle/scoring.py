from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ScoreResult:
    score: float
    confidence: float
    severity: str
    interpretation: str


def calculate_score(days_to_next: int, variability: int, cycle_count: int) -> ScoreResult:
    if days_to_next < 0:
        score = 0.55
        severity = "medium"
        interpretation = "Прогноз указывает на возможную задержку цикла."
    elif days_to_next <= 3:
        score = 0.85
        severity = "high"
        interpretation = "Ожидается скорое начало цикла в ближайшие дни."
    elif days_to_next <= 7:
        score = 0.65
        severity = "medium"
        interpretation = "Начало цикла ожидается на этой неделе."
    else:
        score = 0.25
        severity = "low"
        interpretation = "До ожидаемого начала цикла еще есть время."

    confidence = min(1.0, 0.45 + (cycle_count / 8.0) * 0.35 + max(0.0, (12 - variability) / 12.0) * 0.2)
    return ScoreResult(score=score, confidence=confidence, severity=severity, interpretation=interpretation)
