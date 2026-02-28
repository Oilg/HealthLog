from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Iterable


@dataclass(slots=True)
class EventPoint:
    timestamp: datetime
    value: float


def build_score_confidence_interpretation(score: float, confidence: float) -> str:
    if score >= 0.6 and confidence < 0.5:
        return "Высокий уровень риска при низкой достоверности сигнала: подозрение есть, но данных пока мало."
    if score >= 0.6 and confidence >= 0.5:
        return "Высокий уровень риска и высокая достоверность сигнала: сигнал устойчивый, стоит проверить у врача."
    if score < 0.3 and confidence >= 0.5:
        return "Низкий уровень риска при нормальной достоверности сигнала: явного устойчивого риска по текущим данным нет."
    return "Сигнал промежуточный: наблюдай динамику и собирай данные дальше."


def safe_float(raw: object) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (float, int)):
        return float(raw)

    text = str(raw).strip().replace(",", ".")
    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        return None


def to_points(rows: Iterable[tuple[datetime, object]]) -> list[EventPoint]:
    points: list[EventPoint] = []
    for ts, raw in rows:
        value = safe_float(raw)
        if ts is None or value is None:
            continue
        points.append(EventPoint(timestamp=ts, value=value))
    return points


def nearest_value(points: list[EventPoint], target_ts: datetime, max_seconds: int) -> float | None:
    nearest: EventPoint | None = None
    nearest_delta: float | None = None

    for point in points:
        delta = abs((point.timestamp - target_ts).total_seconds())
        if delta > max_seconds:
            continue
        if nearest_delta is None or delta < nearest_delta:
            nearest = point
            nearest_delta = delta

    return nearest.value if nearest else None


def split_baseline_recent(points: list[EventPoint]) -> tuple[list[EventPoint], list[EventPoint]]:
    if len(points) < 2:
        return points, []
    split_idx = max(1, int(len(points) * 0.7))
    split_idx = min(split_idx, len(points) - 1)
    return points[:split_idx], points[split_idx:]


def resting_like_median(values: list[float]) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    low_count = max(1, int(len(sorted_values) * 0.3))
    return median(sorted_values[:low_count])
