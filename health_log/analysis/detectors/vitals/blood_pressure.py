from __future__ import annotations

from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import EventPoint, to_points

_MIN_MEASUREMENTS = 6
_MIN_DISTINCT_DAYS = 3


def _days_with_condition(
    sbp: list[EventPoint],
    dbp: list[EventPoint],
    sbp_threshold: float | None,
    dbp_threshold: float | None,
    *,
    above: bool = True,
) -> int:
    sbp_by_day: dict[int, list[float]] = {}
    for p in sbp:
        sbp_by_day.setdefault(p.timestamp.toordinal(), []).append(p.value)
    dbp_by_day: dict[int, list[float]] = {}
    for p in dbp:
        dbp_by_day.setdefault(p.timestamp.toordinal(), []).append(p.value)

    days = set(sbp_by_day) | set(dbp_by_day)
    confirmed = 0
    for day in days:
        day_sbp = sbp_by_day.get(day, [])
        day_dbp = dbp_by_day.get(day, [])
        sbp_ok = False
        dbp_ok = False
        if sbp_threshold is not None and day_sbp:
            med = median(day_sbp)
            sbp_ok = (med >= sbp_threshold) if above else (med < sbp_threshold)
        if dbp_threshold is not None and day_dbp:
            med = median(day_dbp)
            dbp_ok = (med >= dbp_threshold) if above else (med < dbp_threshold)
        if sbp_ok or dbp_ok:
            confirmed += 1
    return confirmed


def _distinct_days(points: list[EventPoint]) -> int:
    return len({p.timestamp.toordinal() for p in points})


def _insufficient_bp(condition: str, window: TimeWindow, n: int) -> RiskAssessment:
    return RiskAssessment(
        condition=condition,
        window=window,
        score=0.0,
        confidence=0.0,
        severity="unknown",
        interpretation="Недостаточно измерений артериального давления.",
        summary=f"Найдено {n} измерений АД (нужно ≥{_MIN_MEASUREMENTS} в ≥{_MIN_DISTINCT_DAYS} разных днях).",
        recommendation="Проверь синхронизацию данных артериального давления в Apple Health.",
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={"measurements_count": n},
    )


def assess_hypertension_risk(
    sbp_rows: Iterable[tuple],
    dbp_rows: Iterable[tuple],
    *,
    window: TimeWindow,
) -> RiskAssessment:
    sbp = to_points(sbp_rows)
    dbp = to_points(dbp_rows)
    n_measurements = len(sbp)

    if n_measurements < _MIN_MEASUREMENTS or _distinct_days(sbp) < _MIN_DISTINCT_DAYS:
        return _insufficient_bp("hypertension_risk", window, n_measurements)

    avg_sbp = sum(p.value for p in sbp) / len(sbp)
    avg_dbp = sum(p.value for p in dbp) / len(dbp) if dbp else 0.0

    if avg_sbp >= 160 or avg_dbp >= 100:
        severity = "high"
        score_base = 0.85
        sbp_thr, dbp_thr = 160.0, 100.0
    elif avg_sbp >= 140 or avg_dbp >= 90:
        severity = "medium"
        score_base = 0.65
        sbp_thr, dbp_thr = 140.0, 90.0
    elif avg_sbp >= 130 or avg_dbp >= 80:
        severity = "low"
        score_base = 0.35
        sbp_thr, dbp_thr = 130.0, 80.0
    else:
        return RiskAssessment(
            condition="hypertension_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, n_measurements / 20.0), 3),
            severity="none",
            interpretation="Значимого повышения АД не выявлено.",
            summary=f"Среднее АД: {avg_sbp:.0f}/{avg_dbp:.0f} мм рт.ст. — в пределах нормы.",
            recommendation="Продолжай регулярный контроль АД.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"avg_sbp": round(avg_sbp, 1), "avg_dbp": round(avg_dbp, 1), "measurements": n_measurements},
        )

    confirmed_days = _days_with_condition(sbp, dbp, sbp_thr, dbp_thr, above=True)

    if confirmed_days < 2:
        return RiskAssessment(
            condition="hypertension_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, n_measurements / 20.0), 3),
            severity="none",
            interpretation="Единичное повышение АД — для сигнала требуется подтверждение в ≥2 дня.",
            summary=f"Среднее АД {avg_sbp:.0f}/{avg_dbp:.0f} мм рт.ст., но устойчивого паттерна не выявлено.",
            recommendation="Продолжай измерения; при повторных высоких значениях обратись к врачу.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"avg_sbp": round(avg_sbp, 1), "avg_dbp": round(avg_dbp, 1), "confirmed_days": confirmed_days},
        )

    score = round(min(1.0, score_base + confirmed_days * 0.03), 3)
    confidence = round(min(1.0, n_measurements / 20.0) * 0.7 + min(1.0, confirmed_days / 5.0) * 0.3, 3)

    return RiskAssessment(
        condition="hypertension_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Это не диагноз; подтверждение гипертонии требует клинической оценки. "
            "Повторные высокие значения АД требуют внимания специалиста."
        ),
        summary=(
            f"Подозрение на повышенное АД: среднее {avg_sbp:.0f}/{avg_dbp:.0f} мм рт.ст., "
            f"подтверждено в {confirmed_days} дня(ей)."
        ),
        recommendation=(
            "Рекомендуется обратиться к терапевту или кардиологу. "
            "Контролируй АД регулярно; снизь потребление соли и следи за весом."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "avg_sbp": round(avg_sbp, 1),
            "avg_dbp": round(avg_dbp, 1),
            "measurements": n_measurements,
            "confirmed_days": confirmed_days,
        },
    )


def assess_hypotension_risk(
    sbp_rows: Iterable[tuple],
    dbp_rows: Iterable[tuple] | None = None,
    heart_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
) -> RiskAssessment:
    sbp = to_points(sbp_rows)
    n_measurements = len(sbp)

    if n_measurements < _MIN_MEASUREMENTS or _distinct_days(sbp) < _MIN_DISTINCT_DAYS:
        return _insufficient_bp("hypotension_risk", window, n_measurements)

    avg_sbp = sum(p.value for p in sbp) / len(sbp)

    hr_points = to_points(heart_rows or [])
    avg_hr = sum(p.value for p in hr_points) / len(hr_points) if hr_points else None

    days_sbp_below_90 = _days_with_condition(sbp, [], 90.0, None, above=False)
    high_hr_concurrent = avg_hr is not None and avg_hr > 90

    if avg_sbp < 90 and days_sbp_below_90 >= 2 and high_hr_concurrent:
        severity = "high"
        score = 0.85
    elif avg_sbp < 90:
        severity = "medium"
        score = 0.65
    elif avg_sbp < 100:
        severity = "low"
        score = 0.35
    else:
        return RiskAssessment(
            condition="hypotension_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, n_measurements / 20.0), 3),
            severity="none",
            interpretation="Значимого снижения АД не выявлено.",
            summary=f"Среднее АД: {avg_sbp:.0f} мм рт.ст. — в пределах нормы.",
            recommendation="Продолжай контроль АД; при головокружениях или обмороках обратись к врачу.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"avg_sbp": round(avg_sbp, 1), "measurements": n_measurements},
        )

    confidence = round(min(1.0, n_measurements / 20.0) * 0.8 + (0.2 if days_sbp_below_90 >= 2 else 0.0), 3)

    summary = f"Подозрение на сниженное АД: среднее {avg_sbp:.0f} мм рт.ст."
    if high_hr_concurrent:
        summary += f" На фоне повышенного пульса в покое ({avg_hr:.0f} уд/мин)."

    return RiskAssessment(
        condition="hypotension_risk",
        window=window,
        score=round(score, 3),
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Это не диагноз; пониженное АД с тахикардией может указывать на дегидратацию, "
            "ортостатическую гипотензию или другие состояния, требующие оценки врача."
        ),
        summary=summary,
        recommendation=(
            "Обратись к терапевту. При острых симптомах (обморок, слабость, потемнение в глазах) "
            "необходима срочная медицинская помощь."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "avg_sbp": round(avg_sbp, 1),
            "measurements": n_measurements,
            "days_sbp_below_90": days_sbp_below_90,
            "avg_resting_hr": round(avg_hr, 1) if avg_hr is not None else None,
        },
    )
