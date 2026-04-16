from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import to_points
from health_log.utils import utcnow

_MIN_MEASUREMENTS = 5
_LOOKBACK_DAYS = 60
_VO2MAX_DECLINE_BOOST = 0.1

# Walking heart rate average rises when cardiovascular fitness declines:
# higher walking HR at the same activity level → worse aerobic capacity.
# Thresholds represent rise in bpm over the lookback period.
_THRESHOLD_HIGH = 12   # ≥12 bpm rise → high risk
_THRESHOLD_MEDIUM = 8  # ≥8 bpm rise  → medium risk
_THRESHOLD_LOW = 5     # ≥5 bpm rise  → low risk


def assess_hrr_decline_risk(
    hrr_rows: Iterable[tuple],
    vo2max_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    """Detect cardiovascular fitness decline via walking heart rate trend.

    Uses HKQuantityTypeIdentifierWalkingHeartRateAverage: if walking HR rises
    over time (while activity level stays similar) that indicates reduced
    aerobic capacity.  This is NOT clinical Heart Rate Recovery (HRR), which
    requires post-exercise 1-min measurement — it is a submaximal fitness proxy.
    """
    now = now or utcnow()
    cutoff = now - timedelta(days=_LOOKBACK_DAYS)
    points = sorted(
        [p for p in to_points(hrr_rows) if p.timestamp >= cutoff],
        key=lambda p: p.timestamp,
    )

    if len(points) < _MIN_MEASUREMENTS:
        return RiskAssessment(
            condition="walking_fitness_decline_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных пульса при ходьбе для оценки кардиофитнеса.",
            summary=(
                f"Найдено {len(points)} записей пульса при ходьбе за {_LOOKBACK_DAYS} дней "
                f"(нужно ≥{_MIN_MEASUREMENTS})."
            ),
            recommendation="Убедись, что данные Walking Heart Rate Average синхронизированы из Apple Health.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"measurements_count": len(points)},
        )

    split_idx = max(1, int(len(points) * 0.6))
    baseline_points = points[:split_idx]
    recent_points = points[split_idx:]

    baseline_whr = median([p.value for p in baseline_points])
    recent_whr = median([p.value for p in recent_points])

    # Positive rise = walking HR went up = fitness declined
    rise_bpm = recent_whr - baseline_whr

    if rise_bpm < _THRESHOLD_LOW:
        return RiskAssessment(
            condition="walking_fitness_decline_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(points) / 10.0), 3),
            severity="none",
            interpretation="Значимого роста пульса при ходьбе не выявлено.",
            summary=(
                f"Кардиофитнес при ходьбе стабилен: ЧСС {baseline_whr:.1f} → {recent_whr:.1f} уд/мин "
                f"(Δ={rise_bpm:+.1f})."
            ),
            recommendation="Поддерживай регулярные аэробные нагрузки.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={
                "baseline_walking_hr": round(baseline_whr, 1),
                "recent_walking_hr": round(recent_whr, 1),
                "rise_bpm": round(rise_bpm, 1),
            },
        )

    if rise_bpm >= _THRESHOLD_HIGH:
        severity = "high"
        score_base = 0.85
    elif rise_bpm >= _THRESHOLD_MEDIUM:
        severity = "medium"
        score_base = 0.65
    else:
        severity = "low"
        score_base = 0.35

    score = score_base
    vo2max_declined = False

    if vo2max_rows is not None:
        vo2_points = sorted(
            [p for p in to_points(vo2max_rows) if p.timestamp >= cutoff],
            key=lambda p: p.timestamp,
        )
        if len(vo2_points) >= 3:
            vo2_baseline = median([p.value for p in vo2_points])
            vo2_recent = vo2_points[-1].value
            if vo2_baseline > 0 and (vo2_baseline - vo2_recent) / vo2_baseline >= 0.05:
                score = min(1.0, score + _VO2MAX_DECLINE_BOOST)
                vo2max_declined = True

    score = round(score, 3)
    confidence = round(min(1.0, len(points) / 10.0), 3)

    return RiskAssessment(
        condition="walking_fitness_decline_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Рост пульса при одинаковой активности ходьбы указывает на снижение аэробного кардиофитнеса. "
            "Это косвенный показатель; для точной оценки нужны нагрузочные тесты."
        ),
        summary=(
            f"Снижение кардиофитнеса при ходьбе: ЧСС выросла с {baseline_whr:.1f} до "
            f"{recent_whr:.1f} уд/мин (+{rise_bpm:.1f} уд/мин за {_LOOKBACK_DAYS} дней)."
            + (" VO2 max также снижается." if vo2max_declined else "")
        ),
        recommendation=(
            "Увеличь объём аэробных нагрузок (ходьба, бег, велосипед). "
            "При продолжающемся росте ЧСС или симптомах обратись к кардиологу."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "baseline_walking_hr_bpm": round(baseline_whr, 1),
            "recent_walking_hr_bpm": round(recent_whr, 1),
            "rise_bpm": round(rise_bpm, 1),
            "measurements_count": len(points),
            "vo2max_also_declined": vo2max_declined,
        },
    )
