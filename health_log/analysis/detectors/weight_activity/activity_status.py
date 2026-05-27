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
    MIN_ACTIVITY_DAYS_VALID,
    target_threshold_for_age,
)
from health_log.analysis.detectors.weight_activity.helpers import (
    daily_step_totals,
    daily_totals,
    latest_complete_day_end,
)
from health_log.analysis.detectors.weight_activity.recommendations import (
    build_weight_activity_recommendations,
)
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import to_points
from health_log.utils import utcnow


def _sedentary_severity_for_steps(median_steps: float, target: int) -> tuple[str, float] | None:
    """Категория severity для assess_sedentary_lifestyle_risk относительно целевого порога.

    Целевой порог = "норма". Ступени ниже:
        target * 0.43 (~3000 при target=7000) → high
        target * 0.71 (~5000 при target=7000) → medium
        ниже target → low
        >= target → None (норма)
    """
    if median_steps >= target:
        return None
    if median_steps < round(target * 3 / 7):  # ~3000 при 7000, ~2571 при 6000, ~1714 при 4000
        return "high", 0.85
    if median_steps < round(target * 5 / 7):  # ~5000 при 7000, ~4286 при 6000, ~2857 при 4000
        return "medium", 0.65
    return "low", 0.35


def _insufficient_severity_for_steps(
    median_steps: float, target: int
) -> tuple[str, float] | None:
    """Категория severity для assess_insufficient_activity_risk.

    Ступени относительно целевого порога:
        target * 4/8 (~4000 при 8000-target эквиваленте) → high
        target * 6/8 → medium
        < target → low
        >= target → None (норма)
    Сохраняем семантику оригинальных STEP_INSUFFICIENT_HIGH/MEDIUM/LOW=4000/6000/8000:
    при target=7000 пороги становятся примерно target*4/7, target*6/7, target.
    """
    if median_steps >= target:
        return None
    if median_steps < round(target * 4 / 7):  # ~4000 при 7000, ~3429 при 6000, ~2286 при 4000
        return "high", 0.75
    if median_steps < round(target * 6 / 7):  # ~6000 при 7000, ~5143 при 6000, ~3429 при 4000
        return "medium", 0.55
    return "low", 0.35


def assess_sedentary_lifestyle_risk(
    step_rows: Iterable[tuple],
    exercise_time_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
    age: int | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    # Отсекаем незавершённый "сегодня" — берём данные до полуночи UTC текущего дня.
    eval_end = latest_complete_day_end(now)
    cutoff = eval_end - timedelta(days=MIN_ACTIVITY_DAYS)
    step_points = [p for p in to_points(step_rows) if cutoff <= p.timestamp < eval_end]
    exercise_points = [
        p for p in to_points(exercise_time_rows or []) if cutoff <= p.timestamp < eval_end
    ]

    daily_steps = daily_step_totals(step_points, cutoff, eval_end, exclude_zero=True)
    if len(daily_steps) < MIN_ACTIVITY_DAYS_VALID:
        return _insufficient(
            "sedentary_lifestyle_risk",
            window,
            len(step_points),
            f"мало валидных дней с шагами ({len(daily_steps)} из {MIN_ACTIVITY_DAYS_VALID})",
        )

    median_steps = median(daily_steps)
    target = target_threshold_for_age(age)
    confidence = round(min(1.0, len(daily_steps) / MIN_ACTIVITY_DAYS), 3)

    severity_pair = _sedentary_severity_for_steps(median_steps, target)
    if severity_pair is None:
        return RiskAssessment(
            condition="sedentary_lifestyle_risk",
            window=window,
            score=0.0,
            confidence=confidence,
            severity="none",
            interpretation="Уровень активности в норме.",
            summary=f"Медиана шагов {median_steps:.0f}/день — активность достаточная.",
            recommendation="Поддерживай текущий уровень активности.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={
                "median_daily_steps": round(median_steps, 0),
                "target_threshold": target,
            },
        )

    severity, score = severity_pair

    weekly_exercise = None
    if exercise_points:
        # Exercise time — суммы за день без фильтрации нулей.
        ex_totals = list(daily_totals(exercise_points, cutoff, eval_end).values())
        weekly_exercise = sum(ex_totals) / len(ex_totals) * 7 if ex_totals else 0.0
        if weekly_exercise < EXERCISE_TIME_WEEKLY_MIN:
            score = min(1.0, score + 0.1)

    if score >= 0.75:
        severity = "high"
    elif score >= 0.45:
        severity = "medium"
    elif score > 0:
        severity = "low"

    recs = build_weight_activity_recommendations(
        {
            "low_activity": True,
            "sedentary": True,
            "weight_issue": False,
        }
    )

    return RiskAssessment(
        condition="sedentary_lifestyle_risk",
        window=window,
        score=round(score, 3),
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Малоподвижный образ жизни связан с повышенным риском метаболических, "
            "сердечно-сосудистых заболеваний и снижения продолжительности жизни."
        ),
        summary=(
            f"Подозрение на малоподвижный образ жизни: медиана {median_steps:.0f} шагов/день"
            + (f", нагрузка {weekly_exercise:.0f} мин/нед" if weekly_exercise is not None else "")
            + f" (целевой порог {target})."
        ),
        recommendation=f"Увеличь ежедневную активность. Цель — не менее {target} шагов в день.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "median_daily_steps": round(median_steps, 0),
            "target_threshold": target,
            "weekly_exercise_min": round(weekly_exercise, 0)
            if weekly_exercise is not None
            else None,
        },
        lifestyle_recommendations=recs,
    )


def assess_insufficient_activity_risk(
    step_rows: Iterable[tuple],
    *,
    window: TimeWindow,
    now: datetime | None = None,
    age: int | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    eval_end = latest_complete_day_end(now)
    cutoff = eval_end - timedelta(days=MIN_ACTIVITY_DAYS)
    step_points = [p for p in to_points(step_rows) if cutoff <= p.timestamp < eval_end]

    daily_steps = daily_step_totals(step_points, cutoff, eval_end, exclude_zero=True)
    if len(daily_steps) < MIN_ACTIVITY_DAYS_VALID:
        return _insufficient(
            "insufficient_activity_risk",
            window,
            len(step_points),
            f"мало валидных дней с шагами ({len(daily_steps)} из {MIN_ACTIVITY_DAYS_VALID})",
        )

    median_steps = median(daily_steps)
    target = target_threshold_for_age(age)
    confidence = round(min(1.0, len(daily_steps) / MIN_ACTIVITY_DAYS), 3)

    severity_pair = _insufficient_severity_for_steps(median_steps, target)
    if severity_pair is None:
        return RiskAssessment(
            condition="insufficient_activity_risk",
            window=window,
            score=0.0,
            confidence=confidence,
            severity="none",
            interpretation="Объём повседневной активности достаточный.",
            summary=f"Медиана шагов {median_steps:.0f}/день — норма.",
            recommendation="Поддерживай текущий уровень активности.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={
                "median_daily_steps": round(median_steps, 0),
                "target_threshold": target,
            },
        )

    severity, score_base = severity_pair
    recs = build_weight_activity_recommendations({"low_activity": True})

    return RiskAssessment(
        condition="insufficient_activity_risk",
        window=window,
        score=round(score_base, 3),
        confidence=confidence,
        severity=severity,
        interpretation="Недостаточный объём повседневной активности может способствовать ухудшению здоровья.",
        summary=(
            f"Подозрение на недостаточную активность: медиана {median_steps:.0f} шагов/день "
            f"(целевой порог {target})."
        ),
        recommendation=f"Постепенно увеличивай ежедневное число шагов до {target}.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "median_daily_steps": round(median_steps, 0),
            "target_threshold": target,
        },
        lifestyle_recommendations=recs,
    )
