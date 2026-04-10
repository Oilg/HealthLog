from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow

_IRREGULAR_EVENTS_BOOST = 0.15
_ECG_AFIB_BOOST = 0.25


def assess_atrial_fibrillation_risk(
    afib_burden_rows: Iterable[tuple[datetime, float]] | None = None,
    irregular_rhythm_event_rows: Iterable[tuple[datetime, object]] | None = None,
    *,
    ecg_afib_count: int = 0,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or datetime.utcnow()
    cutoff_30d = now - timedelta(days=30)

    burden_values = [float(v) for _, v in (afib_burden_rows or []) if v is not None]
    event_timestamps = [ts for ts, _ in (irregular_rhythm_event_rows or []) if ts is not None]
    events_30d = sum(1 for ts in event_timestamps if ts >= cutoff_30d)

    has_burden = bool(burden_values)
    has_events = bool(event_timestamps)

    if not has_burden and not (has_events and ecg_afib_count > 0):
        if not has_events and ecg_afib_count == 0:
            return RiskAssessment(
                condition="atrial_fibrillation_risk",
                window=window,
                score=0.0,
                confidence=0.0,
                severity="unknown",
                interpretation="Недостаточно данных: нет данных AFib burden, событий ритма или ЭКГ.",
                summary="Данных для оценки риска фибрилляции предсердий недостаточно.",
                recommendation="Для оценки риска ФП необходима ЭКГ или наличие AFib burden из Apple Watch.",
                clinical_safety_note=CLINICAL_SAFETY_NOTE,
                supporting_metrics={"afib_burden_records": 0, "events_30d": 0},
            )

    avg_burden = sum(burden_values) / len(burden_values) if burden_values else 0.0
    max_burden = max(burden_values) if burden_values else 0.0

    if has_burden:
        if avg_burden > 5.0:
            base_score, severity = 0.85, "high"
        elif avg_burden >= 1.0:
            base_score, severity = 0.6, "medium"
        else:
            base_score, severity = 0.25, "low"
    else:
        base_score, severity = 0.25, "low"

    score = base_score
    if events_30d >= 2:
        score = min(1.0, score + _IRREGULAR_EVENTS_BOOST)
    if ecg_afib_count > 0:
        score = min(1.0, score + _ECG_AFIB_BOOST)

    score = round(score, 3)

    confidence_parts = []
    if has_burden:
        confidence_parts.append(min(1.0, len(burden_values) / 10.0))
    if has_events:
        confidence_parts.append(min(1.0, len(event_timestamps) / 5.0))
    if ecg_afib_count > 0:
        confidence_parts.append(0.9)
    confidence = round(sum(confidence_parts) / max(len(confidence_parts), 1), 3)

    if score >= 0.75:
        severity = "high"
    elif score >= 0.45:
        severity = "medium"
    elif score > 0:
        severity = "low"

    summary_parts = []
    if has_burden:
        summary_parts.append(f"AFib burden: среднее {avg_burden:.1f}%, максимум {max_burden:.1f}%")
    if has_events:
        summary_parts.append(f"{len(event_timestamps)} событий нерегулярного ритма, из них {events_30d} за 30 дней")
    if ecg_afib_count > 0:
        summary_parts.append(f"ЭКГ Apple Watch: {ecg_afib_count} записей с признаками ФП")

    metrics: dict[str, object] = {
        "afib_burden_records": len(burden_values),
        "avg_burden_pct": round(avg_burden, 2),
        "max_burden_pct": round(max_burden, 2),
        "irregular_events_total": len(event_timestamps),
        "irregular_events_30d": events_30d,
        "ecg_afib_count": ecg_afib_count,
    }

    return RiskAssessment(
        condition="atrial_fibrillation_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Это не диагноз; подтверждение ФП требует ЭКГ. "
            "Оценка основана на данных носимого устройства и не заменяет профессиональную диагностику."
        ),
        summary="Подозрение на фибрилляцию предсердий. " + ". ".join(summary_parts) + ".",
        recommendation=(
            "Обязательна консультация кардиолога. "
            "Необходимо подтверждение ЭКГ или суточным мониторированием (Holter)."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics=metrics,
    )
