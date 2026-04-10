from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import EventPoint, merge_datetime_intervals, to_points

_MIN_REST_POINTS = 20
_BRADYCARDIA_THRESHOLD = 50
_EPISODE_MIN_POINTS = 3
_EPISODE_MAX_GAP_SEC = 120
_EPISODE_MIN_DURATION_SEC = 300
_MEDIAN_STRONG_THRESHOLD = 45


def _in_sleep(ts: datetime, segments: list[tuple[datetime, datetime]]) -> bool:
    for start, end in segments:
        if start <= ts <= end:
            return True
    return False


def _sleep_rest_points(
    heart: list[EventPoint],
    segments: list[tuple[datetime, datetime]],
) -> list[EventPoint]:
    return [p for p in heart if _in_sleep(p.timestamp, segments)]


def _fallback_rest_points(heart: list[EventPoint]) -> list[EventPoint]:
    if not heart:
        return []
    values = sorted(p.value for p in heart)
    threshold = values[max(0, int(len(values) * 0.2) - 1)]
    return [p for p in heart if p.value <= threshold]


def _build_bradycardia_episodes(rest_points: list[EventPoint]) -> list[dict]:
    low_points = [p for p in sorted(rest_points, key=lambda p: p.timestamp) if p.value < _BRADYCARDIA_THRESHOLD]
    if not low_points:
        return []

    clusters: list[list[EventPoint]] = []
    cur: list[EventPoint] = [low_points[0]]
    for p in low_points[1:]:
        gap = (p.timestamp - cur[-1].timestamp).total_seconds()
        if gap <= _EPISODE_MAX_GAP_SEC:
            cur.append(p)
        else:
            clusters.append(cur)
            cur = [p]
    clusters.append(cur)

    episodes: list[dict] = []
    for cl in clusters:
        if len(cl) < _EPISODE_MIN_POINTS:
            continue
        duration = (cl[-1].timestamp - cl[0].timestamp).total_seconds()
        if duration < _EPISODE_MIN_DURATION_SEC:
            continue
        min_hr = min(p.value for p in cl)
        episodes.append({"min_hr": min_hr, "point_count": len(cl), "duration_sec": duration})
    return episodes


def assess_bradycardia_risk(
    heart_rows: Iterable[tuple],
    sleep_segments: list[tuple[datetime, datetime]] | None = None,
    *,
    low_hr_event_count: int = 0,
    window: TimeWindow,
) -> RiskAssessment:
    heart = sorted(to_points(heart_rows), key=lambda p: p.timestamp)
    segments = merge_datetime_intervals(
        [(s, e) for s, e in (sleep_segments or []) if s and e and e > s]
    )

    if segments:
        rest_points = _sleep_rest_points(heart, segments)
    else:
        rest_points = _fallback_rest_points(heart)

    if len(rest_points) < _MIN_REST_POINTS:
        return RiskAssessment(
            condition="bradycardia_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных для оценки подозрения на брадикардию.",
            summary=f"Найдено {len(rest_points)} точек пульса в покое (нужно ≥{_MIN_REST_POINTS}).",
            recommendation="Проверь синхронизацию данных сна и пульса в Apple Health.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"rest_points_count": len(rest_points)},
        )

    episodes = _build_bradycardia_episodes(rest_points)
    rest_values = [p.value for p in rest_points]
    med_hr = median(rest_values)
    min_hr = min(rest_values)

    if not episodes and low_hr_event_count == 0:
        return RiskAssessment(
            condition="bradycardia_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(rest_points) / 60.0), 3),
            severity="none",
            interpretation="Устойчивых эпизодов брадикардии в покое не обнаружено.",
            summary="Подозрение на брадикардию: признаков не выявлено по текущим данным.",
            recommendation="Продолжай наблюдение; при головокружениях или обмороках обратись к врачу.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"rest_points_count": len(rest_points), "median_rest_hr": round(med_hr, 1), "min_rest_hr": round(min_hr, 1)},
        )

    episode_count_component = min(1.0, len(episodes) / 3.0)
    intensity_component = min(1.0, max(0.0, _BRADYCARDIA_THRESHOLD - min_hr) / 15.0)
    event_component = 1.0 if low_hr_event_count > 0 else 0.0

    score = 0.45 * episode_count_component + 0.35 * intensity_component + 0.20 * event_component

    if med_hr < _MEDIAN_STRONG_THRESHOLD:
        score = min(1.0, score + 0.15)
    if low_hr_event_count > 0:
        score = min(1.0, score + 0.25)

    score = round(score, 3)

    if score >= 0.75:
        severity = "high"
    elif score >= 0.45:
        severity = "medium"
    elif score > 0:
        severity = "low"
    else:
        severity = "none"

    confidence = round(min(1.0, len(rest_points) / 60.0) * 0.7 + min(1.0, len(episodes) / 3.0) * 0.3, 3)

    if severity in {"medium", "high"}:
        recommendation = (
            "Рекомендуется обратиться к кардиологу для ЭКГ или суточного мониторирования (Holter). "
            "Брадикардия у нетренированных людей или при симптомах требует оценки специалиста."
        )
    else:
        recommendation = "При головокружении, обмороках или усталости обратись к врачу."

    summary = (
        f"Подозрение на брадикардию: обнаружено {len(episodes)} эпизодов пульса <{_BRADYCARDIA_THRESHOLD} уд/мин "
        f"в покое. Минимальный пульс: {min_hr:.0f} уд/мин, медиана: {med_hr:.0f} уд/мин."
    )
    if low_hr_event_count > 0:
        summary += f" Apple Health зафиксировал {low_hr_event_count} событий низкого пульса."

    return RiskAssessment(
        condition="bradycardia_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Это не диагноз; подтверждение брадикардии требует ЭКГ. "
            "Оценка отражает вероятность по данным носимого устройства."
        ),
        summary=summary,
        recommendation=recommendation,
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "rest_points_count": len(rest_points),
            "episode_count": len(episodes),
            "min_rest_hr": round(min_hr, 1),
            "median_rest_hr": round(med_hr, 1),
            "low_hr_event_count": low_hr_event_count,
        },
    )
