from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import to_points
from health_log.utils import utcnow

_MIN_MEASUREMENTS = 3
_LOOKBACK_DAYS = 90


def assess_vo2max_decline_risk(
    vo2max_rows: Iterable[tuple],
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    cutoff = now - timedelta(days=_LOOKBACK_DAYS)
    points = sorted(
        [p for p in to_points(vo2max_rows) if p.timestamp >= cutoff],
        key=lambda p: p.timestamp,
    )

    if len(points) < _MIN_MEASUREMENTS:
        return RiskAssessment(
            condition="vo2max_decline_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно измерений VO2 max для оценки тренда.",
            summary=f"Найдено {len(points)} измерений VO2 max за {_LOOKBACK_DAYS} дней (нужно ≥{_MIN_MEASUREMENTS}).",
            recommendation="Проверь синхронизацию данных VO2 max в Apple Health (требуются регулярные пробежки или ходьба).",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"measurements_count": len(points)},
        )

    baseline_val = median([p.value for p in points])
    recent_val = points[-1].value
    decline_pct = (baseline_val - recent_val) / baseline_val * 100 if baseline_val > 0 else 0.0

    if decline_pct >= 15:
        severity = "high"
        score_base = 0.85
    elif decline_pct >= 10:
        severity = "medium"
        score_base = 0.65
    elif decline_pct >= 8:
        # Apple Watch VO2max has ~10-15% measurement error; flag only above 8%
        severity = "low"
        score_base = 0.35
    else:
        return RiskAssessment(
            condition="vo2max_decline_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(points) / 6.0), 3),
            severity="none",
            interpretation="Значимого снижения VO2 max не выявлено.",
            summary=f"VO2 max стабилен: последнее значение {recent_val:.1f} мл/кг/мин (медиана {baseline_val:.1f}).",
            recommendation="Поддерживай регулярную кардионагрузку для сохранения кардиофитнеса.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={
                "recent_vo2max": round(recent_val, 1),
                "baseline_median_vo2max": round(baseline_val, 1),
                "decline_pct": round(decline_pct, 1),
            },
        )

    score = round(min(1.0, score_base + (decline_pct - 8) * 0.01), 3)
    confidence = round(min(1.0, len(points) / 6.0), 3)

    return RiskAssessment(
        condition="vo2max_decline_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Снижение VO2 max отражает ухудшение кардиореспираторного фитнеса. "
            "Возможные причины: снижение нагрузок, болезнь, усталость или другие факторы."
        ),
        summary=(
            f"Снижение кардиофитнеса: VO2 max {recent_val:.1f} мл/кг/мин "
            f"(медиана за {_LOOKBACK_DAYS} дней: {baseline_val:.1f}), падение на {decline_pct:.1f}%."
        ),
        recommendation=(
            "Увеличь объём аэробных нагрузок. "
            "При выраженном снижении или симптомах (одышка, усталость) обратись к кардиологу."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "recent_vo2max": round(recent_val, 1),
            "baseline_median_vo2max": round(baseline_val, 1),
            "decline_pct": round(decline_pct, 1),
            "measurements_count": len(points),
        },
    )
