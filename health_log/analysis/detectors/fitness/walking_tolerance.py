from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import EventPoint, to_points

_MIN_VALID_DAYS = 10
_LOOKBACK_DAYS = 30
_BASELINE_DAYS = 60
_STEP_RANGE_LOW = 3000
_STEP_RANGE_HIGH = 8000


def _group_by_day(points: list[EventPoint]) -> dict[int, float]:
    by_day: dict[int, list[float]] = {}
    for p in points:
        by_day.setdefault(p.timestamp.toordinal(), []).append(p.value)
    return {day: median(vals) for day, vals in by_day.items()}


def assess_walking_tolerance_decline_risk(
    walking_hr_rows: Iterable[tuple],
    step_rows: Iterable[tuple],
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or datetime.utcnow()
    recent_cutoff = now - timedelta(days=_LOOKBACK_DAYS)
    baseline_cutoff = now - timedelta(days=_LOOKBACK_DAYS + _BASELINE_DAYS)

    whr_points = to_points(walking_hr_rows)
    step_points = to_points(step_rows)

    step_by_day = _group_by_day(step_points)

    def filter_moderate_days(pts: list[EventPoint], cutoff_start: datetime, cutoff_end: datetime) -> list[float]:
        result = []
        for p in pts:
            if not (cutoff_start <= p.timestamp <= cutoff_end):
                continue
            day = p.timestamp.toordinal()
            day_steps = step_by_day.get(day, 0)
            if _STEP_RANGE_LOW <= day_steps <= _STEP_RANGE_HIGH:
                result.append(p.value)
        return result

    recent_hr_vals = filter_moderate_days(whr_points, recent_cutoff, now)
    baseline_hr_vals = filter_moderate_days(whr_points, baseline_cutoff, recent_cutoff)

    recent_days = len({p.timestamp.toordinal() for p in step_points if p.timestamp >= recent_cutoff})

    if recent_days < _MIN_VALID_DAYS:
        return RiskAssessment(
            condition="walking_tolerance_decline_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных для оценки переносимости ходьбы.",
            summary=f"Найдено {recent_days} дней с данными за {_LOOKBACK_DAYS} дней (нужно ≥{_MIN_VALID_DAYS}).",
            recommendation="Проверь синхронизацию шагов и пульса при ходьбе в Apple Health.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"recent_valid_days": recent_days},
        )

    if not recent_hr_vals or not baseline_hr_vals:
        return RiskAssessment(
            condition="walking_tolerance_decline_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, recent_days / _MIN_VALID_DAYS), 3),
            severity="unknown",
            interpretation="Недостаточно дней с умеренной активностью (3000–8000 шагов) для сравнения.",
            summary="Нет дней с сопоставимой активностью в обоих периодах.",
            recommendation="Продолжай синхронизацию данных для накопления baseline.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"recent_valid_days": recent_days, "moderate_activity_days_recent": len(recent_hr_vals)},
        )

    baseline_hr = median(baseline_hr_vals)
    recent_hr = median(recent_hr_vals)
    delta_bpm = recent_hr - baseline_hr

    if delta_bpm >= 15:
        severity = "high"
        score_base = 0.85
    elif delta_bpm >= 10:
        severity = "medium"
        score_base = 0.65
    elif delta_bpm >= 7:
        severity = "low"
        score_base = 0.35
    else:
        return RiskAssessment(
            condition="walking_tolerance_decline_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, recent_days / _MIN_VALID_DAYS), 3),
            severity="none",
            interpretation="Переносимость обычной нагрузки не ухудшилась.",
            summary=(
                f"Пульс при ходьбе стабилен: baseline {baseline_hr:.0f} уд/мин, "
                f"recent {recent_hr:.0f} уд/мин (Δ={delta_bpm:+.0f})."
            ),
            recommendation="Продолжай поддерживать регулярную активность.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={
                "baseline_walking_hr": round(baseline_hr, 1),
                "recent_walking_hr": round(recent_hr, 1),
                "delta_bpm": round(delta_bpm, 1),
            },
        )

    score = round(score_base, 3)
    confidence = round(min(1.0, recent_days / _MIN_VALID_DAYS) * 0.7 + min(1.0, len(recent_hr_vals) / 10.0) * 0.3, 3)

    return RiskAssessment(
        condition="walking_tolerance_decline_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Рост пульса при аналогичной нагрузке может указывать на снижение кардиофитнеса, "
            "болезнь, стресс или недовосстановление."
        ),
        summary=(
            f"Подозрение на ухудшение переносимости нагрузки: пульс при ходьбе вырос "
            f"с {baseline_hr:.0f} до {recent_hr:.0f} уд/мин (+{delta_bpm:.0f} уд/мин) "
            f"при сопоставимой активности ({_STEP_RANGE_LOW}–{_STEP_RANGE_HIGH} шагов/день)."
        ),
        recommendation=(
            "Проверь самочувствие и уровень нагрузок. "
            "При продолжающемся росте пульса или симптомах обратись к кардиологу."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "baseline_walking_hr": round(baseline_hr, 1),
            "recent_walking_hr": round(recent_hr, 1),
            "delta_bpm": round(delta_bpm, 1),
            "recent_valid_days": recent_days,
            "moderate_activity_days_baseline": len(baseline_hr_vals),
            "moderate_activity_days_recent": len(recent_hr_vals),
        },
    )
