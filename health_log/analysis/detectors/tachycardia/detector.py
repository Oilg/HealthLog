from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import EventPoint, merge_datetime_intervals, to_points


def _in_sleep(ts: datetime, segments: list[tuple[datetime, datetime]]) -> bool:
    for start, end in segments:
        if start <= ts <= end:
            return True
    return False


def _sleep_total_hours(segments: list[tuple[datetime, datetime]]) -> float:
    merged = merge_datetime_intervals([(s, e) for s, e in segments if s is not None and e is not None and e > s])
    return sum((e - s).total_seconds() for s, e in merged) / 3600.0


def _rest_points_from_sleep(heart: list[EventPoint], segments: list[tuple[datetime, datetime]]) -> list[EventPoint]:
    return [p for p in heart if _in_sleep(p.timestamp, segments)]


def _percentile_20_threshold(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = max(0, int(0.2 * (len(s) - 1)))
    return s[idx]


def _rest_like_daytime_points(heart: list[EventPoint], segments: list[tuple[datetime, datetime]]) -> list[EventPoint]:
    outside = [p for p in heart if not _in_sleep(p.timestamp, segments)]
    if not outside:
        return []
    thr = _percentile_20_threshold([p.value for p in heart])
    if thr is None:
        return []
    candidates = [p for p in outside if p.value <= thr]
    candidates.sort(key=lambda p: p.timestamp)
    if not candidates:
        return []
    clusters: list[list[EventPoint]] = []
    cur = [candidates[0]]
    for p in candidates[1:]:
        if (p.timestamp - cur[-1].timestamp).total_seconds() <= 120:
            cur.append(p)
        else:
            clusters.append(cur)
            cur = [p]
    clusters.append(cur)
    rest: list[EventPoint] = []
    for cl in clusters:
        span = (cl[-1].timestamp - cl[0].timestamp).total_seconds()
        if span >= 300:
            rest.extend(cl)
    return rest


def _rest_context_intervals(
    used_sleep: bool,
    heart: list[EventPoint],
    segments: list[tuple[datetime, datetime]],
    rest_points: list[EventPoint],
) -> list[tuple[datetime, datetime]]:
    if used_sleep:
        return merge_datetime_intervals(list(segments))
    clusters: list[list[EventPoint]] = []
    rest_sorted = sorted(rest_points, key=lambda p: p.timestamp)
    if not rest_sorted:
        return []
    cur = [rest_sorted[0]]
    for p in rest_sorted[1:]:
        if (p.timestamp - cur[-1].timestamp).total_seconds() <= 120:
            cur.append(p)
        else:
            clusters.append(cur)
            cur = [p]
    clusters.append(cur)
    intervals: list[tuple[datetime, datetime]] = []
    for cl in clusters:
        span = (cl[-1].timestamp - cl[0].timestamp).total_seconds()
        if span >= 300:
            intervals.append((cl[0].timestamp, cl[-1].timestamp))
    return merge_datetime_intervals(intervals)


def _point_in_intervals(ts: datetime, intervals: list[tuple[datetime, datetime]]) -> bool:
    for start, end in intervals:
        if start <= ts <= end:
            return True
    return False


def _build_episodes(
    heart_sorted: list[EventPoint],
    rest_intervals: list[tuple[datetime, datetime]],
    rest_baseline_hr: float,
) -> list[dict[str, float | int]]:
    # Cluster ALL resting points (not just >100) so the 70% check evaluates
    # the full continuous timeline; two isolated spikes separated by normal
    # measurements cannot silently merge into a single "episode".
    rest_all = [p for p in heart_sorted if _point_in_intervals(p.timestamp, rest_intervals)]
    if not rest_all:
        return []
    episodes_raw: list[list[EventPoint]] = []
    cur = [rest_all[0]]
    for p in rest_all[1:]:
        if (p.timestamp - cur[-1].timestamp).total_seconds() <= 120:
            cur.append(p)
        else:
            episodes_raw.append(cur)
            cur = [p]
    episodes_raw.append(cur)
    episodes: list[dict[str, float | int]] = []
    for ep in episodes_raw:
        if len(ep) < 3:
            continue
        duration_sec = (ep[-1].timestamp - ep[0].timestamp).total_seconds()
        if duration_sec < 300:
            continue
        hi = sum(1 for p in ep if p.value > 100)
        if hi / len(ep) < 0.7:
            continue
        peak_hr = max(p.value for p in ep)
        med_hr = float(median([p.value for p in ep]))
        delta = med_hr - rest_baseline_hr
        if delta < 15 or peak_hr < 105:
            continue
        episodes.append(
            {
                "peak_hr": peak_hr,
                "median_hr": med_hr,
                "duration_minutes": duration_sec / 60.0,
                "delta_from_baseline": delta,
            }
        )
    return episodes


def assess_tachycardia_risk(
    heart_rows: Iterable[tuple],
    sleep_segments: list[tuple[datetime, datetime]] | None = None,
    *,
    window: TimeWindow,
) -> RiskAssessment:
    heart = sorted(to_points(heart_rows), key=lambda p: p.timestamp)
    segments = list(sleep_segments or [])
    merged_sleep = merge_datetime_intervals([(s, e) for s, e in segments if s and e and e > s])

    if not heart:
        return RiskAssessment(
            condition="tachycardia_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных для интерпретации уровня риска и достоверности сигнала.",
            summary="Недостаточно данных пульса для оценки.",
            recommendation="Проверь синхронизацию данных пульса из Apple Health.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    used_sleep = bool(merged_sleep)
    if used_sleep:
        rest_points = _rest_points_from_sleep(heart, merged_sleep)
    else:
        rest_points = _rest_like_daytime_points(heart, merged_sleep)

    if len(rest_points) < 10:
        return RiskAssessment(
            condition="tachycardia_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation=(
                "Это не диагноз; окончательное подтверждение тахикардии требует ЭКГ или ритм-мониторинга (Holter). "
                "Недостаточно точек пульса в покое для устойчивой оценки."
            ),
            summary="Недостаточно данных пульса в покое для оценки подозрения на тахикардию.",
            recommendation="Проверь синхронизацию данных и наличие записей сна в Apple Health.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    rest_baseline_hr = float(median([p.value for p in rest_points]))
    rest_intervals = _rest_context_intervals(used_sleep, heart, merged_sleep, rest_points)
    episodes = _build_episodes(heart, rest_intervals, rest_baseline_hr)

    if not episodes:
        confidence_raw = _tachycardia_confidence(
            used_sleep=used_sleep,
            merged_sleep=merged_sleep,
            rest_points_count=len(rest_points),
            episode_count=0,
        )
        return RiskAssessment(
            condition="tachycardia_risk",
            window=window,
            score=0.0,
            confidence=round(confidence_raw, 3),
            severity="none",
            interpretation=(
                "Это не диагноз; окончательное подтверждение тахикардии требует ЭКГ или ритм-мониторинга. "
                "По данным wearables устойчивых эпизодов повышенного пульса в покое не выявлено."
            ),
            summary="Подозрение на тахикардию: устойчивых эпизодов пульса >100 уд/мин в покое не обнаружено.",
            recommendation="Продолжай наблюдение; при появлении симптомов обратись к врачу.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    total_minutes = sum(float(e["duration_minutes"]) for e in episodes)
    max_peak_over = max(float(e["peak_hr"]) - 100.0 for e in episodes)
    episode_count_component = min(1.0, len(episodes) / 3.0)
    duration_component = min(1.0, total_minutes / 30.0)
    intensity_component = min(1.0, max(0.0, max_peak_over) / 30.0)
    score = 0.4 * episode_count_component + 0.35 * duration_component + 0.25 * intensity_component

    if score >= 0.75:
        severity = "high"
    elif score >= 0.45:
        severity = "medium"
    elif score > 0:
        severity = "low"
    else:
        severity = "none"

    confidence_raw = _tachycardia_confidence(
        used_sleep=used_sleep,
        merged_sleep=merged_sleep,
        rest_points_count=len(rest_points),
        episode_count=len(episodes),
    )

    ctx = "сна" if used_sleep else "покоя"
    summary = (
        f"Подозрение на тахикардию. Во время {ctx} обнаружено {len(episodes)} эпизодов повышенного пульса "
        f">100 уд/мин, суммарной длительностью {total_minutes:.0f} мин."
    )

    if (severity in {"high", "medium"}) and confidence_raw >= 0.5:
        recommendation = (
            "Если эпизоды повторяются или сопровождаются слабостью, одышкой, болью в груди, "
            "стоит обсудить результаты с кардиологом и рассмотреть ЭКГ/Holter."
        )
    else:
        recommendation = (
            "Сигнал носит вероятностный характер по данным wearables; при симптомах или сомнениях проконсультируйся с врачом."
        )

    interpretation = (
        "Это не диагноз; окончательное подтверждение тахикардии требует ЭКГ или ритм-мониторинга (Holter). "
        "Оценка отражает вероятность клинически значимого эпизода по данным носимого устройства."
    )

    return RiskAssessment(
        condition="tachycardia_risk",
        window=window,
        score=round(score, 3),
        confidence=round(confidence_raw, 3),
        severity=severity,
        interpretation=interpretation,
        summary=summary,
        recommendation=recommendation,
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
    )


def _tachycardia_confidence(
    *,
    used_sleep: bool,
    merged_sleep: list[tuple[datetime, datetime]],
    rest_points_count: int,
    episode_count: int,
) -> float:
    sleep_hours = _sleep_total_hours(merged_sleep)
    sleep_coverage_component = min(1.0, sleep_hours / 6.0)
    point_density_component = min(1.0, rest_points_count / 60.0)
    signal_consistency_component = min(1.0, episode_count / 2.0)
    confidence = (
        0.5 * sleep_coverage_component + 0.3 * point_density_component + 0.2 * signal_consistency_component
    )
    if not used_sleep:
        confidence *= 0.7
    return min(1.0, confidence)
