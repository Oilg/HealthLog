from __future__ import annotations

from dataclasses import dataclass

from health_log.analysis.detectors.illness.constants import MIN_DAYS_FOR_TREND, RECENT_DAYS
from health_log.analysis.detectors.illness.features import TrendSnapshot


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(slots=True)
class ScoreResult:
    score: float
    confidence: float
    severity: str


def calculate_score(snapshot: TrendSnapshot) -> ScoreResult:
    hr_component = _clamp01(snapshot.hr_increase / 10.0)
    hrv_component = _clamp01(snapshot.hrv_drop_pct / 0.35)
    resp_component = _clamp01(snapshot.resp_increase_pct / 0.2)
    consistency_component = snapshot.confirmed_days / RECENT_DAYS

    score = min(
        1.0,
        hr_component * 0.4
        + hrv_component * 0.3
        + resp_component * 0.15
        + snapshot.sleep_disruption * 0.05
        + consistency_component * 0.1,
    )
    confidence = min(
        1.0,
        (len(snapshot.selected_days) / MIN_DAYS_FOR_TREND) * 0.55
        + (snapshot.heart_points_count / 400.0) * 0.25
        + (snapshot.hrv_points_count / 200.0) * 0.2,
    )

    if score >= 0.7:
        severity = "high"
    elif score >= 0.4:
        severity = "medium"
    elif score > 0:
        severity = "low"
    else:
        severity = "none"

    return ScoreResult(score=score, confidence=confidence, severity=severity)
