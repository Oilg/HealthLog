from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from statistics import median
from typing import Iterable

from health_log.analysis.detectors.illness.constants import (
    BASELINE_MAX_DAYS,
    HR_POINTS_PER_DAY_MIN,
    HRV_POINTS_PER_DAY_MIN,
    MIN_RECENT_VALID_DAYS,
    MIN_VALID_DAYS_FOR_SIGNAL,
    RECENT_DAYS,
)
from health_log.analysis.utils import EventPoint, merge_datetime_intervals


def _group_by_day(points: list[EventPoint]) -> dict[date, list[EventPoint]]:
    grouped: dict[date, list[EventPoint]] = defaultdict(list)
    for point in points:
        grouped[point.timestamp.date()].append(point)
    return grouped


def _merged_sleep(sleep_rows: Iterable[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    intervals = [(s, e) for s, e in sleep_rows if s and e and e > s]
    return merge_datetime_intervals(intervals)


def _in_sleep(ts: datetime, merged: list[tuple[datetime, datetime]]) -> bool:
    for start, end in merged:
        if start <= ts <= end:
            return True
    return False


def _day_has_sleep(d: date, sleep_rows: Iterable[tuple[datetime, datetime]]) -> bool:
    # Bind each sleep segment to the single date when the sleeper wakes up
    # (end.date()), so an overnight session 23:00→07:00 is counted once,
    # not for both calendar days.
    for start, end in sleep_rows:
        if start and end and end > start and end.date() == d:
            return True
    return False


def _bottom_fraction_median(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = max(1, int(len(s) * fraction))
    low = s[:n]
    return float(median(low))


def _day_rest_hr(
    day: date,
    heart_day: list[EventPoint],
    merged_sleep: list[tuple[datetime, datetime]],
) -> float | None:
    in_bed = [p.value for p in heart_day if _in_sleep(p.timestamp, merged_sleep)]
    if in_bed:
        return float(median(in_bed))
    if not heart_day:
        return None
    return _bottom_fraction_median([p.value for p in heart_day], 0.2)


def _day_median_hrv_night_else_all(
    day: date,
    hrv_day: list[EventPoint],
    merged_sleep: list[tuple[datetime, datetime]],
) -> float | None:
    night = [p.value for p in hrv_day if _in_sleep(p.timestamp, merged_sleep)]
    if night:
        return float(median(night))
    if not hrv_day:
        return None
    return float(median([p.value for p in hrv_day]))


def _day_median_rr_night_else_all(
    day: date,
    rr_day: list[EventPoint],
    merged_sleep: list[tuple[datetime, datetime]],
) -> float | None:
    night = [p.value for p in rr_day if _in_sleep(p.timestamp, merged_sleep)]
    if night:
        return float(median(night))
    if not rr_day:
        return None
    return float(median([p.value for p in rr_day]))


@dataclass(slots=True)
class TrendSnapshot:
    baseline_rest_hr: float
    recent_rest_hr: float
    baseline_hrv: float
    recent_hrv: float
    baseline_rr: float | None
    recent_rr: float | None
    resp_increase_pct: float
    confirmed_days: int
    valid_days_count: int
    total_hr_points: int
    total_hrv_points: int
    days_with_sleep: int


def build_trend_snapshot(
    heart: list[EventPoint],
    hrv: list[EventPoint],
    respiratory: list[EventPoint],
    sleep_rows: Iterable[tuple[datetime, datetime]],
) -> TrendSnapshot | None:
    merged = _merged_sleep(sleep_rows)
    heart_by_day = _group_by_day(heart)
    hrv_by_day = _group_by_day(hrv)
    resp_by_day = _group_by_day(respiratory)

    all_days = sorted(set(heart_by_day) | set(hrv_by_day))
    valid_days: list[date] = []
    for d in all_days:
        if (
            len(heart_by_day.get(d, [])) >= HR_POINTS_PER_DAY_MIN
            and len(hrv_by_day.get(d, [])) >= HRV_POINTS_PER_DAY_MIN
        ):
            valid_days.append(d)

    if len(valid_days) < MIN_VALID_DAYS_FOR_SIGNAL:
        return None

    recent_days = valid_days[-RECENT_DAYS:]
    if len(recent_days) < MIN_RECENT_VALID_DAYS:
        return None

    baseline_days = valid_days[:-RECENT_DAYS]
    if len(baseline_days) > BASELINE_MAX_DAYS:
        baseline_days = baseline_days[-BASELINE_MAX_DAYS:]

    day_hr: dict[date, float] = {}
    day_hrv: dict[date, float] = {}
    day_rr: dict[date, float] = {}
    for d in valid_days:
        rh = _day_rest_hr(d, heart_by_day.get(d, []), merged)
        hv = _day_median_hrv_night_else_all(d, hrv_by_day.get(d, []), merged)
        if rh is None or hv is None:
            continue
        day_hr[d] = rh
        day_hrv[d] = hv
        rr = _day_median_rr_night_else_all(d, resp_by_day.get(d, []), merged)
        if rr is not None:
            day_rr[d] = rr

    baseline_rest_hr = float(median([day_hr[d] for d in baseline_days if d in day_hr]))
    recent_rest_hr = float(median([day_hr[d] for d in recent_days if d in day_hr]))
    baseline_hrv = float(median([day_hrv[d] for d in baseline_days if d in day_hrv]))
    recent_hrv = float(median([day_hrv[d] for d in recent_days if d in day_hrv]))

    baseline_rr_list = [day_rr[d] for d in baseline_days if d in day_rr]
    baseline_rr = float(median(baseline_rr_list)) if baseline_rr_list else None
    recent_rr_list = [day_rr[d] for d in recent_days if d in day_rr]
    recent_rr = float(median(recent_rr_list)) if recent_rr_list else None

    if baseline_hrv == 0:
        return None

    resp_increase_pct = 0.0
    if baseline_rr is not None and recent_rr is not None and baseline_rr > 0:
        resp_increase_pct = max(0.0, (recent_rr - baseline_rr) / baseline_rr)

    confirmed_days = 0
    for d in recent_days:
        day_hr_v = day_hr.get(d)
        day_hrv_v = day_hrv.get(d)
        day_rr_v = day_rr.get(d)
        hr_flag = day_hr_v is not None and day_hr_v >= baseline_rest_hr + 4
        hrv_flag = day_hrv_v is not None and day_hrv_v <= baseline_hrv * 0.9
        resp_flag = (
            day_rr_v is not None
            and baseline_rr is not None
            and day_rr_v >= baseline_rr * 1.08
        )
        if sum([hr_flag, hrv_flag, resp_flag]) >= 2:
            confirmed_days += 1

    days_with_sleep = sum(1 for d in valid_days if _day_has_sleep(d, sleep_rows))

    return TrendSnapshot(
        baseline_rest_hr=baseline_rest_hr,
        recent_rest_hr=recent_rest_hr,
        baseline_hrv=baseline_hrv,
        recent_hrv=recent_hrv,
        baseline_rr=baseline_rr,
        recent_rr=recent_rr,
        resp_increase_pct=resp_increase_pct,
        confirmed_days=confirmed_days,
        valid_days_count=len(valid_days),
        total_hr_points=len(heart),
        total_hrv_points=len(hrv),
        days_with_sleep=days_with_sleep,
    )


def trend_days_available(
    heart: list[EventPoint],
    hrv: list[EventPoint],
) -> int:
    heart_by_day = _group_by_day(heart)
    hrv_by_day = _group_by_day(hrv)
    all_days = sorted(set(heart_by_day) | set(hrv_by_day))
    n = 0
    for d in all_days:
        if (
            len(heart_by_day.get(d, [])) >= HR_POINTS_PER_DAY_MIN
            and len(hrv_by_day.get(d, [])) >= HRV_POINTS_PER_DAY_MIN
        ):
            n += 1
    return n
