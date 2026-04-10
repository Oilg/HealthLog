from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.detectors.weight_activity._common import (
    _insufficient,
    _severity_from_score,
)
from health_log.analysis.detectors.weight_activity.constants import (
    BODY_FAT_THRESHOLDS_FEMALE,
    BODY_FAT_THRESHOLDS_MALE,
    MIN_WEIGHT_MEASUREMENTS,
    WAIST_THRESHOLDS_FEMALE,
    WAIST_THRESHOLDS_MALE,
)
from health_log.analysis.detectors.weight_activity.helpers import (
    compute_bmi,
    daily_medians,
    window_median,
)
from health_log.analysis.detectors.weight_activity.recommendations import (
    build_weight_activity_recommendations,
)
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import to_points


def assess_cardiometabolic_profile_risk(
    body_mass_rows: Iterable[tuple] | None = None,
    height_m: float | None = None,
    bmi_rows: Iterable[tuple] | None = None,
    body_fat_rows: Iterable[tuple] | None = None,
    waist_rows: Iterable[tuple] | None = None,
    step_rows: Iterable[tuple] | None = None,
    vo2max_rows: Iterable[tuple] | None = None,
    heart_rows: Iterable[tuple] | None = None,
    sbp_rows: Iterable[tuple] | None = None,
    *,
    sex: str = "male",
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=60)

    mass_points = [p for p in to_points(body_mass_rows or []) if p.timestamp >= cutoff]
    fat_points = [p for p in to_points(body_fat_rows or []) if p.timestamp >= cutoff]
    step_points = [p for p in to_points(step_rows or []) if p.timestamp >= cutoff]
    hr_points = [p for p in to_points(heart_rows or []) if p.timestamp >= cutoff]
    sbp_points = [p for p in to_points(sbp_rows or []) if p.timestamp >= cutoff]
    bmi_points = [p for p in to_points(bmi_rows or []) if p.timestamp >= cutoff]
    vo2_points = [p for p in to_points(vo2max_rows or []) if p.timestamp >= cutoff]

    components: list[float] = []
    component_names: list[str] = []

    bmi_val: float | None
    if bmi_points:
        bmi_val = median([p.value for p in bmi_points])
    elif mass_points and height_m is not None:
        bmi_val = compute_bmi(median([p.value for p in mass_points]), height_m)
    else:
        bmi_val = None
    if bmi_val:
        comp = min(1.0, max(0.0, (bmi_val - 22) / 18))
        components.append(comp)
        component_names.append("bmi")

    if fat_points:
        thresholds = BODY_FAT_THRESHOLDS_FEMALE if sex == "female" else BODY_FAT_THRESHOLDS_MALE
        fat_pct = median([p.value for p in fat_points])
        comp = min(1.0, max(0.0, (fat_pct - thresholds["low"]) / 10))
        components.append(comp)
        component_names.append("body_fat")

    if step_points:
        daily_steps = daily_medians(step_points, cutoff, now)
        med_steps = median(daily_steps) if daily_steps else 5000.0
        comp = min(1.0, max(0.0, (5000 - med_steps) / 5000))
        components.append(comp)
        component_names.append("inactivity")

    if vo2_points:
        vo2_val = vo2_points[-1].value
        comp = min(1.0, max(0.0, (40 - vo2_val) / 20))
        components.append(comp)
        component_names.append("low_fitness")

    if hr_points:
        rest_hr = sorted([p.value for p in hr_points])
        low_20 = rest_hr[:max(1, int(len(rest_hr) * 0.2))]
        resting_hr = median(low_20)
        comp = min(1.0, max(0.0, (resting_hr - 55) / 25))
        components.append(comp)
        component_names.append("elevated_hr")

    if sbp_points:
        avg_sbp = median([p.value for p in sbp_points])
        comp = min(1.0, max(0.0, (avg_sbp - 120) / 40))
        components.append(comp)
        component_names.append("elevated_bp")

    if not components:
        return _insufficient("cardiometabolic_profile_risk", window, 0, "нет достаточных данных для составного сигнала")

    score = sum(components) / len(components)
    score = round(score, 3)
    severity = _severity_from_score(score)
    confidence = round(min(1.0, len(components) / 4.0), 3)

    recs = build_weight_activity_recommendations({
        "weight_issue": "bmi" in component_names,
        "fat_issue": "body_fat" in component_names,
        "low_activity": "inactivity" in component_names,
        "metabolic_risk": True,
        "cardiovascular_symptom_risk": "elevated_hr" in component_names or "elevated_bp" in component_names,
    })

    return RiskAssessment(
        condition="cardiometabolic_profile_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Составной кардиометаболический сигнал объединяет компоненты ИМТ, жировой массы, "
            "активности, фитнеса и сердечно-сосудистых показателей."
        ),
        summary=f"Подозрение на ухудшение кардиометаболического профиля: score {score:.2f} по {len(components)} компонентам ({', '.join(component_names)}).",
        recommendation="Проверь давление, глюкозу и липиды. При выраженном сигнале обратись к терапевту.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={"components_used": component_names, "component_scores": [round(c, 2) for c in components]},
        lifestyle_recommendations=recs,
    )




def assess_metabolic_syndrome_risk(
    waist_rows: Iterable[tuple] | None = None,
    sbp_rows: Iterable[tuple] | None = None,
    dbp_rows: Iterable[tuple] | None = None,
    body_mass_rows: Iterable[tuple] | None = None,
    height_m: float | None = None,
    bmi_rows: Iterable[tuple] | None = None,
    step_rows: Iterable[tuple] | None = None,
    *,
    sex: str = "male",
    has_abnormal_glucose: bool = False,
    has_abnormal_lipids: bool = False,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=60)

    waist_points = [p for p in to_points(waist_rows or []) if p.timestamp >= cutoff]
    sbp_points = [p for p in to_points(sbp_rows or []) if p.timestamp >= cutoff]
    dbp_points = [p for p in to_points(dbp_rows or []) if p.timestamp >= cutoff]
    mass_points = [p for p in to_points(body_mass_rows or []) if p.timestamp >= cutoff]
    step_points = [p for p in to_points(step_rows or []) if p.timestamp >= cutoff]
    bmi_points = [p for p in to_points(bmi_rows or []) if p.timestamp >= cutoff]

    criteria_count = 0
    met_criteria: list[str] = []

    if waist_points:
        waist_cm = median([p.value for p in waist_points])
        thresholds = WAIST_THRESHOLDS_FEMALE if sex == "female" else WAIST_THRESHOLDS_MALE
        if waist_cm >= thresholds["low"]:
            criteria_count += 1
            met_criteria.append(f"абдоминальное ожирение (талия {waist_cm:.0f} см)")

    if sbp_points:
        avg_sbp = median([p.value for p in sbp_points])
        avg_dbp = median([p.value for p in dbp_points]) if dbp_points else 0.0
        if avg_sbp >= 130 or avg_dbp >= 85:
            criteria_count += 1
            met_criteria.append(f"повышенное АД ({avg_sbp:.0f}/{avg_dbp:.0f} мм рт.ст.)")

    if step_points:
        daily_steps = daily_medians(step_points, cutoff, now)
        if median(daily_steps) < 5000:
            criteria_count += 1
            met_criteria.append(f"низкая активность ({median(daily_steps):.0f} шагов/день)")

    bmi_val_meta: float | None
    if bmi_points:
        bmi_val_meta = median([p.value for p in bmi_points])
    elif mass_points and height_m is not None:
        bmi_val_meta = compute_bmi(median([p.value for p in mass_points]), height_m)
    else:
        bmi_val_meta = None
    if bmi_val_meta and bmi_val_meta >= 30:
        criteria_count += 1
        met_criteria.append(f"ожирение (ИМТ {bmi_val_meta:.1f})")

    if has_abnormal_glucose:
        criteria_count += 1
        met_criteria.append("нарушение глюкозы")

    if has_abnormal_lipids:
        criteria_count += 1
        met_criteria.append("дислипидемия")

    if criteria_count == 0:
        return _insufficient("metabolic_syndrome_risk", window, 0, "нет достаточных данных для оценки")

    if criteria_count >= 4:
        severity, score = "high", 0.85
    elif criteria_count >= 3:
        severity, score = "medium", 0.65
    elif criteria_count >= 2:
        severity, score = "low", 0.35
    else:
        return RiskAssessment(
            condition="metabolic_syndrome_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, criteria_count / 4.0), 3),
            severity="none",
            interpretation="Признаков метаболического синдрома не выявлено (менее 2 критериев).",
            summary=f"Выявлен {criteria_count} критерий метаболического синдрома — ниже порога сигнала.",
            recommendation="Контролируй АД, вес и уровень активности.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"criteria_count": criteria_count},
        )

    labs_note = "" if (has_abnormal_glucose or has_abnormal_lipids) else " Оценка предварительная — данные анализов отсутствуют."
    confidence = round(min(1.0, criteria_count / 5.0), 3)

    recs = build_weight_activity_recommendations({
        "weight_issue": "ожирение" in str(met_criteria),
        "metabolic_risk": True,
        "low_activity": "активность" in str(met_criteria),
        "persistent_weight_gain": True,
    })

    return RiskAssessment(
        condition="metabolic_syndrome_risk",
        window=window,
        score=round(score, 3),
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Метаболический синдром — сочетание факторов, значительно повышающих риск диабета 2 типа "
            "и сердечно-сосудистых заболеваний." + labs_note
        ),
        summary=f"Подозрение на метаболический синдром: {criteria_count} из 5+ критериев. " + "; ".join(met_criteria) + ".",
        recommendation="Обратись к терапевту или эндокринологу. Проверь глюкозу, липиды и давление.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={"criteria_count": criteria_count, "criteria_met": met_criteria},
        lifestyle_recommendations=recs,
    )




def assess_cardiovascular_obesity_risk(
    body_mass_rows: Iterable[tuple] | None = None,
    height_m: float | None = None,
    bmi_rows: Iterable[tuple] | None = None,
    body_fat_rows: Iterable[tuple] | None = None,
    waist_rows: Iterable[tuple] | None = None,
    step_rows: Iterable[tuple] | None = None,
    vo2max_rows: Iterable[tuple] | None = None,
    heart_rows: Iterable[tuple] | None = None,
    sbp_rows: Iterable[tuple] | None = None,
    *,
    sex: str = "male",
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=60)

    mass_points = [p for p in to_points(body_mass_rows or []) if p.timestamp >= cutoff]
    bmi_points = [p for p in to_points(bmi_rows or []) if p.timestamp >= cutoff]
    step_points = [p for p in to_points(step_rows or []) if p.timestamp >= cutoff]
    vo2_points = [p for p in to_points(vo2max_rows or []) if p.timestamp >= cutoff]
    hr_points = [p for p in to_points(heart_rows or []) if p.timestamp >= cutoff]
    sbp_points = [p for p in to_points(sbp_rows or []) if p.timestamp >= cutoff]

    bmi_val = None
    if bmi_points:
        bmi_val = median([p.value for p in bmi_points])
    elif mass_points and height_m:
        bmi_val = compute_bmi(median([p.value for p in mass_points]), height_m)

    step_median = None
    if step_points:
        daily_steps = daily_medians(step_points, cutoff, now)
        step_median = median(daily_steps) if daily_steps else None

    overweight = bmi_val is not None and bmi_val >= 25
    inactive = step_median is not None and step_median < 5000

    if not overweight or not inactive:
        return RiskAssessment(
            condition="cardiovascular_obesity_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(mass_points) / 10.0), 3),
            severity="none",
            interpretation="Обязательные критерии (лишний вес + низкая активность) не выполнены.",
            summary="Сигнал не активирован: нет сочетания лишнего веса и низкой активности.",
            recommendation="Поддерживай здоровый вес и регулярную активность.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"bmi": round(bmi_val, 1) if bmi_val else None, "median_steps": round(step_median, 0) if step_median else None},
        )

    score = 0.35

    poor_vo2 = False
    high_resting_hr = False
    high_bp = False
    severe_obesity = bmi_val >= 35 if bmi_val else False

    if vo2_points:
        vo2_val = vo2_points[-1].value
        if vo2_val < 35:
            score = min(1.0, score + 0.15)
            poor_vo2 = True

    if hr_points:
        rest_hr = sorted([p.value for p in hr_points])
        low_20_hr = rest_hr[:max(1, int(len(rest_hr) * 0.2))]
        rhr = median(low_20_hr)
        if rhr > 75:
            score = min(1.0, score + 0.15)
            high_resting_hr = True

    if sbp_points:
        avg_sbp = median([p.value for p in sbp_points])
        if avg_sbp >= 140:
            score = min(1.0, score + 0.15)
            high_bp = True

    if severe_obesity:
        score = min(1.0, score + 0.15)

    score = round(score, 3)
    if score >= 0.75:
        severity = "high"
    elif score >= 0.45:
        severity = "medium"
    else:
        severity = "low"

    boosters = [x for x, flag in [
        ("низкий VO2 max", poor_vo2), ("высокий покоящийся пульс", high_resting_hr),
        ("высокое АД", high_bp), ("выраженное ожирение", severe_obesity),
    ] if flag]

    recs = build_weight_activity_recommendations({
        "weight_issue": True,
        "low_activity": True,
        "metabolic_risk": True,
        "cardiovascular_symptom_risk": high_bp or poor_vo2 or high_resting_hr,
        "persistent_weight_gain": severe_obesity,
    })

    return RiskAssessment(
        condition="cardiovascular_obesity_risk",
        window=window,
        score=score,
        confidence=round(min(1.0, (len(mass_points) + len(step_points)) / 20.0), 3),
        severity=severity,
        interpretation=(
            "Сочетание лишнего веса и низкой активности — базовый сердечно-сосудистый риск. "
            "Усиливается при низком VO2 max, высоком пульсе или давлении."
        ),
        summary=(
            f"Подозрение на повышенный кардиоваскулярный риск: ИМТ {bmi_val:.1f}, "
            f"шаги {step_median:.0f}/день"
            + (f". Усилители: {', '.join(boosters)}" if boosters else "")
            + "."
        ),
        recommendation=(
            "При нагрузочной симптоматике (одышка, перебои в сердце) обратись к кардиологу. "
            "Проверь давление, липиды, глюкозу."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "bmi": round(bmi_val, 1) if bmi_val else None,
            "median_steps": round(step_median, 0) if step_median else None,
            "poor_vo2max": poor_vo2,
            "high_resting_hr": high_resting_hr,
            "high_bp": high_bp,
        },
        lifestyle_recommendations=recs,
    )




def assess_fitness_weight_gain_risk(
    body_mass_rows: Iterable[tuple],
    vo2max_rows: Iterable[tuple] | None = None,
    walking_hr_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or datetime.utcnow()
    cutoff_90d = now - timedelta(days=90)
    mass_points = sorted([p for p in to_points(body_mass_rows) if p.timestamp >= cutoff_90d], key=lambda p: p.timestamp)
    vo2_points = sorted([p for p in to_points(vo2max_rows or []) if p.timestamp >= cutoff_90d], key=lambda p: p.timestamp)
    whr_points = sorted([p for p in to_points(walking_hr_rows or []) if p.timestamp >= cutoff_90d], key=lambda p: p.timestamp)

    if len(mass_points) < MIN_WEIGHT_MEASUREMENTS:
        return _insufficient("fitness_weight_gain_risk", window, len(mass_points), "мало измерений веса")

    start_med = window_median(mass_points, cutoff_90d, cutoff_90d + timedelta(days=14))
    end_med = window_median(mass_points, now - timedelta(days=14), now)

    if start_med is None or end_med is None or start_med <= 0:
        return _insufficient("fitness_weight_gain_risk", window, len(mass_points), "недостаточно точек для сглаживания")

    weight_change_pct = (end_med - start_med) / start_med * 100

    vo2_decline_pct = 0.0
    if len(vo2_points) >= 2:
        vo2_base = median([p.value for p in vo2_points[:max(1, len(vo2_points) // 2)]])
        vo2_recent = vo2_points[-1].value
        if vo2_base > 0:
            vo2_decline_pct = (vo2_base - vo2_recent) / vo2_base * 100

    whr_delta = 0.0
    if len(whr_points) >= 4:
        whr_base = median([p.value for p in whr_points[:len(whr_points) // 2]])
        whr_recent = median([p.value for p in whr_points[len(whr_points) // 2:]])
        whr_delta = whr_recent - whr_base

    if weight_change_pct >= 5 and vo2_decline_pct >= 10 and whr_delta >= 10:
        severity, score = "high", 0.85
    elif weight_change_pct >= 5 and vo2_decline_pct >= 10:
        severity, score = "medium", 0.65
    elif weight_change_pct >= 3 and vo2_decline_pct >= 5:
        severity, score = "low", 0.35
    else:
        return RiskAssessment(
            condition="fitness_weight_gain_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(mass_points) / 10.0), 3),
            severity="none",
            interpretation="Сочетания набора веса и снижения фитнеса не выявлено.",
            summary=f"Вес изменился на {weight_change_pct:+.1f}%, VO2 max на {-vo2_decline_pct:.1f}%.",
            recommendation="Поддерживай регулярные аэробные нагрузки и контролируй вес.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={
                "weight_change_pct": round(weight_change_pct, 1),
                "vo2max_decline_pct": round(vo2_decline_pct, 1),
                "walking_hr_delta": round(whr_delta, 1),
            },
        )

    recs = build_weight_activity_recommendations({
        "weight_issue": True,
        "low_activity": True,
        "cardiovascular_symptom_risk": whr_delta >= 10,
    })

    return RiskAssessment(
        condition="fitness_weight_gain_risk",
        window=window,
        score=round(score, 3),
        confidence=round(min(1.0, len(mass_points) / 10.0), 3),
        severity=severity,
        interpretation=(
            "Одновременный набор веса и ухудшение кардиофитнеса — неблагоприятная комбинация, "
            "усиливающая кардиоваскулярный риск."
        ),
        summary=(
            f"Подозрение на ухудшение формы на фоне набора веса: "
            f"вес +{weight_change_pct:.1f}%, VO2 max −{vo2_decline_pct:.1f}%"
            + (f", пульс при ходьбе +{whr_delta:.0f} уд/мин" if whr_delta >= 5 else "")
            + "."
        ),
        recommendation=(
            "Увеличь аэробные нагрузки и пересмотри питание. "
            "При одышке или высоком пульсе при нагрузке обратись к кардиологу."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "weight_change_pct": round(weight_change_pct, 1),
            "vo2max_decline_pct": round(vo2_decline_pct, 1),
            "walking_hr_delta": round(whr_delta, 1),
        },
        lifestyle_recommendations=recs,
    )




def assess_recovery_obesity_risk(
    body_mass_rows: Iterable[tuple] | None = None,
    height_m: float | None = None,
    bmi_rows: Iterable[tuple] | None = None,
    body_fat_rows: Iterable[tuple] | None = None,
    step_rows: Iterable[tuple] | None = None,
    sleep_segments: list[tuple[datetime, datetime]] | None = None,
    hrv_rows: Iterable[tuple] | None = None,
    heart_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:

    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=60)
    recent_start = now - timedelta(days=14)

    mass_points = [p for p in to_points(body_mass_rows or []) if p.timestamp >= cutoff]
    bmi_points = [p for p in to_points(bmi_rows or []) if p.timestamp >= cutoff]
    step_points = [p for p in to_points(step_rows or []) if p.timestamp >= cutoff]
    hrv_points = [p for p in to_points(hrv_rows or []) if p.timestamp >= cutoff]
    hr_points = [p for p in to_points(heart_rows or []) if p.timestamp >= cutoff]
    segments = list(sleep_segments or [])

    bmi_val = None
    if bmi_points:
        bmi_val = median([p.value for p in bmi_points])
    elif mass_points and height_m:
        bmi_val = compute_bmi(median([p.value for p in mass_points]), height_m)

    step_median = None
    if step_points:
        daily_steps = daily_medians(step_points, cutoff, now)
        step_median = median(daily_steps) if daily_steps else None

    overweight = bmi_val is not None and bmi_val >= 25
    inactive = step_median is not None and step_median < 5000

    if not overweight or not inactive:
        return RiskAssessment(
            condition="recovery_obesity_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="none",
            interpretation="Обязательные критерии (лишний вес + низкая активность) не выполнены.",
            summary="Сигнал не активирован.",
            recommendation="Поддерживай здоровый вес и активность.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    recovery_flags = 0

    if hrv_points:
        baseline_hrv = [p.value for p in hrv_points if p.timestamp < recent_start]
        recent_hrv = [p.value for p in hrv_points if p.timestamp >= recent_start]
        if baseline_hrv and recent_hrv:
            b = median(baseline_hrv)
            r = median(recent_hrv)
            if b > 0 and r <= b * 0.85:
                recovery_flags += 1

    if segments:
        from health_log.analysis.detectors.fitness.overload_recovery import _sleep_hours_per_day
        baseline_sleep = _sleep_hours_per_day([(s, e) for s, e in segments if s and s < recent_start])
        recent_sleep = _sleep_hours_per_day([(s, e) for s, e in segments if s and s >= recent_start])
        if baseline_sleep and recent_sleep:
            b_sleep = median(baseline_sleep.values())
            r_sleep = median(recent_sleep.values())
            if b_sleep - r_sleep >= 1.0:
                recovery_flags += 1

    if hr_points:
        baseline_hr_vals = [p.value for p in hr_points if p.timestamp < recent_start]
        recent_hr_vals = [p.value for p in hr_points if p.timestamp >= recent_start]
        if baseline_hr_vals and recent_hr_vals:
            if median(recent_hr_vals) >= median(baseline_hr_vals) + 5:
                recovery_flags += 1

    if recovery_flags >= 3:
        severity, score = "high", 0.85
    elif recovery_flags >= 2:
        severity, score = "medium", 0.65
    elif recovery_flags >= 1:
        severity, score = "low", 0.35
    else:
        return RiskAssessment(
            condition="recovery_obesity_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(mass_points) / 10.0), 3),
            severity="none",
            interpretation="Нарушений восстановления на фоне лишнего веса не выявлено.",
            summary="Показатели восстановления в норме.",
            recommendation="Поддерживай режим сна и умеренную активность.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"bmi": round(bmi_val, 1) if bmi_val else None, "recovery_flags": recovery_flags},
        )

    recs = build_weight_activity_recommendations({
        "weight_issue": True,
        "low_activity": True,
        "sedentary": inactive,
    })

    return RiskAssessment(
        condition="recovery_obesity_risk",
        window=window,
        score=round(score, 3),
        confidence=round(min(1.0, len(mass_points) / 10.0), 3),
        severity=severity,
        interpretation=(
            "Нарушение восстановления на фоне лишнего веса и низкой активности — "
            "неблагоприятная комбинация для долгосрочного здоровья."
        ),
        summary=f"Подозрение на нарушение восстановления: {recovery_flags} флага(ов) (HRV, сон, пульс) на фоне ИМТ {bmi_val:.1f}.",
        recommendation="Улучши качество сна, добавь умеренную ходьбу и силовые тренировки.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "bmi": round(bmi_val, 1) if bmi_val else None,
            "median_daily_steps": round(step_median, 0) if step_median else None,
            "recovery_flags": recovery_flags,
        },
        lifestyle_recommendations=recs,
    )


