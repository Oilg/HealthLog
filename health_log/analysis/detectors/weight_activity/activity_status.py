from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.detectors.weight_activity._common import (
    _insufficient,
)
from health_log.analysis.detectors.weight_activity.constants import (
    EXERCISE_TIME_WEEKLY_MIN,
    MIN_ACTIVITY_DAYS,
    STEP_HIGH_SEDENTARY,
    STEP_INSUFFICIENT_HIGH,
    STEP_INSUFFICIENT_LOW,
    STEP_INSUFFICIENT_MEDIUM,
    STEP_LOW_SEDENTARY,
    STEP_MEDIUM_SEDENTARY,
)
from health_log.analysis.detectors.weight_activity.helpers import (
    daily_medians,
    distinct_day_count,
)
from health_log.analysis.detectors.weight_activity.recommendations import (
    build_weight_activity_recommendations,
)
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import to_points
from health_log.utils import utcnow


def assess_sedentary_lifestyle_risk(
    step_rows: Iterable[tuple],
    exercise_time_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    cutoff = now - timedelta(days=MIN_ACTIVITY_DAYS)
    step_points = [p for p in to_points(step_rows) if p.timestamp >= cutoff]
    exercise_points = [p for p in to_points(exercise_time_rows or []) if p.timestamp >= cutoff]

    if distinct_day_count(step_points, cutoff, now) < MIN_ACTIVITY_DAYS:
        return _insufficient("sedentary_lifestyle_risk", window, len(step_points), "мало дней с данными шагов")

    daily_steps = daily_medians(step_points, cutoff, now)
    median_steps = median(daily_steps)

    if median_steps < STEP_LOW_SEDENTARY:
        severity, score_base = "high", 0.85
    elif median_steps < STEP_MEDIUM_SEDENTARY:
        severity, score_base = "medium", 0.65
    elif median_steps < STEP_HIGH_SEDENTARY:
        severity, score_base = "low", 0.35
    else:
        return RiskAssessment(
            condition="sedentary_lifestyle_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(daily_steps) / MIN_ACTIVITY_DAYS), 3),
            severity="none",
            interpretation="Уровень активности в норме.",
            summary=f"Медиана шагов {median_steps:.0f}/день — активность достаточная.",
            recommendation="Поддерживай текущий уровень активности.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"median_daily_steps": round(median_steps, 0)},
        )

    score = score_base
    weekly_exercise = None
    if exercise_points:
        daily_ex = daily_medians(exercise_points, cutoff, now)
        weekly_exercise = sum(daily_ex) / len(daily_ex) * 7 if daily_ex else 0.0
        if weekly_exercise < EXERCISE_TIME_WEEKLY_MIN:
            score = min(1.0, score + 0.1)

    if score >= 0.75:
        severity = "high"
    elif score >= 0.45:
        severity = "medium"
    elif score > 0:
        severity = "low"

    recs = build_weight_activity_recommendations({
        "low_activity": True,
        "sedentary": True,
        "weight_issue": False,
    })

    return RiskAssessment(
        condition="sedentary_lifestyle_risk",
        window=window,
        score=round(score, 3),
        confidence=round(min(1.0, len(daily_steps) / MIN_ACTIVITY_DAYS), 3),
        severity=severity,
        interpretation=(
            "Малоподвижный образ жизни связан с повышенным риском метаболических, "
            "сердечно-сосудистых заболеваний и снижения продолжительности жизни."
        ),
        summary=(
            f"Подозрение на малоподвижный образ жизни: медиана {median_steps:.0f} шагов/день"
            + (f", нагрузка {weekly_exercise:.0f} мин/нед" if weekly_exercise is not None else "")
            + "."
        ),
        recommendation="Увеличь ежедневную активность. Цель — не менее 7000–10000 шагов в день.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "median_daily_steps": round(median_steps, 0),
            "weekly_exercise_min": round(weekly_exercise, 0) if weekly_exercise is not None else None,
        },
        lifestyle_recommendations=recs,
    )




def assess_insufficient_activity_risk(
    step_rows: Iterable[tuple],
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    cutoff = now - timedelta(days=MIN_ACTIVITY_DAYS)
    step_points = [p for p in to_points(step_rows) if p.timestamp >= cutoff]

    if distinct_day_count(step_points, cutoff, now) < MIN_ACTIVITY_DAYS:
        return _insufficient("insufficient_activity_risk", window, len(step_points), "мало дней с данными шагов")

    daily_steps = daily_medians(step_points, cutoff, now)
    median_steps = median(daily_steps)

    if median_steps < STEP_INSUFFICIENT_HIGH:
        severity, score_base = "high", 0.75
    elif median_steps < STEP_INSUFFICIENT_MEDIUM:
        severity, score_base = "medium", 0.55
    elif median_steps < STEP_INSUFFICIENT_LOW:
        severity, score_base = "low", 0.35
    else:
        return RiskAssessment(
            condition="insufficient_activity_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(daily_steps) / MIN_ACTIVITY_DAYS), 3),
            severity="none",
            interpretation="Объём повседневной активности достаточный.",
            summary=f"Медиана шагов {median_steps:.0f}/день — норма.",
            recommendation="Поддерживай текущий уровень активности.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"median_daily_steps": round(median_steps, 0)},
        )

    recs = build_weight_activity_recommendations({"low_activity": True})

    return RiskAssessment(
        condition="insufficient_activity_risk",
        window=window,
        score=round(score_base, 3),
        confidence=round(min(1.0, len(daily_steps) / MIN_ACTIVITY_DAYS), 3),
        severity=severity,
        interpretation="Недостаточный объём повседневной активности может способствовать ухудшению здоровья.",
        summary=f"Подозрение на недостаточную активность: медиана {median_steps:.0f} шагов/день.",
        recommendation="Постепенно увеличивай ежедневное число шагов до 8000–10000.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={"median_daily_steps": round(median_steps, 0)},
        lifestyle_recommendations=recs,
    )


