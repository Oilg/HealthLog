from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from statistics import median
from typing import Iterable

from health_log.analysis.detectors.menstrual_cycle.constants import (
    MAX_CYCLE_LENGTH_DAYS,
    MIN_CYCLE_LENGTH_DAYS,
)


def is_flow_value(raw: object) -> bool:
    if raw is None:
        return False
    text = str(raw).strip()
    if not text:
        return False

    if text.startswith("HKCategoryValueMenstrualFlow"):
        return not text.endswith("None")

    try:
        return float(text) > 0
    except ValueError:
        return False


def extract_flow_days(rows: Iterable[tuple[datetime, object]]) -> list[date]:
    days: set[date] = set()
    for ts, value in rows:
        if ts is None:
            continue
        if is_flow_value(value):
            days.add(ts.date())
    return sorted(days)


def build_period_starts(flow_days: list[date]) -> list[date]:
    if not flow_days:
        return []

    starts = [flow_days[0]]
    prev = flow_days[0]
    for day in flow_days[1:]:
        if (day - prev).days > 2:
            starts.append(day)
        prev = day
    return starts


def build_cycle_lengths(starts: list[date]) -> list[int]:
    return [
        (starts[idx] - starts[idx - 1]).days
        for idx in range(1, len(starts))
        if MIN_CYCLE_LENGTH_DAYS <= (starts[idx] - starts[idx - 1]).days <= MAX_CYCLE_LENGTH_DAYS
    ]


def weighted_cycle_length(lengths: list[int]) -> float:
    recent = lengths[-6:]
    weights = list(range(1, len(recent) + 1))
    weighted_mean = sum(length * weight for length, weight in zip(recent, weights, strict=True)) / sum(weights)
    return (weighted_mean * 0.7) + (median(recent) * 0.3)


def variability_band(lengths: list[int]) -> int:
    recent = sorted(lengths[-8:])
    if len(recent) < 3:
        return 3
    p25_idx = int((len(recent) - 1) * 0.25)
    p75_idx = int((len(recent) - 1) * 0.75)
    iqr = max(0, recent[p75_idx] - recent[p25_idx])
    return max(2, min(6, int(round(iqr / 2)) + 1))


@dataclass(slots=True)
class MenstrualTrend:
    starts_count: int
    cycle_lengths: list[int]
    typical_cycle: int
    predicted_earliest: date
    predicted_latest: date
    ovulation_from: date
    ovulation_to: date
    days_to_next: int
    variability: int
