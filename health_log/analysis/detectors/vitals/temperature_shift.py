from __future__ import annotations

from datetime import datetime, timedelta
from health_log.utils import utcnow
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import EventPoint, to_points

_MIN_BASELINE_NIGHTS = 7
_MIN_RECENT_NIGHTS = 2
_BASELINE_LOOKBACK_DAYS = 14
_RECENT_LOOKBACK_DAYS = 2


def _group_by_date(points: list[EventPoint]) -> dict[int, list[float]]:
    by_date: dict[int, list[float]] = {}
    for p in points:
        key = p.timestamp.toordinal()
        by_date.setdefault(key, []).append(p.value)
    return by_date


def _daily_medians(by_date: dict[int, list[float]]) -> list[tuple[int, float]]:
    return sorted((day, median(vals)) for day, vals in by_date.items())


def assess_temperature_shift_risk(
    wrist_temp_rows: Iterable[tuple],
    heart_rows: Iterable[tuple] | None = None,
    respiratory_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    all_temp_points = to_points(wrist_temp_rows)

    recent_cutoff = now - timedelta(days=_RECENT_LOOKBACK_DAYS)
    baseline_cutoff = now - timedelta(days=_BASELINE_LOOKBACK_DAYS + _RECENT_LOOKBACK_DAYS)

    baseline_points = [p for p in all_temp_points if baseline_cutoff <= p.timestamp < recent_cutoff]
    recent_points = [p for p in all_temp_points if p.timestamp >= recent_cutoff]

    baseline_by_date = _group_by_date(baseline_points)
    recent_by_date = _group_by_date(recent_points)

    if len(baseline_by_date) < _MIN_BASELINE_NIGHTS:
        return RiskAssessment(
            condition="temperature_shift_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно базовых данных температуры запястья.",
            summary=(
                f"Найдено {len(baseline_by_date)} ночей базового периода "
                f"(нужно ≥{_MIN_BASELINE_NIGHTS})."
            ),
            recommendation="Продолжай синхронизацию данных Apple Watch для накопления baseline.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"baseline_nights": len(baseline_by_date), "recent_nights": len(recent_by_date)},
        )

    if len(recent_by_date) < _MIN_RECENT_NIGHTS:
        return RiskAssessment(
            condition="temperature_shift_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно последних данных температуры запястья.",
            summary=f"Найдено {len(recent_by_date)} ночей в recent-периоде (нужно ≥{_MIN_RECENT_NIGHTS}).",
            recommendation="Продолжай ношение Apple Watch во время сна.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"baseline_nights": len(baseline_by_date), "recent_nights": len(recent_by_date)},
        )

    baseline_values = [m for _, m in _daily_medians(baseline_by_date)]
    recent_values = [m for _, m in _daily_medians(recent_by_date)]
    baseline_temp = median(baseline_values)
    recent_temp = median(recent_values)
    delta = recent_temp - baseline_temp

    if delta >= 0.7:
        severity = "high"
        score_base = 0.85
    elif delta >= 0.5:
        severity = "medium"
        score_base = 0.65
    elif delta >= 0.3:
        severity = "low"
        score_base = 0.35
    else:
        return RiskAssessment(
            condition="temperature_shift_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(baseline_by_date) / 14.0), 3),
            severity="none",
            interpretation="Значимого температурного сдвига не выявлено.",
            summary=f"Температура в норме: baseline {baseline_temp:.2f}°C, recent {recent_temp:.2f}°C (Δ={delta:+.2f}°C).",
            recommendation="Продолжай наблюдение.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={
                "baseline_temp": round(baseline_temp, 2),
                "recent_temp": round(recent_temp, 2),
                "delta_c": round(delta, 2),
            },
        )

    score = score_base
    hr_points = to_points(heart_rows or [])
    rr_points = to_points(respiratory_rows or [])

    hr_boost = False
    rr_boost = False

    if hr_points:
        recent_hr_points = [p for p in hr_points if p.timestamp >= recent_cutoff]
        baseline_hr_points = [p for p in hr_points if baseline_cutoff <= p.timestamp < recent_cutoff]
        if recent_hr_points and baseline_hr_points:
            recent_hr = median([p.value for p in recent_hr_points])
            baseline_hr = median([p.value for p in baseline_hr_points])
            if recent_hr >= baseline_hr + 5:
                score = min(1.0, score + 0.1)
                hr_boost = True

    if rr_points:
        recent_rr_points = [p for p in rr_points if p.timestamp >= recent_cutoff]
        baseline_rr_points = [p for p in rr_points if baseline_cutoff <= p.timestamp < recent_cutoff]
        if recent_rr_points and baseline_rr_points:
            recent_rr = median([p.value for p in recent_rr_points])
            baseline_rr = median([p.value for p in baseline_rr_points])
            if baseline_rr > 0 and recent_rr >= baseline_rr * 1.08:
                score = min(1.0, score + 0.1)
                rr_boost = True

    score = round(score, 3)
    if score >= 0.75:
        severity = "high"
    elif score >= 0.45:
        severity = "medium"
    elif score > 0:
        severity = "low"

    confidence = round(min(1.0, len(baseline_by_date) / 14.0) * 0.7 + min(1.0, len(recent_by_date) / 3.0) * 0.3, 3)

    summary = (
        f"Подозрение на температурный сдвиг: +{delta:.2f}°C (baseline {baseline_temp:.2f}°C → recent {recent_temp:.2f}°C)."
    )
    if hr_boost:
        summary += " Пульс ночью также повышен."
    if rr_boost:
        summary += " Частота дыхания также повышена."

    return RiskAssessment(
        condition="temperature_shift_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Это не диагноз; повышение температуры запястья может указывать на начало инфекционного процесса, "
            "воспаление или иные состояния. Оценка основана на данных носимого устройства."
        ),
        summary=summary,
        recommendation=(
            "При сохраняющемся повышении температуры, появлении симптомов болезни или "
            "ухудшении самочувствия обратись к терапевту."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "baseline_temp_c": round(baseline_temp, 2),
            "recent_temp_c": round(recent_temp, 2),
            "delta_c": round(delta, 2),
            "baseline_nights": len(baseline_by_date),
            "recent_nights": len(recent_by_date),
            "hr_elevated": hr_boost,
            "rr_elevated": rr_boost,
        },
    )
