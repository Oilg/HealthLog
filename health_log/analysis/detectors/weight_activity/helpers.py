from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import TypeVar

from health_log.analysis.utils import EventPoint

T = TypeVar("T")


def group_by_day(points: list[EventPoint]) -> dict[int, list[float]]:
    by_day: dict[int, list[float]] = {}
    for p in points:
        by_day.setdefault(p.timestamp.toordinal(), []).append(p.value)
    return by_day


def daily_medians(points: list[EventPoint], start: datetime, end: datetime) -> list[float]:
    by_day = group_by_day([p for p in points if start <= p.timestamp <= end])
    return [median(vals) for vals in by_day.values()]


def latest_complete_day_end(now: datetime) -> datetime:
    """Конец последнего полностью прошедшего дня UTC.

    Используется для отсечения незавершённого "сегодня" в детекторах, агрегирующих
    суточные суммы (шаги). Возвращает полночь сегодняшнего дня UTC, что равно
    точке, до которой включительно данные считаются полными.

    Известное ограничение: пользователи в восточных таймзонах (UTC+3..+10) могут
    потерять последние часы предыдущего календарного дня в своей локальной зоне.
    """
    return datetime(now.year, now.month, now.day, 0, 0, 0)


def daily_totals(
    points: list[EventPoint],
    start: datetime,
    end: datetime,
) -> dict[int, float]:
    """Суммы значений за каждый день в окне [start, end]. Без фильтрации нулей.

    Подходит для метрик, где ноль — валидное значение (например, exercise_time).
    """
    totals: dict[int, float] = {}
    for p in points:
        if start <= p.timestamp <= end:
            totals[p.timestamp.toordinal()] = totals.get(p.timestamp.toordinal(), 0.0) + p.value
    return totals


def daily_step_totals(
    points: list[EventPoint],
    start: datetime,
    end: datetime,
    *,
    exclude_zero: bool = True,
) -> list[float]:
    """Суммы шагов за каждый день в окне [start, end].

    При exclude_zero=True (по умолчанию) дни с нулевой суммой исключаются как
    wear-time gaps (часы не носили / iPhone остался дома). Отсутствие данных
    не равно гиподинамии. Согласовано: Trost 2005, Tudor-Locke 2005.
    """
    totals = daily_totals(points, start, end)
    if exclude_zero:
        return [v for v in totals.values() if v > 0]
    return list(totals.values())


def valid_step_day_count(
    points: list[EventPoint],
    start: datetime,
    end: datetime,
) -> int:
    """Количество дней в окне [start, end] с ненулевой суммой шагов."""
    return len(daily_step_totals(points, start, end, exclude_zero=True))


def window_median(points: list[EventPoint], start: datetime, end: datetime) -> float | None:
    vals = daily_medians(points, start, end)
    return median(vals) if vals else None


def recent_and_baseline(
    points: list[EventPoint],
    now: datetime,
    *,
    recent_days: int,
    baseline_days: int,
) -> tuple[list[EventPoint], list[EventPoint]]:
    recent_start = now - timedelta(days=recent_days)
    baseline_start = now - timedelta(days=recent_days + baseline_days)
    recent = [p for p in points if p.timestamp >= recent_start]
    baseline = [p for p in points if baseline_start <= p.timestamp < recent_start]
    return recent, baseline


def compute_bmi(weight_kg: float, height_m: float) -> float | None:
    if height_m <= 0:
        return None
    return weight_kg / (height_m**2)


def smoothed_median(
    points: list[EventPoint],
    start: datetime,
    end: datetime,
    *,
    edge_days: int = 14,
) -> tuple[float, float] | tuple[None, None]:
    period_start = start
    period_end = start + timedelta(days=edge_days)
    first_half = daily_medians(points, period_start, period_end)
    last_half_start = end - timedelta(days=edge_days)
    last_half = daily_medians(points, last_half_start, end)
    if first_half and last_half:
        return median(first_half), median(last_half)
    return None, None


def distinct_day_count(points: list[EventPoint], start: datetime, end: datetime) -> int:
    return len({p.timestamp.toordinal() for p in points if start <= p.timestamp <= end})
