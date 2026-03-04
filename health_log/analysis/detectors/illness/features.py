from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from statistics import median
from typing import Iterable

from health_log.analysis.detectors.illness.constants import (
    BASELINE_DAYS,
    MIN_DAYS_FOR_TREND,
    RECENT_DAYS,
)
from health_log.analysis.utils import EventPoint, resting_like_median


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _daily_resting_hr(points: list[EventPoint]) -> dict[date, float]:
    grouped: dict[date, list[float]] = defaultdict(list)
    for point in points:
        grouped[point.timestamp.date()].append(point.value)

    daily: dict[date, float] = {}
    for day, values in grouped.items():
        resting = resting_like_median(values)
        if resting is not None:
            daily[day] = resting
    return daily


def _daily_median(points: list[EventPoint]) -> dict[date, float]:
    grouped: dict[date, list[float]] = defaultdict(list)
    for point in points:
        grouped[point.timestamp.date()].append(point.value)

    daily: dict[date, float] = {}
    for day, values in grouped.items():
        if values:
            daily[day] = median(values)
    return daily


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []

    intervals_sorted = sorted(intervals, key=lambda item: item[0])
    merged: list[tuple[datetime, datetime]] = [intervals_sorted[0]]
    for start, end in intervals_sorted[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _daily_sleep_stats(sleep_rows: Iterable[tuple[datetime, datetime]]) -> tuple[dict[date, float], dict[date, int]]:
    by_day: dict[date, list[tuple[datetime, datetime]]] = defaultdict(list)
    for start, end in sleep_rows:
        if start is None or end is None or end <= start:
            continue
        by_day[end.date()].append((start, end))

    duration_hours: dict[date, float] = {}
    fragments: dict[date, int] = {}
    for day, intervals in by_day.items():
        merged = _merge_intervals(intervals)
        total_seconds = sum((end - start).total_seconds() for start, end in merged)
        duration_hours[day] = total_seconds / 3600.0
        fragments[day] = len(merged)

    return duration_hours, fragments


@dataclass(slots=True)
class TrendSnapshot:
    selected_days: list[date]
    hr_increase: float
    hrv_drop_pct: float
    hrv_change_pct: float
    resp_increase_pct: float
    sleep_disruption: float
    confirmed_days: int
    heart_points_count: int
    hrv_points_count: int


def build_trend_snapshot(
    heart: list[EventPoint],
    hrv: list[EventPoint],
    respiratory: list[EventPoint],
    sleep_rows: Iterable[tuple[datetime, datetime]],
) -> TrendSnapshot | None:
    heart_by_day = _daily_resting_hr(heart)
    hrv_by_day = _daily_median(hrv)
    resp_by_day = _daily_median(respiratory)
    sleep_duration_by_day, sleep_fragments_by_day = _daily_sleep_stats(sleep_rows)

    trend_days = sorted(set(heart_by_day) & set(hrv_by_day))
    if len(trend_days) < MIN_DAYS_FOR_TREND:
        return None

    selected_days = trend_days[-MIN_DAYS_FOR_TREND:]
    baseline_days = selected_days[:BASELINE_DAYS]
    recent_days = selected_days[-RECENT_DAYS:]

    baseline_rest_hr = median([heart_by_day[d] for d in baseline_days])
    baseline_hrv = median([hrv_by_day[d] for d in baseline_days])
    recent_rest_hr = median([heart_by_day[d] for d in recent_days])
    recent_hrv = median([hrv_by_day[d] for d in recent_days])
    if baseline_hrv == 0:
        return None

    hr_increase = recent_rest_hr - baseline_rest_hr
    hrv_drop_pct = max(0.0, (baseline_hrv - recent_hrv) / baseline_hrv)
    hrv_change_pct = ((recent_hrv - baseline_hrv) / baseline_hrv) * 100

    baseline_resp = median([resp_by_day[d] for d in baseline_days if d in resp_by_day]) if resp_by_day else None
    recent_resp = median([resp_by_day[d] for d in recent_days if d in resp_by_day]) if resp_by_day else None
    resp_increase_pct = 0.0
    if baseline_resp is not None and recent_resp is not None and baseline_resp > 0:
        resp_increase_pct = max(0.0, (recent_resp - baseline_resp) / baseline_resp)

    baseline_sleep_hours = (
        median([sleep_duration_by_day[d] for d in baseline_days if d in sleep_duration_by_day])
        if sleep_duration_by_day
        else None
    )
    recent_sleep_hours = (
        median([sleep_duration_by_day[d] for d in recent_days if d in sleep_duration_by_day])
        if sleep_duration_by_day
        else None
    )
    baseline_fragments = (
        median([sleep_fragments_by_day[d] for d in baseline_days if d in sleep_fragments_by_day])
        if sleep_fragments_by_day
        else None
    )
    recent_fragments = (
        median([sleep_fragments_by_day[d] for d in recent_days if d in sleep_fragments_by_day])
        if sleep_fragments_by_day
        else None
    )

    sleep_disruption = 0.0
    if baseline_sleep_hours is not None and recent_sleep_hours is not None:
        sleep_disruption = max(sleep_disruption, _clamp01((baseline_sleep_hours - recent_sleep_hours) / 2.0))
    if baseline_fragments is not None and recent_fragments is not None:
        sleep_disruption = max(sleep_disruption, _clamp01((recent_fragments - baseline_fragments) / 2.0))

    confirmed_days = 0
    for day in recent_days:
        day_hr = heart_by_day.get(day)
        day_hrv = hrv_by_day.get(day)
        day_resp = resp_by_day.get(day)

        hr_flag = day_hr is not None and day_hr >= baseline_rest_hr + 4
        hrv_flag = day_hrv is not None and day_hrv <= baseline_hrv * 0.9
        resp_flag = day_resp is not None and baseline_resp is not None and day_resp >= baseline_resp * 1.08
        if sum([hr_flag, hrv_flag, resp_flag]) >= 2:
            confirmed_days += 1

    return TrendSnapshot(
        selected_days=selected_days,
        hr_increase=hr_increase,
        hrv_drop_pct=hrv_drop_pct,
        hrv_change_pct=hrv_change_pct,
        resp_increase_pct=resp_increase_pct,
        sleep_disruption=sleep_disruption,
        confirmed_days=confirmed_days,
        heart_points_count=len(heart),
        hrv_points_count=len(hrv),
    )


def trend_days_available(
    heart: list[EventPoint],
    hrv: list[EventPoint],
) -> int:
    heart_by_day = _daily_resting_hr(heart)
    hrv_by_day = _daily_median(hrv)
    return len(set(heart_by_day) & set(hrv_by_day))
