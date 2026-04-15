from __future__ import annotations

from datetime import datetime
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.utils import utcnow

_SCORE_ONE_EVENT = 0.3
_SCORE_TWO_PLUS_EVENTS = 0.6
_SCORE_THREE_PLUS_EVENTS_30D = 0.8
_AFIB_BURDEN_BOOST = 0.2
_ECG_ABNORMAL_BOOST = 0.25


def _count_events_in_window(event_timestamps: list[datetime], cutoff: datetime) -> int:
    return sum(1 for ts in event_timestamps if ts >= cutoff)


def assess_irregular_rhythm_risk(
    irregular_rhythm_event_rows: Iterable[tuple[datetime, object]],
    *,
    afib_burden_pct: float | None = None,
    ecg_abnormal_count: int = 0,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    event_timestamps = [ts for ts, _ in irregular_rhythm_event_rows if ts is not None]

    if not event_timestamps:
        return RiskAssessment(
            condition="irregular_rhythm_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных: событий нерегулярного ритма не зафиксировано.",
            summary="Событий нерегулярного ритма Apple Health не обнаружено.",
            recommendation="При сердцебиениях, перебоях в ритме обратись к кардиологу.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"events_90d": 0, "events_30d": 0},
        )

    cutoff_90d = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_90d = cutoff_90d.__class__(
        cutoff_90d.year, cutoff_90d.month, cutoff_90d.day
    )
    from datetime import timedelta
    cutoff_90d = now - timedelta(days=90)
    cutoff_30d = now - timedelta(days=30)

    events_90d = _count_events_in_window(event_timestamps, cutoff_90d)
    events_30d = _count_events_in_window(event_timestamps, cutoff_30d)

    if events_30d >= 3:
        base_score = _SCORE_THREE_PLUS_EVENTS_30D
        severity = "high"
    elif events_90d >= 2:
        base_score = _SCORE_TWO_PLUS_EVENTS
        severity = "medium"
    else:
        base_score = _SCORE_ONE_EVENT
        severity = "low"

    score = base_score
    if afib_burden_pct is not None and afib_burden_pct > 2.0:
        score = min(1.0, score + _AFIB_BURDEN_BOOST)
    if ecg_abnormal_count > 0:
        score = min(1.0, score + _ECG_ABNORMAL_BOOST)

    score = round(score, 3)

    confidence = round(min(1.0, events_90d / 5.0) * 0.6 + (0.4 if ecg_abnormal_count > 0 else 0.0), 3)

    metrics: dict[str, object] = {
        "events_90d": events_90d,
        "events_30d": events_30d,
    }
    if afib_burden_pct is not None:
        metrics["afib_burden_pct"] = round(afib_burden_pct, 2)
    if ecg_abnormal_count > 0:
        metrics["ecg_abnormal_count"] = ecg_abnormal_count

    summary = (
        f"Подозрение на нерегулярный сердечный ритм: {events_90d} событий за 90 дней, "
        f"{events_30d} за последние 30 дней."
    )

    return RiskAssessment(
        condition="irregular_rhythm_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Это не диагноз; подтверждение нарушения ритма требует ЭКГ или суточного мониторирования. "
            "Оценка основана на событиях, зафиксированных Apple Health."
        ),
        summary=summary,
        recommendation=(
            "Рекомендуется обратиться к кардиологу для ЭКГ или Holter-мониторирования. "
            "Нарушения ритма требуют профессиональной оценки."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics=metrics,
    )
