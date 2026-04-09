from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
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


def prediction_band_from_variability(variability: int) -> int:
    if variability <= 4:
        return 2
    if variability <= 8:
        return 4
    return 6


def cycle_variability_last_six(lengths: list[int]) -> int:
    recent = lengths[-6:]
    return max(recent) - min(recent)


@dataclass(slots=True)
class MenstrualModel:
    starts_count: int
    cycle_lengths: list[int]
    typical_cycle: int
    predicted_next: date
    predicted_earliest: date
    predicted_latest: date
    band: int
    days_to_next: int
    variability: int
    last_start: date
    last_cycle_start_age_days: int


def build_menstrual_model(
    menstrual_rows: Iterable[tuple[datetime, object]],
    *,
    now: datetime,
) -> MenstrualModel | None:
    flow_days = extract_flow_days(menstrual_rows)
    starts = build_period_starts(flow_days)
    if len(starts) < 4:
        return None
    cycle_lengths = build_cycle_lengths(starts)
    if len(cycle_lengths) < 3:
        return None

    typ_float = weighted_cycle_length(cycle_lengths)
    variability = cycle_variability_last_six(cycle_lengths)
    band = prediction_band_from_variability(variability)
    last_start = starts[-1]
    typical_int = int(round(typ_float))
    predicted_next = last_start + timedelta(days=typical_int)
    predicted_earliest = predicted_next - timedelta(days=band)
    predicted_latest = predicted_next + timedelta(days=band)
    days_to_next = (predicted_next - now.date()).days

    return MenstrualModel(
        starts_count=len(starts),
        cycle_lengths=cycle_lengths,
        typical_cycle=typical_int,
        predicted_next=predicted_next,
        predicted_earliest=predicted_earliest,
        predicted_latest=predicted_latest,
        band=band,
        days_to_next=days_to_next,
        variability=variability,
        last_start=last_start,
        last_cycle_start_age_days=(now.date() - last_start).days,
    )
