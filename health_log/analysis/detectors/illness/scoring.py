from __future__ import annotations

from dataclasses import dataclass

from health_log.analysis.detectors.illness.constants import RECENT_DAYS
from health_log.analysis.detectors.illness.features import TrendSnapshot


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(slots=True)
class ScoreResult:
    score: float
    confidence: float
    severity: str


def calculate_score(snapshot: TrendSnapshot) -> ScoreResult:
    hr_component = _clamp01((snapshot.recent_rest_hr - snapshot.baseline_rest_hr) / 10.0)
    hrv_component = _clamp01((snapshot.baseline_hrv - snapshot.recent_hrv) / snapshot.baseline_hrv / 0.35)
    resp_component = 0.0
    if snapshot.baseline_rr is not None and snapshot.recent_rr is not None and snapshot.baseline_rr > 0:
        resp_component = _clamp01(
            (snapshot.recent_rr - snapshot.baseline_rr) / snapshot.baseline_rr / 0.20
        )
    consistency_component = snapshot.confirmed_days / RECENT_DAYS

    score = min(
        1.0,
        hr_component * 0.4
        + hrv_component * 0.3
        + resp_component * 0.15
        + consistency_component * 0.15,
    )

    valid_days_component = min(1.0, snapshot.valid_days_count / 63.0)
    hr_density_component = min(1.0, snapshot.total_hr_points / 500.0)
    hrv_density_component = min(1.0, snapshot.total_hrv_points / 180.0)
    sleep_coverage_component = min(1.0, snapshot.days_with_sleep / 45.0)
    confidence = (
        0.35 * valid_days_component
        + 0.25 * hr_density_component
        + 0.2 * hrv_density_component
        + 0.2 * sleep_coverage_component
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
