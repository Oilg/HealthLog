from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.detectors.weight_activity._common import (
    _insufficient,
)
from health_log.analysis.detectors.weight_activity.constants import (
    MIN_FAT_MEASUREMENTS,
    MIN_LEAN_MEASUREMENTS,
    MIN_WEIGHT_MEASUREMENTS,
)
from health_log.analysis.detectors.weight_activity.helpers import (
    window_median,
)
from health_log.analysis.detectors.weight_activity.recommendations import (
    build_weight_activity_recommendations,
)
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import EventPoint, to_points
from health_log.utils import utcnow


def assess_lean_mass_decline_risk(
    lean_mass_rows: Iterable[tuple],
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    cutoff = now - timedelta(days=60)
    points = sorted(
        [p for p in to_points(lean_mass_rows) if p.timestamp >= cutoff],
        key=lambda p: p.timestamp,
    )

    if len(points) < MIN_LEAN_MEASUREMENTS:
        return _insufficient("lean_mass_decline_risk", window, len(points), "мало измерений безжировой массы")

    baseline_val = median([p.value for p in points[:max(1, len(points) // 2)]])
    recent_val = median([p.value for p in points[len(points) // 2:]])

    if baseline_val <= 0:
        return _insufficient("lean_mass_decline_risk", window, len(points), "нулевые значения безжировой массы")

    decline_pct = (baseline_val - recent_val) / baseline_val * 100

    if decline_pct >= 8:
        severity, score = "high", 0.85
    elif decline_pct >= 5:
        severity, score = "medium", 0.65
    elif decline_pct >= 3:
        severity, score = "low", 0.35
    else:
        return RiskAssessment(
            condition="lean_mass_decline_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(points) / 6.0), 3),
            severity="none",
            interpretation="Значимого снижения безжировой массы не выявлено.",
            summary=f"Безжировая масса стабильна: {recent_val:.1f} кг.",
            recommendation="Поддерживай силовые тренировки и достаточное потребление белка.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"recent_lean_kg": round(recent_val, 1), "decline_pct": round(decline_pct, 1)},
        )

    recs = build_weight_activity_recommendations({
        "lean_mass_issue": True,
        "fat_issue": False,
        "low_activity": True,
    })

    return RiskAssessment(
        condition="lean_mass_decline_risk",
        window=window,
        score=round(score, 3),
        confidence=round(min(1.0, len(points) / 6.0), 3),
        severity=severity,
        interpretation=(
            "Снижение безжировой массы может указывать на саркопению, недостаточность питания "
            "или снижение физической активности."
        ),
        summary=f"Подозрение на снижение безжировой массы: −{decline_pct:.1f}% ({baseline_val:.1f} → {recent_val:.1f} кг).",
        recommendation="Добавь силовые тренировки и увеличь потребление белка. Обратись к терапевту при выраженном снижении.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "baseline_lean_kg": round(baseline_val, 1),
            "recent_lean_kg": round(recent_val, 1),
            "decline_pct": round(decline_pct, 1),
            "measurements_count": len(points),
        },
        lifestyle_recommendations=recs,
    )




def assess_weight_trend_risk(
    body_mass_rows: Iterable[tuple],
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    points = sorted(to_points(body_mass_rows), key=lambda p: p.timestamp)

    if len(points) < MIN_WEIGHT_MEASUREMENTS:
        return _insufficient("weight_trend_risk", window, len(points), "мало измерений веса")

    def _edge_median(pts: list[EventPoint], start: datetime, days: int) -> float | None:
        end = start + timedelta(days=days)
        window_pts = [p.value for p in pts if start <= p.timestamp <= end]
        return median(window_pts) if window_pts else None

    high_threshold_pct = 10.0
    medium_threshold_pct = 5.0
    low_threshold_pct = 2.0

    for horizon_days, threshold_pct, sev in [
        (180, high_threshold_pct, "high"),
        (90, medium_threshold_pct, "medium"),
        (30, low_threshold_pct, "low"),
    ]:
        if (now - points[0].timestamp).days < horizon_days:
            continue
        cutoff = now - timedelta(days=horizon_days)
        start_med = _edge_median(points, cutoff, 14)
        end_start = now - timedelta(days=14)
        end_med = _edge_median(points, end_start, 14)
        if start_med is None or end_med is None or start_med <= 0:
            continue
        change_pct = (end_med - start_med) / start_med * 100
        if change_pct >= threshold_pct:
            score = round(min(1.0, 0.35 + (change_pct - threshold_pct) * 0.02), 3)
            recs = build_weight_activity_recommendations({
                "weight_issue": True,
                "persistent_weight_gain": True,
                "metabolic_risk": True,
            })
            return RiskAssessment(
                condition="weight_trend_risk",
                window=window,
                score=score,
                confidence=round(min(1.0, len(points) / 15.0), 3),
                severity=sev,
                interpretation=(
                    "Устойчивый набор веса связан с повышенным риском метаболических нарушений."
                ),
                summary=(
                    f"Подозрение на неблагоприятную динамику веса: +{change_pct:.1f}% "
                    f"за {horizon_days} дней ({start_med:.1f} → {end_med:.1f} кг)."
                ),
                recommendation="Обратись к терапевту при устойчивом наборе веса.",
                clinical_safety_note=CLINICAL_SAFETY_NOTE,
                supporting_metrics={
                    "start_weight_kg": round(start_med, 1),
                    "end_weight_kg": round(end_med, 1),
                    "change_pct": round(change_pct, 1),
                    "horizon_days": horizon_days,
                },
                lifestyle_recommendations=recs,
            )

    return RiskAssessment(
        condition="weight_trend_risk",
        window=window,
        score=0.0,
        confidence=round(min(1.0, len(points) / 15.0), 3),
        severity="none",
        interpretation="Неблагоприятной динамики веса не выявлено.",
        summary="Динамика веса в норме.",
        recommendation="Продолжай наблюдение за весом.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={"measurements_count": len(points)},
    )




def assess_fat_mass_trend_risk(
    body_mass_rows: Iterable[tuple],
    body_fat_rows: Iterable[tuple],
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    cutoff_90d = now - timedelta(days=90)

    mass_points = sorted([p for p in to_points(body_mass_rows) if p.timestamp >= cutoff_90d], key=lambda p: p.timestamp)
    fat_points = sorted([p for p in to_points(body_fat_rows) if p.timestamp >= cutoff_90d], key=lambda p: p.timestamp)

    if len(mass_points) < MIN_WEIGHT_MEASUREMENTS or len(fat_points) < MIN_FAT_MEASUREMENTS:
        return _insufficient(
            "fat_mass_trend_risk",
            window,
            min(len(mass_points), len(fat_points)),
            "мало измерений веса или жировой массы",
        )

    def fat_mass_kg(mass_pts: list[EventPoint], fat_pts: list[EventPoint], start: datetime, end: datetime) -> float | None:
        m = window_median(mass_pts, start, end)
        f = window_median(fat_pts, start, end)
        if m is None or f is None:
            return None
        return m * f / 100.0

    start_fat = fat_mass_kg(mass_points, fat_points, cutoff_90d, cutoff_90d + timedelta(days=14))
    end_fat = fat_mass_kg(mass_points, fat_points, now - timedelta(days=14), now)

    if start_fat is None or end_fat is None or start_fat <= 0:
        return _insufficient("fat_mass_trend_risk", window, len(fat_points), "недостаточно точек для сглаживания")

    change_pct = (end_fat - start_fat) / start_fat * 100

    if change_pct >= 15:
        severity, score = "high", 0.85
    elif change_pct >= 10:
        severity, score = "medium", 0.65
    elif change_pct >= 5:
        severity, score = "low", 0.35
    else:
        return RiskAssessment(
            condition="fat_mass_trend_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(fat_points) / 10.0), 3),
            severity="none",
            interpretation="Значимого роста жировой массы за 90 дней не выявлено.",
            summary=f"Жировая масса стабильна: {start_fat:.1f} → {end_fat:.1f} кг (Δ={change_pct:+.1f}%).",
            recommendation="Продолжай контролировать состав тела.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"fat_mass_start_kg": round(start_fat, 1), "fat_mass_end_kg": round(end_fat, 1), "change_pct": round(change_pct, 1)},
        )

    recs = build_weight_activity_recommendations({
        "fat_issue": True,
        "lean_mass_issue": False,
        "low_activity": True,
        "persistent_weight_gain": True,
    })

    return RiskAssessment(
        condition="fat_mass_trend_risk",
        window=window,
        score=round(score, 3),
        confidence=round(min(1.0, len(fat_points) / 10.0), 3),
        severity=severity,
        interpretation="Устойчивый рост жировой массы связан с метаболическими и сердечно-сосудистыми рисками.",
        summary=f"Подозрение на рост жировой массы: {start_fat:.1f} → {end_fat:.1f} кг (+{change_pct:.1f}%) за 90 дней.",
        recommendation="Пересмотри питание и увеличь физическую активность. При выраженном росте обратись к врачу.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "fat_mass_start_kg": round(start_fat, 1),
            "fat_mass_end_kg": round(end_fat, 1),
            "change_pct": round(change_pct, 1),
        },
        lifestyle_recommendations=recs,
    )




def assess_body_composition_trend_risk(
    body_mass_rows: Iterable[tuple],
    body_fat_rows: Iterable[tuple],
    lean_mass_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    cutoff = now - timedelta(days=90)

    mass_points = sorted([p for p in to_points(body_mass_rows) if p.timestamp >= cutoff], key=lambda p: p.timestamp)
    fat_points = sorted([p for p in to_points(body_fat_rows) if p.timestamp >= cutoff], key=lambda p: p.timestamp)
    lean_points = sorted([p for p in to_points(lean_mass_rows or []) if p.timestamp >= cutoff], key=lambda p: p.timestamp)

    if len(mass_points) < MIN_WEIGHT_MEASUREMENTS or len(fat_points) < MIN_FAT_MEASUREMENTS:
        return _insufficient("body_composition_trend_risk", window, min(len(mass_points), len(fat_points)), "мало данных состава тела")

    start_wt_pts = [p.value for p in mass_points if p.timestamp <= cutoff + timedelta(days=14)]
    end_wt_pts = [p.value for p in mass_points if p.timestamp >= now - timedelta(days=14)]
    start_fat_pts = [p.value for p in fat_points if p.timestamp <= cutoff + timedelta(days=14)]
    end_fat_pts = [p.value for p in fat_points if p.timestamp >= now - timedelta(days=14)]

    if not (start_wt_pts and end_wt_pts and start_fat_pts and end_fat_pts):
        return _insufficient("body_composition_trend_risk", window, len(mass_points), "недостаточно точек на границах")

    weight_change_pct = (median(end_wt_pts) - median(start_wt_pts)) / median(start_wt_pts) * 100
    fat_pp_change = median(end_fat_pts) - median(start_fat_pts)

    lean_decline_pct = 0.0
    if len(lean_points) >= 2:
        start_lean = median([p.value for p in lean_points[:max(1, len(lean_points) // 2)]])
        end_lean = median([p.value for p in lean_points[len(lean_points) // 2:]])
        if start_lean > 0:
            lean_decline_pct = (start_lean - end_lean) / start_lean * 100

    weight_stable = abs(weight_change_pct) <= 2.0
    fat_rising = fat_pp_change >= 2.0
    lean_falling = lean_decline_pct >= 3.0

    if weight_stable and fat_rising and lean_falling and fat_pp_change >= 4 and lean_decline_pct >= 5:
        severity, score = "high", 0.85
    elif weight_stable and fat_rising and lean_falling:
        severity, score = "medium", 0.65
    elif weight_stable and (fat_rising or lean_falling):
        severity, score = "low", 0.35
    else:
        return RiskAssessment(
            condition="body_composition_trend_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(fat_points) / 10.0), 3),
            severity="none",
            interpretation="Неблагоприятного тренда состава тела не выявлено.",
            summary=(
                f"Состав тела стабилен: вес {weight_change_pct:+.1f}%, жир {fat_pp_change:+.1f} п.п."
            ),
            recommendation="Продолжай контролировать состав тела.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={
                "weight_change_pct": round(weight_change_pct, 1),
                "fat_pct_point_change": round(fat_pp_change, 1),
                "lean_decline_pct": round(lean_decline_pct, 1),
            },
        )

    recs = build_weight_activity_recommendations({
        "fat_issue": fat_rising,
        "lean_mass_issue": lean_falling,
        "low_activity": True,
    })

    return RiskAssessment(
        condition="body_composition_trend_risk",
        window=window,
        score=round(score, 3),
        confidence=round(min(1.0, len(fat_points) / 10.0), 3),
        severity=severity,
        interpretation=(
            "При стабильном весе рост жировой массы и снижение безжировой — "
            "признак реакомпозиции тела в неблагоприятном направлении (саркопеническое ожирение)."
        ),
        summary=(
            f"Подозрение на неблагоприятный тренд состава тела: вес стабилен ({weight_change_pct:+.1f}%), "
            f"жир {fat_pp_change:+.1f} п.п., безжировая −{lean_decline_pct:.1f}%."
        ),
        recommendation="Добавь силовые тренировки, увеличь белок в питании. При выраженных изменениях обратись к врачу.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "weight_change_pct": round(weight_change_pct, 1),
            "fat_pct_point_change": round(fat_pp_change, 1),
            "lean_decline_pct": round(lean_decline_pct, 1),
        },
        lifestyle_recommendations=recs,
    )
