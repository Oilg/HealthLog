from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean, median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import EventPoint, merge_datetime_intervals, to_points
from health_log.utils import utcnow

_LOOKBACK_DAYS = 14
_BASELINE_DAYS = 60
_MIN_VALID_DAYS = 7
_SLEEP_DROP_MINUTES = 60
_HR_RISE_BPM = 5
_HRV_DROP_PCT = 0.15
_HRV_7D_DROP_PCT = 0.10  # Early-stage threshold for 7-day rolling mean comparison


def _sleep_hours_per_day(segments: list[tuple[datetime, datetime]]) -> dict[int, float]:
    by_day: dict[int, float] = {}
    merged = merge_datetime_intervals([(s, e) for s, e in segments if s and e and e > s])
    for seg_start, seg_end in merged:
        day_key = seg_start.toordinal()
        hours = (seg_end - seg_start).total_seconds() / 3600.0
        by_day[day_key] = by_day.get(day_key, 0.0) + hours
    return by_day


def _daily_median_for_points(
    points: list[EventPoint], cutoff_start: datetime, cutoff_end: datetime
) -> dict[int, float]:
    by_day: dict[int, list[float]] = {}
    for p in points:
        if cutoff_start <= p.timestamp <= cutoff_end:
            key = p.timestamp.toordinal()
            by_day.setdefault(key, []).append(p.value)
    return {day: median(vals) for day, vals in by_day.items()}


def _resting_hr_from_all(hr_points: list[EventPoint]) -> list[EventPoint]:
    """Approximate resting HR as the lower 20% of all HR measurements."""
    sorted_vals = sorted(hr_points, key=lambda p: p.value)
    n = max(1, int(len(sorted_vals) * 0.2))
    return sorted_vals[:n]


def assess_overload_recovery_risk(
    sleep_segments: list[tuple[datetime, datetime]] | None = None,
    heart_rows: Iterable[tuple] | None = None,
    hrv_rows: Iterable[tuple] | None = None,
    resting_heart_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    recent_start = now - timedelta(days=_LOOKBACK_DAYS)
    baseline_start = now - timedelta(days=_LOOKBACK_DAYS + _BASELINE_DAYS)

    segments = list(sleep_segments or [])
    all_hr_points = to_points(heart_rows or [])
    resting_hr_points = to_points(resting_heart_rows or [])
    hrv_points = to_points(hrv_rows or [])

    # Use dedicated resting HR points if available; fall back to lower-20% approximation.
    if resting_hr_points:
        hr_points = resting_hr_points
        using_resting_hr = True
    elif all_hr_points:
        hr_points = _resting_hr_from_all(all_hr_points)
        using_resting_hr = False
    else:
        hr_points = []
        using_resting_hr = False

    recent_sleep_by_day = _sleep_hours_per_day([(s, e) for s, e in segments if e >= recent_start])
    baseline_sleep_by_day = _sleep_hours_per_day(
        [(s, e) for s, e in segments if baseline_start <= s < recent_start]
    )

    recent_days_count = len(recent_sleep_by_day)

    if recent_days_count < _MIN_VALID_DAYS:
        return RiskAssessment(
            condition="overload_recovery_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных для оценки перегрузки/восстановления.",
            summary=f"Найдено {recent_days_count} дней с данными за 14 дней (нужно ≥{_MIN_VALID_DAYS}).",
            recommendation="Проверь синхронизацию сна, пульса и HRV в Apple Health.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"recent_days_with_sleep": recent_days_count},
        )

    baseline_sleep_med = median(baseline_sleep_by_day.values()) if baseline_sleep_by_day else None

    recent_hr_by_day = _daily_median_for_points(hr_points, recent_start, now)
    baseline_hr_by_day = _daily_median_for_points(hr_points, baseline_start, recent_start)
    recent_hrv_by_day = _daily_median_for_points(hrv_points, recent_start, now)
    baseline_hrv_by_day = _daily_median_for_points(hrv_points, baseline_start, recent_start)

    baseline_hr_med = median(baseline_hr_by_day.values()) if baseline_hr_by_day else None
    baseline_hrv_med = median(baseline_hrv_by_day.values()) if baseline_hrv_by_day else None

    # 7-day rolling mean of HRV for early-stage detection.
    # Compute per-day HRV medians over [baseline_start..now], then build rolling average.
    all_hrv_by_day = _daily_median_for_points(hrv_points, baseline_start, now)
    hrv_7d_mean_by_day: dict[int, float] = {}
    if all_hrv_by_day:
        sorted_hrv_days = sorted(all_hrv_by_day.keys())
        for i, day in enumerate(sorted_hrv_days):
            # Collect up to the 7 days immediately preceding this day (not including it).
            window_vals = [
                all_hrv_by_day[d]
                for d in sorted_hrv_days[max(0, i - 7) : i]
            ]
            if window_vals:
                hrv_7d_mean_by_day[day] = mean(window_vals)

    signal_days = 0
    recent_all_days = set(recent_sleep_by_day) | set(recent_hr_by_day) | set(recent_hrv_by_day)
    recent_all_days_sorted = sorted(recent_all_days)

    # For HR signal: require 2 of the 3 most-recent days with data to show elevation.
    recent_hr_days_sorted = sorted(recent_hr_by_day.keys())
    last_3_hr_days = recent_hr_days_sorted[-3:] if len(recent_hr_days_sorted) >= 2 else []
    hr_elevated_in_last3 = 0
    if baseline_hr_med is not None:
        for day in last_3_hr_days:
            if recent_hr_by_day[day] >= baseline_hr_med + _HR_RISE_BPM:
                hr_elevated_in_last3 += 1
    hr_signal_sustained = hr_elevated_in_last3 >= 2

    for day in recent_all_days_sorted:
        flags = 0
        if baseline_sleep_med is not None and day in recent_sleep_by_day:
            sleep_h = recent_sleep_by_day[day]
            if baseline_sleep_med - sleep_h >= _SLEEP_DROP_MINUTES / 60.0:
                flags += 1
        # HR flag: use sustained signal (not per-day) — only count on days where the
        # overall sustained criterion is met.
        if hr_signal_sustained and day in recent_hr_by_day:
            if baseline_hr_med is not None and recent_hr_by_day[day] >= baseline_hr_med + _HR_RISE_BPM:
                flags += 1
        # HRV flag: 60-day baseline OR 7-day rolling mean drop ≥10% (early-stage detection).
        hrv_flag = False
        if baseline_hrv_med is not None and day in recent_hrv_by_day:
            if recent_hrv_by_day[day] <= baseline_hrv_med * (1 - _HRV_DROP_PCT):
                hrv_flag = True
        if not hrv_flag and day in recent_hrv_by_day and day in hrv_7d_mean_by_day:
            if recent_hrv_by_day[day] <= hrv_7d_mean_by_day[day] * (1 - _HRV_7D_DROP_PCT):
                hrv_flag = True
        if hrv_flag:
            flags += 1
        if flags >= 2:
            signal_days += 1

    # Compute actual resting HR value for supporting_metrics.
    recent_resting_hr_val: float | None = None
    if recent_hr_by_day:
        recent_resting_hr_val = median(recent_hr_by_day.values())

    if signal_days >= 6:
        severity = "high"
        score = 0.85
    elif signal_days >= 4:
        severity = "medium"
        score = 0.65
    elif signal_days >= 2:
        severity = "low"
        score = 0.35
    else:
        return RiskAssessment(
            condition="overload_recovery_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, recent_days_count / _MIN_VALID_DAYS), 3),
            severity="none",
            interpretation="Признаков перегрузки или нарушения восстановления не выявлено.",
            summary=f"Показатели восстановления в норме за последние {_LOOKBACK_DAYS} дней.",
            recommendation="Продолжай поддерживать режим сна и восстановления.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"signal_days": signal_days, "recent_valid_days": recent_days_count},
        )

    confidence = round(
        min(1.0, recent_days_count / _MIN_VALID_DAYS) * 0.7 + min(1.0, signal_days / 6.0) * 0.3, 3
    )

    return RiskAssessment(
        condition="overload_recovery_risk",
        window=window,
        score=round(score, 3),
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Совокупность нарушений сна, повышения ночного пульса и снижения HRV "
            "указывает на возможное недовосстановление или перегрузку."
        ),
        summary=(
            f"Подозрение на нарушение восстановления: {signal_days} сигнальных дней из {_LOOKBACK_DAYS} "
            f"(≥2 флага из трёх: сон, пульс, HRV)."
        ),
        recommendation=(
            "Увеличь время сна, снизь интенсивность нагрузок и добавь дни восстановления. "
            "При сохраняющихся симптомах обратись к врачу."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "signal_days_14d": signal_days,
            "recent_valid_days": recent_days_count,
            "baseline_sleep_hours": round(baseline_sleep_med, 2) if baseline_sleep_med is not None else None,
            "recent_resting_hr": round(recent_resting_hr_val, 1) if recent_resting_hr_val is not None else None,
            "baseline_resting_hr": round(baseline_hr_med, 1) if baseline_hr_med is not None else None,
            "baseline_hrv": round(baseline_hrv_med, 1) if baseline_hrv_med is not None else None,
            "resting_hr_source": "dedicated" if using_resting_hr else "approximated",
        },
    )
