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


def assess_hrr_decline_risk(
    hrr_rows: Iterable[tuple],
    vo2max_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    cutoff = now - timedelta(days=_LOOKBACK_DAYS)
    points = sorted(
        [p for p in to_points(hrr_rows) if p.timestamp >= cutoff],
        key=lambda p: p.timestamp,
    )

    if len(points) < _MIN_MEASUREMENTS:
        return RiskAssessment(
            condition="hrr_decline_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных восстановления пульса для оценки.",
            summary=(
                f"Найдено {len(points)} записей HRR за {_LOOKBACK_DAYS} дней "
                f"(нужно ≥{_MIN_MEASUREMENTS})."
            ),
            recommendation="Проверь наличие данных heart rate recovery в Apple Health.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"measurements_count": len(points)},
        )

    split_idx = max(1, int(len(points) * 0.6))
    baseline_points = points[:split_idx]
    recent_points = points[split_idx:]

    baseline_hrr = median([p.value for p in baseline_points])
    recent_hrr = median([p.value for p in recent_points])
    decline_bpm = baseline_hrr - recent_hrr

    if decline_bpm >= 12:
        severity = "high"
        score_base = 0.85
    elif decline_bpm >= 8:
        severity = "medium"
        score_base = 0.65
    elif decline_bpm >= 5:
        severity = "low"
        score_base = 0.35
    else:
        return RiskAssessment(
            condition="hrr_decline_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(points) / 10.0), 3),
            severity="none",
            interpretation="Значимого снижения восстановления пульса не выявлено.",
            summary=(
                f"HRR стабилен: baseline {baseline_hrr:.1f} уд/мин, "
                f"recent {recent_hrr:.1f} уд/мин (Δ={decline_bpm:.1f})."
            ),
            recommendation="Поддерживай регулярные аэробные тренировки.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={
                "baseline_hrr": round(baseline_hrr, 1),
                "recent_hrr": round(recent_hrr, 1),
                "decline_bpm": round(decline_bpm, 1),
            },
        )

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
        condition="hrr_decline_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Снижение восстановления пульса после нагрузки может отражать ухудшение "
            "вегетативной регуляции или кардиофитнеса. Требует наблюдения."
        ),
        summary=(
            f"Подозрение на ухудшение восстановления: HRR снизился с {baseline_hrr:.1f} до "
            f"{recent_hrr:.1f} уд/мин (−{decline_bpm:.1f} уд/мин)."
            + (" VO2 max также снижается." if vo2max_declined else "")
        ),
        recommendation=(
            "Убедись в полноценном восстановлении между тренировками. "
            "При продолжающемся снижении или симптомах обратись к кардиологу."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "baseline_hrr_bpm": round(baseline_hrr, 1),
            "recent_hrr_bpm": round(recent_hrr, 1),
            "decline_bpm": round(decline_bpm, 1),
            "measurements_count": len(points),
            "vo2max_also_declined": vo2max_declined,
        },
    )
