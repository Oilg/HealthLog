from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, SignalEvidence, TimeWindow
from health_log.analysis.utils import (
    build_score_confidence_interpretation,
    nearest_value,
    to_points,
)


def _in_sleep_segments(ts: datetime, segments: list[tuple[datetime, datetime]]) -> bool:
    for start, end in segments:
        if start <= ts <= end:
            return True
    return False


def build_sleep_apnea_event_rows(
    respiratory_rows: Iterable[tuple],
    heart_rows: Iterable[tuple],
    hrv_rows: Iterable[tuple],
    sleep_segments: list[tuple[datetime, datetime]] | None = None,
    *,
    detected_by: str = "rule_engine_v1",
) -> list[dict[str, object]]:
    respiratory = to_points(respiratory_rows)
    heart = to_points(heart_rows)
    hrv = to_points(hrv_rows)
    segments = sleep_segments or []

    if segments:
        respiratory = [p for p in respiratory if _in_sleep_segments(p.timestamp, segments)]
        heart = [p for p in heart if _in_sleep_segments(p.timestamp, segments)]
        hrv = [p for p in hrv if _in_sleep_segments(p.timestamp, segments)]

    if len(respiratory) < 2:
        return []

    heart_baseline = median([p.value for p in heart]) if heart else None
    hrv_baseline = median([p.value for p in hrv]) if hrv else None

    events: list[dict[str, object]] = []
    for idx in range(1, len(respiratory)):
        prev_point = respiratory[idx - 1]
        current = respiratory[idx]
        if current.value >= 10:
            continue

        duration = (current.timestamp - prev_point.timestamp).total_seconds()
        if duration < 10:
            continue

        heart_near = nearest_value(heart, current.timestamp, max_seconds=120)
        hrv_near = nearest_value(hrv, current.timestamp, max_seconds=120)

        respiratory_drop = None
        if idx >= 10:
            prev_window = [respiratory[i].value for i in range(max(0, idx - 10), idx)]
            baseline_resp = median(prev_window) if prev_window else None
            if baseline_resp is not None:
                respiratory_drop = max(0.0, baseline_resp - current.value)

        heart_spike = None
        if heart_near is not None and heart_baseline is not None:
            heart_spike = heart_near - heart_baseline

        hrv_change = None
        if hrv_near is not None and hrv_baseline is not None:
            hrv_change = hrv_near - hrv_baseline

        severity = "mild"
        if (heart_spike is not None and heart_spike >= 20) or (respiratory_drop is not None and respiratory_drop >= 4):
            severity = "moderate"
        if (heart_spike is not None and heart_spike >= 30) and (hrv_change is not None and hrv_change <= -10):
            severity = "severe"

        events.append(
            {
                "start_time": prev_point.timestamp,
                "end_time": current.timestamp,
                "respiratory_rate_drop": respiratory_drop,
                "heart_rate_spike": heart_spike,
                "hrv_change": hrv_change,
                "severity": severity,
                "detected_by": detected_by,
            }
        )

    return events


def assess_sleep_apnea_risk(
    respiratory_rows: Iterable[tuple],
    heart_rows: Iterable[tuple],
    hrv_rows: Iterable[tuple],
    sleep_segments: list[tuple[datetime, datetime]] | None = None,
    *,
    window: TimeWindow,
) -> RiskAssessment:
    respiratory = to_points(respiratory_rows)
    heart = to_points(heart_rows)
    hrv = to_points(hrv_rows)
    segments = sleep_segments or []

    if segments:
        respiratory = [p for p in respiratory if _in_sleep_segments(p.timestamp, segments)]
        heart = [p for p in heart if _in_sleep_segments(p.timestamp, segments)]
        hrv = [p for p in hrv if _in_sleep_segments(p.timestamp, segments)]

    evidence = SignalEvidence(data_points=len(respiratory))

    if not respiratory:
        return RiskAssessment(
            condition="sleep_apnea_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных для интерпретации уровня риска и достоверности сигнала.",
            summary="Недостаточно данных дыхания для оценки.",
            recommendation="Проверь, что Apple Watch носится во время сна и данные синхронизируются.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    baseline_hr = median([p.value for p in heart]) if heart else None
    baseline_hrv = median([p.value for p in hrv]) if hrv else None

    for point in respiratory:
        if point.value < 10:
            evidence.low_respiratory_events += 1

            hr_near = nearest_value(heart, point.timestamp, max_seconds=120)
            if hr_near is not None and baseline_hr is not None and hr_near >= baseline_hr + 12:
                evidence.hr_spike_events += 1

            hrv_near = nearest_value(hrv, point.timestamp, max_seconds=120)
            if hrv_near is not None and baseline_hrv is not None and hrv_near <= baseline_hrv * 0.8:
                evidence.hrv_drop_events += 1

    score = min(
        1.0,
        evidence.low_respiratory_events * 0.1
        + evidence.hr_spike_events * 0.18
        + evidence.hrv_drop_events * 0.22,
    )

    signal_coverage = min(1.0, (len(heart) + len(hrv)) / max(1, len(respiratory)))
    confidence = min(1.0, (len(respiratory) / 120.0) * 0.6 + signal_coverage * 0.4)

    if score >= 0.75:
        severity = "high"
    elif score >= 0.45:
        severity = "medium"
    elif score > 0:
        severity = "low"
    else:
        severity = "none"

    summary = (
        f"Обнаружено случаев пониженной частоты дыхания: {evidence.low_respiratory_events}; "
        f"из них со всплеском пульса: {evidence.hr_spike_events}; "
        f"со снижением вариабельности сердечного ритма (HRV): {evidence.hrv_drop_events}."
    )

    recommendation = (
        "Если сигнал повторяется несколько ночей подряд, стоит обсудить результаты с сомнологом "
        "и рассмотреть клиническое обследование сна."
    )

    return RiskAssessment(
        condition="sleep_apnea_risk",
        window=window,
        score=round(score, 3),
        confidence=round(confidence, 3),
        severity=severity,
        interpretation=build_score_confidence_interpretation(score, confidence),
        summary=summary,
        recommendation=recommendation,
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
    )
