from __future__ import annotations

from dataclasses import dataclass

from health_log.analysis.detectors.menstrual_cycle.features import MenstrualModel


@dataclass(slots=True)
class StartScoreResult:
    score: float
    severity: str


def score_menstrual_start(days_to_next: int) -> StartScoreResult:
    # Negative days_to_next means the predicted start is already overdue;
    # this case belongs to the delay_risk signal, not the start forecast.
    if days_to_next < 0:
        return StartScoreResult(score=0.0, severity="none")
    if days_to_next <= 2:
        return StartScoreResult(score=0.9, severity="high")
    if days_to_next <= 5:
        return StartScoreResult(score=0.75, severity="medium")
    if days_to_next <= 8:
        return StartScoreResult(score=0.55, severity="medium")
    return StartScoreResult(score=0.25, severity="low")


def menstrual_confidence(model: MenstrualModel) -> float:
    cycle_count = len(model.cycle_lengths)
    cycle_count_component = min(1.0, cycle_count / 6.0)
    variability_component = max(0.0, 1.0 - model.variability / 12.0)
    recency_component = 1.0 if model.last_cycle_start_age_days <= 45 else 0.5
    return min(
        1.0,
        0.45 * cycle_count_component + 0.4 * variability_component + 0.15 * recency_component,
    )


def delay_score_and_severity(delay_days: int) -> tuple[float, str]:
    score = min(1.0, delay_days / 10.0)
    if delay_days >= 8:
        return score, "high"
    if delay_days >= 4:
        return score, "medium"
    return score, "low"
