from __future__ import annotations

from dataclasses import dataclass

from health_log.analysis.detectors.illness.constants import (
    MIN_CONFIRMED_DAYS_FOR_SIGNAL,
    RECENT_DAYS,
    SEVERITY_HIGH_MIN,
    SEVERITY_LOW_MIN,
    SEVERITY_MEDIUM_MIN,
    TEMP_STABLE_DELTA_THRESHOLD,
    TEMP_STABLE_PENALTY,
)
from health_log.analysis.detectors.illness.features import TrendSnapshot


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(slots=True)
class ScoreResult:
    score: float
    confidence: float
    severity: str


def calculate_score(snapshot: TrendSnapshot) -> ScoreResult:
    hr_component = _clamp01((snapshot.recent_rest_hr - snapshot.baseline_rest_hr) / 15.0)
    hrv_component = _clamp01(
        (snapshot.baseline_hrv - snapshot.recent_hrv) / snapshot.baseline_hrv / 0.35
    )
    resp_component = 0.0
    if (
        snapshot.baseline_rr is not None
        and snapshot.recent_rr is not None
        and snapshot.baseline_rr > 0
    ):
        resp_component = _clamp01(
            (snapshot.recent_rr - snapshot.baseline_rr) / snapshot.baseline_rr / 0.20
        )
    consistency_component = snapshot.confirmed_days / RECENT_DAYS

    if snapshot.wrist_temp_delta is not None and snapshot.wrist_temp_delta >= 0.1:
        # Температура запястья — самый прямой физиологический сигнал.
        # Активируем при повышении ≥0.1°C (включительно): порог согласован
        # с messages.py, где при том же значении формируется фраза
        # "температура запястья выше baseline".
        # +0.1°C → начало вклада; +0.6°C → максимальный компонент.
        temp_component = _clamp01((snapshot.wrist_temp_delta - 0.1) / 0.5)
        score = min(
            1.0,
            temp_component * 0.30
            + hr_component * 0.25
            + hrv_component * 0.25
            + resp_component * 0.10
            + consistency_component * 0.10,
        )
    else:
        score = min(
            1.0,
            hr_component * 0.40
            + hrv_component * 0.30
            + resp_component * 0.15
            + consistency_component * 0.15,
        )

    # Wrist-temp veto: when Watch 8+ data is available AND skin temperature is
    # not elevated, an inflammatory process is physiologically unlikely.
    # Downweight the score so HR/HRV-only signals from sleep deprivation,
    # alcohol or post-training overreach do not surface as illness alerts.
    # We deliberately apply this only when we have enough nights to compute a
    # delta at all (delta is not None) and the delta is below the threshold.
    if (
        snapshot.wrist_temp_delta is not None
        and snapshot.wrist_temp_delta <= TEMP_STABLE_DELTA_THRESHOLD
    ):
        score *= TEMP_STABLE_PENALTY

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

    # Hard gate against transient noise: at least N of the last RECENT_DAYS
    # must independently flag (>=2 simultaneous channel breaches) before we
    # report anything but "none". A single bad night or two should not be
    # surfaced to the user as an illness signal — that has been the dominant
    # source of false positives in production.
    if snapshot.confirmed_days < MIN_CONFIRMED_DAYS_FOR_SIGNAL:
        severity = "none"
    elif score >= SEVERITY_HIGH_MIN:
        severity = "high"
    elif score >= SEVERITY_MEDIUM_MIN:
        severity = "medium"
    elif score >= SEVERITY_LOW_MIN:
        severity = "low"
    else:
        severity = "none"

    return ScoreResult(score=score, confidence=confidence, severity=severity)
