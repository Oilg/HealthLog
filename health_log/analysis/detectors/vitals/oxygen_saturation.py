from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import EventPoint, to_points

_MIN_MEASUREMENTS = 10
_LOOKBACK_DAYS = 14


def _in_sleep(ts: datetime, segments: list[tuple[datetime, datetime]]) -> bool:
    for start, end in segments:
        if start <= ts <= end:
            return True
    return False


def _nights_with_low_spo2(
    points: list[EventPoint],
    segments: list[tuple[datetime, datetime]],
    threshold: float,
) -> int:
    nights: set[int] = set()
    for seg_start, seg_end in segments:
        night_points = [p for p in points if seg_start <= p.timestamp <= seg_end and p.value < threshold]
        if night_points:
            nights.add(seg_start.toordinal())
    return len(nights)


def assess_low_oxygen_saturation_risk(
    spo2_rows: Iterable[tuple],
    sleep_segments: list[tuple[datetime, datetime]] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=_LOOKBACK_DAYS)
    all_points = to_points(spo2_rows)
    points = [p for p in all_points if p.timestamp >= cutoff]
    segments = list(sleep_segments or [])

    if len(points) < _MIN_MEASUREMENTS:
        return RiskAssessment(
            condition="low_oxygen_saturation_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно измерений SpO2 для оценки.",
            summary=f"Найдено {len(points)} измерений SpO2 за {_LOOKBACK_DAYS} дней (нужно ≥{_MIN_MEASUREMENTS}).",
            recommendation="Проверь синхронизацию данных пульсоксиметрии в Apple Health.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"measurements_count": len(points)},
        )

    count_below_94 = sum(1 for p in points if p.value < 94)
    count_below_92 = sum(1 for p in points if p.value < 92)
    count_below_90 = sum(1 for p in points if p.value < 90)
    min_spo2 = min(p.value for p in points)
    med_spo2 = median([p.value for p in points])

    if count_below_90 >= 2:
        severity = "high"
        score_base = 0.85
    elif count_below_92 >= 3:
        severity = "medium"
        score_base = 0.65
    elif count_below_94 >= 2:
        severity = "low"
        score_base = 0.35
    else:
        return RiskAssessment(
            condition="low_oxygen_saturation_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(points) / 30.0), 3),
            severity="none",
            interpretation="Значимого снижения SpO2 не выявлено.",
            summary=f"SpO2 в норме: медиана {med_spo2:.0f}%, минимум {min_spo2:.0f}%.",
            recommendation="Продолжай наблюдение. При одышке или симптомах обратись к врачу.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={
                "measurements_count": len(points),
                "min_spo2": round(min_spo2, 1),
                "median_spo2": round(med_spo2, 1),
                "count_below_94": count_below_94,
            },
        )

    nights_low_94 = 0
    sleep_overlap_low_spo2_count = 0
    sleep_context_used = bool(segments)

    if segments:
        nights_low_94 = _nights_with_low_spo2(points, segments, 94)
        sleep_overlap_low_spo2_count = sum(
            1 for p in points if p.value < 94 and _in_sleep(p.timestamp, segments)
        )

    confidence = min(1.0, len(points) / 30.0) * 0.6
    if sleep_overlap_low_spo2_count > 0:
        confidence = min(1.0, confidence + 0.2)
    if nights_low_94 >= 2:
        confidence = min(1.0, confidence + 0.2)
    confidence = round(confidence, 3)

    score = round(min(1.0, score_base * (1.0 + (count_below_92 / 10.0))), 3)

    summary = (
        f"Подозрение на снижение SpO2: минимум {min_spo2:.0f}%, медиана {med_spo2:.0f}%. "
        f"Измерений <94%: {count_below_94}, <92%: {count_below_92}, <90%: {count_below_90}."
    )

    return RiskAssessment(
        condition="low_oxygen_saturation_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Это не диагноз; снижение SpO2 требует клинической оценки. "
            "При хроническом снижении возможны заболевания лёгких, апноэ или другие состояния."
        ),
        summary=summary,
        recommendation=(
            "Рекомендуется обратиться к пульмонологу или терапевту. "
            "При острой одышке или SpO2 <90% необходима немедленная медицинская помощь."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "measurements_count": len(points),
            "min_spo2": round(min_spo2, 1),
            "median_spo2": round(med_spo2, 1),
            "count_below_94": count_below_94,
            "count_below_92": count_below_92,
            "count_below_90": count_below_90,
            "nights_low_94": nights_low_94,
            "sleep_overlap_low_spo2_count": sleep_overlap_low_spo2_count,
            "sleep_context_used": sleep_context_used,
        },
    )
