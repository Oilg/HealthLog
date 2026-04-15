from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import EventPoint, to_points
from health_log.utils import utcnow

_MIN_MOBILITY_DAYS = 7
_LOOKBACK_DAYS = 30
_BASELINE_DAYS = 60


def _daily_medians(points: list[EventPoint], start: datetime, end: datetime) -> list[float]:
    by_day: dict[int, list[float]] = {}
    for p in points:
        if start <= p.timestamp <= end:
            by_day.setdefault(p.timestamp.toordinal(), []).append(p.value)
    return [median(vals) for vals in by_day.values()]


def _days_count(points: list[EventPoint], start: datetime, end: datetime) -> int:
    return len({p.timestamp.toordinal() for p in points if start <= p.timestamp <= end})


def assess_fall_risk(
    steadiness_rows: Iterable[tuple] | None = None,
    walking_speed_rows: Iterable[tuple] | None = None,
    step_length_rows: Iterable[tuple] | None = None,
    double_support_rows: Iterable[tuple] | None = None,
    *,
    apple_fall_event_count: int = 0,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    recent_start = now - timedelta(days=_LOOKBACK_DAYS)
    baseline_start = now - timedelta(days=_LOOKBACK_DAYS + _BASELINE_DAYS)

    steadiness = to_points(steadiness_rows or [])
    speed = to_points(walking_speed_rows or [])
    step_len = to_points(step_length_rows or [])
    double_sup = to_points(double_support_rows or [])

    all_mobility = steadiness + speed + step_len + double_sup
    recent_days = _days_count(all_mobility, recent_start, now)

    if apple_fall_event_count == 0 and recent_days < _MIN_MOBILITY_DAYS:
        return RiskAssessment(
            condition="fall_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных подвижности для оценки риска падений.",
            summary=f"Найдено {recent_days} дней с данными подвижности (нужно ≥{_MIN_MOBILITY_DAYS}).",
            recommendation="Проверь синхронизацию данных ходьбы в Apple Health.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"recent_mobility_days": recent_days},
        )

    if apple_fall_event_count > 0:
        return RiskAssessment(
            condition="fall_risk",
            window=window,
            score=0.9,
            confidence=0.9,
            severity="high",
            interpretation=(
                "Apple Watch зафиксировал событие риска падения или падение. "
                "Это требует немедленной клинической оценки."
            ),
            summary=f"Apple Health зафиксировал {apple_fall_event_count} событие(й) риска падения.",
            recommendation=(
                "Обратись к неврологу или терапевту для оценки рисков и профилактики падений. "
                "Рассмотри физиотерапию для улучшения баланса."
            ),
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"apple_fall_event_count": apple_fall_event_count, "recent_mobility_days": recent_days},
        )

    recent_steadiness = _daily_medians(steadiness, recent_start, now)
    baseline_steadiness = _daily_medians(steadiness, baseline_start, recent_start)

    recent_speed = _daily_medians(speed, recent_start, now)
    baseline_speed = _daily_medians(speed, baseline_start, recent_start)

    recent_step = _daily_medians(step_len, recent_start, now)
    baseline_step = _daily_medians(step_len, baseline_start, recent_start)

    recent_ds = _daily_medians(double_sup, recent_start, now)
    baseline_ds = _daily_medians(double_sup, baseline_start, recent_start)

    def decline_pct(baseline_vals: list[float], recent_vals: list[float]) -> float | None:
        if not baseline_vals or not recent_vals:
            return None
        b = median(baseline_vals)
        r = median(recent_vals)
        if b == 0:
            return None
        return (b - r) / b * 100

    def increase_pct(baseline_vals: list[float], recent_vals: list[float]) -> float | None:
        d = decline_pct(baseline_vals, recent_vals)
        return -d if d is not None else None

    steadiness_decline = decline_pct(baseline_steadiness, recent_steadiness)
    speed_decline = decline_pct(baseline_speed, recent_speed)
    step_length_decline = decline_pct(baseline_step, recent_step)
    ds_increase = increase_pct(baseline_ds, recent_ds)

    max_decline = max(
        (v for v in [steadiness_decline, speed_decline, step_length_decline, ds_increase, 0.0] if v is not None),
        default=0.0,
    )

    if max_decline >= 30:
        severity = "high"
        score = 0.85
    elif max_decline >= 20:
        severity = "medium"
        score = 0.65
    elif max_decline >= 10:
        severity = "low"
        score = 0.35
    else:
        return RiskAssessment(
            condition="fall_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, recent_days / _MIN_MOBILITY_DAYS), 3),
            severity="none",
            interpretation="Значимого ухудшения показателей ходьбы не выявлено.",
            summary="Показатели устойчивости ходьбы в норме.",
            recommendation="Продолжай регулярную активность для поддержания баланса.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={
                "steadiness_decline_pct": round(steadiness_decline, 1) if steadiness_decline is not None else None,
                "speed_decline_pct": round(speed_decline, 1) if speed_decline is not None else None,
                "step_length_decline_pct": round(step_length_decline, 1) if step_length_decline is not None else None,
            },
        )

    score = round(score, 3)
    confidence = round(min(1.0, recent_days / _MIN_MOBILITY_DAYS), 3)

    return RiskAssessment(
        condition="fall_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Ухудшение показателей устойчивости ходьбы может указывать на повышенный риск падений. "
            "Требует внимания, особенно у пожилых людей."
        ),
        summary=f"Подозрение на ухудшение устойчивости ходьбы: максимальное отклонение {max_decline:.0f}%.",
        recommendation=(
            "Рекомендуется консультация невролога или терапевта. "
            "Рассмотри тренировки баланса и силовые упражнения."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "steadiness_decline_pct": round(steadiness_decline, 1) if steadiness_decline is not None else None,
            "speed_decline_pct": round(speed_decline, 1) if speed_decline is not None else None,
            "step_length_decline_pct": round(step_length_decline, 1) if step_length_decline is not None else None,
            "double_support_increase_pct": round(ds_increase, 1) if ds_increase is not None else None,
            "recent_mobility_days": recent_days,
        },
    )
