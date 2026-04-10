from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.detectors.weight_activity._common import (
    _insufficient,
)
from health_log.analysis.detectors.weight_activity.constants import (
    BMI_OBESITY_HIGH,
    BMI_OBESITY_MEDIUM,
    BMI_OVERWEIGHT_HIGH,
    BMI_OVERWEIGHT_LOW,
    BODY_FAT_THRESHOLDS_FEMALE,
    BODY_FAT_THRESHOLDS_MALE,
    MIN_FAT_MEASUREMENTS,
    MIN_WEIGHT_DAYS,
    MIN_WEIGHT_MEASUREMENTS,
    WAIST_THRESHOLDS_FEMALE,
    WAIST_THRESHOLDS_MALE,
)
from health_log.analysis.detectors.weight_activity.helpers import (
    compute_bmi,
)
from health_log.analysis.detectors.weight_activity.recommendations import (
    build_weight_activity_recommendations,
)
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import to_points


def assess_overweight_risk(
    body_mass_rows: Iterable[tuple],
    height_m: float | None = None,
    bmi_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=MIN_WEIGHT_DAYS)

    mass_points = [p for p in to_points(body_mass_rows) if p.timestamp >= cutoff]
    bmi_points = [p for p in to_points(bmi_rows or []) if p.timestamp >= cutoff]

    bmi_val: float | None
    if bmi_points:
        bmi_val = median([p.value for p in bmi_points])
    elif mass_points and height_m and height_m > 0:
        avg_mass = median([p.value for p in mass_points])
        bmi_val = compute_bmi(avg_mass, height_m)
    else:
        bmi_val = None

    if len(mass_points) < MIN_WEIGHT_MEASUREMENTS and not bmi_points:
        return _insufficient("overweight_risk", window, len(mass_points), "мало измерений веса")

    if bmi_val is None:
        return _insufficient("overweight_risk", window, 0, "нет данных роста или ИМТ")

    if bmi_val >= BMI_OVERWEIGHT_HIGH:
        return RiskAssessment(
            condition="overweight_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(mass_points) / 10.0), 3),
            severity="none",
            interpretation="Сигнал избыточного веса не применим: ИМТ ≥30 относится к категории ожирения.",
            summary=f"ИМТ {bmi_val:.1f} — категория ожирения, оцени сигнал obesity_risk.",
            recommendation="Обратись к терапевту или эндокринологу.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"bmi": round(bmi_val, 1)},
        )

    if bmi_val >= BMI_OVERWEIGHT_LOW:
        recs = build_weight_activity_recommendations({"weight_issue": True})
        return RiskAssessment(
            condition="overweight_risk",
            window=window,
            score=0.35,
            confidence=round(min(1.0, len(mass_points) / 10.0), 3),
            severity="low",
            interpretation="ИМТ в диапазоне избыточной массы тела (25.0–29.9).",
            summary=f"ИМТ {bmi_val:.1f} — избыточная масса тела.",
            recommendation="Наблюдай динамику веса и пересмотри питание и физическую активность.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"bmi": round(bmi_val, 1), "weight_measurements": len(mass_points)},
            lifestyle_recommendations=recs,
        )

    return RiskAssessment(
        condition="overweight_risk",
        window=window,
        score=0.0,
        confidence=round(min(1.0, len(mass_points) / 10.0), 3),
        severity="none",
        interpretation="ИМТ в пределах нормы.",
        summary=f"ИМТ {bmi_val:.1f} — норма.",
        recommendation="Поддерживай здоровый вес.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={"bmi": round(bmi_val, 1)},
    )




def assess_obesity_risk(
    body_mass_rows: Iterable[tuple],
    height_m: float | None = None,
    bmi_rows: Iterable[tuple] | None = None,
    body_fat_rows: Iterable[tuple] | None = None,
    step_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=MIN_WEIGHT_DAYS)

    mass_points = [p for p in to_points(body_mass_rows) if p.timestamp >= cutoff]
    bmi_points = [p for p in to_points(bmi_rows or []) if p.timestamp >= cutoff]
    fat_points = [p for p in to_points(body_fat_rows or []) if p.timestamp >= cutoff]
    step_points = [p for p in to_points(step_rows or []) if p.timestamp >= cutoff]

    bmi_val: float | None
    if bmi_points:
        bmi_val = median([p.value for p in bmi_points])
    elif mass_points and height_m and height_m > 0:
        bmi_val = compute_bmi(median([p.value for p in mass_points]), height_m)
    else:
        bmi_val = None

    if len(mass_points) < MIN_WEIGHT_MEASUREMENTS and not bmi_points:
        return _insufficient("obesity_risk", window, len(mass_points), "мало измерений веса")

    if bmi_val is None or bmi_val < BMI_OVERWEIGHT_HIGH:
        return RiskAssessment(
            condition="obesity_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(mass_points) / 10.0), 3),
            severity="none",
            interpretation="ИМТ ниже порога ожирения (30).",
            summary=f"ИМТ {bmi_val:.1f} — ожирения нет." if bmi_val else "Нет данных ИМТ.",
            recommendation="Поддерживай здоровый вес.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"bmi": round(bmi_val, 1) if bmi_val else None},
        )

    if bmi_val >= BMI_OBESITY_HIGH:
        severity, score_base = "high", 0.9
    elif bmi_val >= BMI_OBESITY_MEDIUM:
        severity, score_base = "medium", 0.7
    else:
        severity, score_base = "low", 0.45

    score = score_base
    median_steps = median([p.value for p in step_points]) if step_points else None
    fat_pct = median([p.value for p in fat_points]) if fat_points else None
    low_activity = median_steps is not None and median_steps < 5000

    if fat_pct is not None and fat_pct > 30 and low_activity:
        score = min(1.0, score + 0.1)

    score = round(score, 3)
    recs = build_weight_activity_recommendations({
        "weight_issue": True,
        "fat_issue": fat_pct is not None,
        "low_activity": low_activity,
        "metabolic_risk": True,
        "persistent_weight_gain": True,
    })

    return RiskAssessment(
        condition="obesity_risk",
        window=window,
        score=score,
        confidence=round(min(1.0, len(mass_points) / 10.0), 3),
        severity=severity,
        interpretation=(
            "Ожирение повышает риск сердечно-сосудистых заболеваний, диабета 2 типа и других состояний. "
            "Требуется профессиональная оценка и комплексный подход к снижению веса."
        ),
        summary=(
            f"Подозрение на ожирение: ИМТ {bmi_val:.1f}"
            + (f", жировая масса {fat_pct:.1f}%" if fat_pct else "")
            + (f", средние шаги {median_steps:.0f}/день" if median_steps else "")
            + "."
        ),
        recommendation="Обратись к терапевту или эндокринологу для оценки и составления плана снижения веса.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "bmi": round(bmi_val, 1),
            "body_fat_pct": round(fat_pct, 1) if fat_pct else None,
            "median_daily_steps": round(median_steps, 0) if median_steps else None,
        },
        lifestyle_recommendations=recs,
    )




def assess_high_body_fat_risk(
    body_fat_rows: Iterable[tuple],
    *,
    sex: str = "male",
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=MIN_WEIGHT_DAYS)
    fat_points = [p for p in to_points(body_fat_rows) if p.timestamp >= cutoff]

    if len(fat_points) < MIN_FAT_MEASUREMENTS:
        return _insufficient("high_body_fat_risk", window, len(fat_points), "мало измерений жировой массы")

    fat_pct = median([p.value for p in fat_points])
    thresholds = BODY_FAT_THRESHOLDS_FEMALE if sex == "female" else BODY_FAT_THRESHOLDS_MALE

    if fat_pct > thresholds["high"]:
        severity, score = "high", 0.85
    elif fat_pct > thresholds["medium"]:
        severity, score = "medium", 0.65
    elif fat_pct > thresholds["low"]:
        severity, score = "low", 0.35
    else:
        return RiskAssessment(
            condition="high_body_fat_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(fat_points) / 10.0), 3),
            severity="none",
            interpretation="Процент жира в норме.",
            summary=f"Жировая масса {fat_pct:.1f}% — норма для {'женщин' if sex == 'female' else 'мужчин'}.",
            recommendation="Продолжай контролировать состав тела.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"body_fat_pct": round(fat_pct, 1), "sex": sex},
        )

    recs = build_weight_activity_recommendations({
        "fat_issue": True,
        "lean_mass_issue": True,
        "low_activity": True,
    })

    return RiskAssessment(
        condition="high_body_fat_risk",
        window=window,
        score=round(score, 3),
        confidence=round(min(1.0, len(fat_points) / 10.0), 3),
        severity=severity,
        interpretation=(
            f"Повышенный процент жира для {'женщин' if sex == 'female' else 'мужчин'} "
            f"(порог: >{thresholds['low']:.0f}%). Может указывать на риск метаболических нарушений."
        ),
        summary=f"Подозрение на высокий процент жира: {fat_pct:.1f}% (порог >{thresholds['low']:.0f}% для {'женщин' if sex == 'female' else 'мужчин'}).",
        recommendation="Добавь силовые тренировки и пересмотри питание. При высоком значении обратись к врачу.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={"body_fat_pct": round(fat_pct, 1), "sex": sex},
        lifestyle_recommendations=recs,
    )




def assess_abdominal_obesity_risk(
    waist_rows: Iterable[tuple],
    *,
    sex: str = "male",
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=MIN_WEIGHT_DAYS)
    waist_points = [p for p in to_points(waist_rows) if p.timestamp >= cutoff]

    if not waist_points:
        return RiskAssessment(
            condition="abdominal_obesity_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Нет данных об окружности талии — сигнал не строится.",
            summary="Данные окружности талии отсутствуют.",
            recommendation="Добавь измерения окружности талии в Apple Health.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    waist_cm = median([p.value for p in waist_points])
    thresholds = WAIST_THRESHOLDS_FEMALE if sex == "female" else WAIST_THRESHOLDS_MALE

    if waist_cm >= thresholds["high"]:
        severity, score = "high", 0.85
    elif waist_cm >= thresholds["low"]:
        severity, score = "low", 0.35
    else:
        return RiskAssessment(
            condition="abdominal_obesity_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(waist_points) / 5.0), 3),
            severity="none",
            interpretation="Окружность талии в норме.",
            summary=f"Талия {waist_cm:.0f} см — норма для {'женщин' if sex == 'female' else 'мужчин'}.",
            recommendation="Продолжай контролировать объём талии.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"waist_cm": round(waist_cm, 1)},
        )

    recs = build_weight_activity_recommendations({
        "fat_issue": True,
        "waist_available": True,
        "metabolic_risk": True,
    })

    return RiskAssessment(
        condition="abdominal_obesity_risk",
        window=window,
        score=round(score, 3),
        confidence=round(min(1.0, len(waist_points) / 5.0), 3),
        severity=severity,
        interpretation=(
            "Абдоминальное ожирение повышает риск метаболических и сердечно-сосудистых заболеваний "
            "независимо от общего ИМТ."
        ),
        summary=f"Подозрение на абдоминальное ожирение: талия {waist_cm:.0f} см (порог {thresholds['low']:.0f} см для {'женщин' if sex == 'female' else 'мужчин'}).",
        recommendation="Обратись к терапевту. Проверь давление, глюкозу и липиды.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={"waist_cm": round(waist_cm, 1), "sex": sex},
        lifestyle_recommendations=recs,
    )


