from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import EventPoint, to_points

_MIN_RR_DAYS = 7
_MIN_SPO2_MEASUREMENTS = 5
_LOOKBACK_DAYS = 14
_BASELINE_DAYS = 60


def _group_by_day_median(points: list[EventPoint], start: datetime, end: datetime) -> list[float]:
    by_day: dict[int, list[float]] = {}
    for p in points:
        if start <= p.timestamp <= end:
            by_day.setdefault(p.timestamp.toordinal(), []).append(p.value)
    return [median(vals) for vals in by_day.values()]


def assess_respiratory_function_decline_risk(
    respiratory_rows: Iterable[tuple],
    spo2_rows: Iterable[tuple] | None = None,
    walking_hr_rows: Iterable[tuple] | None = None,
    vo2max_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or datetime.utcnow()
    recent_start = now - timedelta(days=_LOOKBACK_DAYS)
    baseline_start = now - timedelta(days=_LOOKBACK_DAYS + _BASELINE_DAYS)

    rr_points = to_points(respiratory_rows)
    spo2_points = to_points(spo2_rows or [])
    whr_points = to_points(walking_hr_rows or [])
    vo2_points = to_points(vo2max_rows or [])

    recent_rr_vals = _group_by_day_median(rr_points, recent_start, now)
    baseline_rr_vals = _group_by_day_median(rr_points, baseline_start, recent_start)

    recent_spo2 = [p.value for p in spo2_points if p.timestamp >= recent_start]

    has_rr = len(recent_rr_vals) >= _MIN_RR_DAYS
    has_spo2 = len(recent_spo2) >= _MIN_SPO2_MEASUREMENTS
    has_load_metric = bool(whr_points) or bool(vo2_points)

    if not has_rr and not has_spo2:
        return RiskAssessment(
            condition="respiratory_function_decline_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных для оценки дыхательной функции.",
            summary=(
                f"RR: {len(recent_rr_vals)} дней (нужно ≥{_MIN_RR_DAYS}), "
                f"SpO2: {len(recent_spo2)} измерений (нужно ≥{_MIN_SPO2_MEASUREMENTS})."
            ),
            recommendation="Проверь синхронизацию данных частоты дыхания и SpO2 в Apple Health.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"rr_recent_days": len(recent_rr_vals), "spo2_recent_count": len(recent_spo2)},
        )

    if not has_load_metric:
        return RiskAssessment(
            condition="respiratory_function_decline_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Для оценки дыхательной функции нужна хотя бы одна нагрузочная метрика (walking HR или VO2 max).",
            summary="Отсутствуют нагрузочные метрики (пульс при ходьбе или VO2 max).",
            recommendation="Убедись, что данные ходьбы и VO2 max синхронизированы.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"rr_recent_days": len(recent_rr_vals), "spo2_recent_count": len(recent_spo2)},
        )

    rr_delta_pct = 0.0
    if has_rr and baseline_rr_vals:
        baseline_rr = median(baseline_rr_vals)
        recent_rr = median(recent_rr_vals)
        rr_delta_pct = (recent_rr - baseline_rr) / baseline_rr * 100 if baseline_rr > 0 else 0.0
    else:
        baseline_rr = None
        recent_rr = None

    spo2_below_92 = sum(1 for v in recent_spo2 if v < 92)
    spo2_below_94 = sum(1 for v in recent_spo2 if v < 94)

    if rr_delta_pct >= 15 and spo2_below_92 >= 2:
        severity = "high"
        score_base = 0.85
    elif rr_delta_pct >= 12 or spo2_below_94 >= 2:
        severity = "medium"
        score_base = 0.65
    elif rr_delta_pct >= 8:
        severity = "low"
        score_base = 0.35
    else:
        return RiskAssessment(
            condition="respiratory_function_decline_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(recent_rr_vals) / _MIN_RR_DAYS), 3),
            severity="none",
            interpretation="Значимого ухудшения дыхательной функции не выявлено.",
            summary=(
                f"Частота дыхания стабильна{f': Δ{rr_delta_pct:+.1f}%' if baseline_rr_vals else ''}. "
                f"SpO2 без значимых отклонений."
            ),
            recommendation="Продолжай наблюдение.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={
                "rr_delta_pct": round(rr_delta_pct, 1) if baseline_rr_vals else None,
                "spo2_below_94_count": spo2_below_94,
            },
        )

    score = score_base

    if whr_points:
        recent_whr = [p.value for p in whr_points if p.timestamp >= recent_start]
        baseline_whr = [p.value for p in whr_points if baseline_start <= p.timestamp < recent_start]
        if recent_whr and baseline_whr:
            whr_delta = median(recent_whr) - median(baseline_whr)
            if whr_delta >= 10:
                score = min(1.0, score + 0.1)

    if vo2_points:
        recent_vo2 = [p.value for p in vo2_points if p.timestamp >= recent_start]
        baseline_vo2 = [p.value for p in vo2_points if baseline_start <= p.timestamp < recent_start]
        if recent_vo2 and baseline_vo2:
            vo2_base = median(baseline_vo2)
            if vo2_base > 0 and (vo2_base - median(recent_vo2)) / vo2_base >= 0.10:
                score = min(1.0, score + 0.1)

    score = round(score, 3)
    if score >= 0.75:
        severity = "high"
    elif score >= 0.45:
        severity = "medium"
    elif score > 0:
        severity = "low"

    confidence = round(
        min(1.0, len(recent_rr_vals) / _MIN_RR_DAYS) * 0.5
        + min(1.0, len(recent_spo2) / 10.0) * 0.3
        + (0.2 if has_load_metric else 0.0),
        3,
    )

    summary_parts = []
    if baseline_rr_vals and recent_rr is not None and baseline_rr is not None:
        summary_parts.append(f"ЧД выросла с {baseline_rr:.1f} до {recent_rr:.1f} ({rr_delta_pct:+.1f}%)")
    if spo2_below_94 > 0:
        summary_parts.append(f"SpO2 <94%: {spo2_below_94} измерений, <92%: {spo2_below_92}")

    return RiskAssessment(
        condition="respiratory_function_decline_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Сочетание роста частоты дыхания и снижения SpO2 может указывать на ухудшение "
            "дыхательной функции. Возможные причины: заболевания лёгких, сердца или другие состояния."
        ),
        summary="Подозрение на ухудшение дыхательной функции. " + ". ".join(summary_parts) + ".",
        recommendation=(
            "Рекомендуется обратиться к пульмонологу или терапевту. "
            "При острой одышке необходима немедленная медицинская помощь."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "rr_delta_pct": round(rr_delta_pct, 1) if baseline_rr_vals else None,
            "rr_recent_days": len(recent_rr_vals),
            "spo2_below_94_count": spo2_below_94,
            "spo2_below_92_count": spo2_below_92,
        },
    )
