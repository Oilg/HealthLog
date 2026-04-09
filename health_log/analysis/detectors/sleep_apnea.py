from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import (
    EventPoint,
    merge_datetime_intervals,
    nearest_value,
    to_points,
)


def _in_sleep_segments(ts: datetime, segments: list[tuple[datetime, datetime]]) -> bool:
    for start, end in segments:
        if start <= ts <= end:
            return True
    return False


def _sleep_hours_total(segments: list[tuple[datetime, datetime]]) -> float:
    merged = merge_datetime_intervals([(s, e) for s, e in segments if s and e and e > s])
    return sum((e - s).total_seconds() for s, e in merged) / 3600.0


@dataclass(slots=True)
class _ConfirmedPoint:
    timestamp: datetime
    rr: float
    supported_by_hr: bool
    supported_by_hrv: bool


@dataclass(slots=True)
class _Episode:
    points: list[_ConfirmedPoint]
    start_time: datetime
    end_time: datetime
    support_level: str


@dataclass(slots=True)
class _ApneaAnalysis:
    score: float
    confidence: float
    sleep_hours: float
    respiratory_count: int
    heart_count: int
    hrv_count: int
    baseline_rr: float
    baseline_hr: float
    baseline_hrv: float
    episodes: list[_Episode]
    risk_episodes: list[_Episode]
    valid_episode_count: int
    strong_episode_count: int
    median_resp_drop: float


def _filter_sleep(
    respiratory: list[EventPoint],
    heart: list[EventPoint],
    hrv: list[EventPoint],
    segments: list[tuple[datetime, datetime]],
) -> tuple[list[EventPoint], list[EventPoint], list[EventPoint]]:
    if not segments:
        return [], [], []
    return (
        [p for p in respiratory if _in_sleep_segments(p.timestamp, segments)],
        [p for p in heart if _in_sleep_segments(p.timestamp, segments)],
        [p for p in hrv if _in_sleep_segments(p.timestamp, segments)],
    )


def _analyze_sleep_apnea(
    respiratory_rows: Iterable[tuple],
    heart_rows: Iterable[tuple],
    hrv_rows: Iterable[tuple],
    sleep_segments: list[tuple[datetime, datetime]] | None,
) -> _ApneaAnalysis | None:
    respiratory = sorted(to_points(respiratory_rows), key=lambda p: p.timestamp)
    heart = sorted(to_points(heart_rows), key=lambda p: p.timestamp)
    hrv = sorted(to_points(hrv_rows), key=lambda p: p.timestamp)
    segments = merge_datetime_intervals(
        [(s, e) for s, e in (sleep_segments or []) if s and e and e > s]
    )

    if not segments:
        return None

    sleep_hours = _sleep_hours_total(segments)
    if sleep_hours < 4.0:
        return None

    respiratory, heart, hrv = _filter_sleep(respiratory, heart, hrv, segments)
    if len(respiratory) < 20:
        return None

    rr_ge_10 = [p.value for p in respiratory if p.value >= 10.0]
    if not rr_ge_10:
        return None
    baseline_rr = float(median(rr_ge_10))
    baseline_hr = float(median([p.value for p in heart])) if heart else 0.0
    baseline_hrv = float(median([p.value for p in hrv])) if hrv else 0.0

    confirmed: list[_ConfirmedPoint] = []
    for p in respiratory:
        if p.value >= 10.0:
            continue
        hr_near = nearest_value(heart, p.timestamp, max_seconds=120)
        hrv_near = nearest_value(hrv, p.timestamp, max_seconds=120)
        supported_by_hr = (
            hr_near is not None and baseline_hr > 0 and hr_near >= baseline_hr + 12.0
        )
        supported_by_hrv = (
            hrv_near is not None
            and baseline_hrv > 0
            and hrv_near <= baseline_hrv * 0.8
        )
        if not (supported_by_hr or supported_by_hrv):
            continue
        confirmed.append(
            _ConfirmedPoint(
                timestamp=p.timestamp,
                rr=p.value,
                supported_by_hr=supported_by_hr,
                supported_by_hrv=supported_by_hrv,
            )
        )

    confirmed.sort(key=lambda c: c.timestamp)
    episode_groups: list[list[_ConfirmedPoint]] = []
    if confirmed:
        cur = [confirmed[0]]
        for pt in confirmed[1:]:
            if (pt.timestamp - cur[-1].timestamp).total_seconds() <= 300:
                cur.append(pt)
            else:
                episode_groups.append(cur)
                cur = [pt]
        episode_groups.append(cur)

    episodes: list[_Episode] = []
    for grp in episode_groups:
        if len(grp) < 2:
            continue
        dur = (grp[-1].timestamp - grp[0].timestamp).total_seconds()
        if dur < 120:
            continue
        has_hr = any(p.supported_by_hr for p in grp)
        has_hrv = any(p.supported_by_hrv for p in grp)
        if has_hr and has_hrv:
            sl = "strong"
        elif has_hr or has_hrv:
            sl = "medium"
        else:
            sl = "weak"
        episodes.append(
            _Episode(
                points=grp,
                start_time=grp[0].timestamp,
                end_time=grp[-1].timestamp,
                support_level=sl,
            )
        )

    risk_eps = [e for e in episodes if e.support_level in {"strong", "medium"}]
    valid_count = len(risk_eps)
    strong_count = sum(1 for e in risk_eps if e.support_level == "strong")

    drops: list[float] = []
    for e in risk_eps:
        med_rr = float(median([p.rr for p in e.points]))
        drops.append(baseline_rr - med_rr)
    median_resp_drop = float(median(drops)) if drops else 0.0

    episode_density = valid_count / sleep_hours if sleep_hours > 0 else 0.0
    density_component = min(1.0, episode_density / 5.0)
    support_component = min(1.0, strong_count / max(1, valid_count))
    depth_component = min(1.0, max(0.0, median_resp_drop) / 6.0)
    score = 0.5 * density_component + 0.3 * support_component + 0.2 * depth_component

    rr_cov = min(1.0, len(respiratory) / 40.0)
    cross = min(1.0, (len(heart) + len(hrv)) / max(1, len(respiratory)))
    sleep_h = min(1.0, sleep_hours / 7.0)
    confidence = 0.4 * rr_cov + 0.35 * cross + 0.25 * sleep_h

    return _ApneaAnalysis(
        score=score,
        confidence=confidence,
        sleep_hours=sleep_hours,
        respiratory_count=len(respiratory),
        heart_count=len(heart),
        hrv_count=len(hrv),
        baseline_rr=baseline_rr,
        baseline_hr=baseline_hr,
        baseline_hrv=baseline_hrv,
        episodes=episodes,
        risk_episodes=risk_eps,
        valid_episode_count=valid_count,
        strong_episode_count=strong_count,
        median_resp_drop=median_resp_drop,
    )


def build_sleep_apnea_event_rows(
    respiratory_rows: Iterable[tuple],
    heart_rows: Iterable[tuple],
    hrv_rows: Iterable[tuple],
    sleep_segments: list[tuple[datetime, datetime]] | None = None,
    *,
    detected_by: str = "rule_engine_v1",
) -> list[dict[str, object]]:
    result = _analyze_sleep_apnea(respiratory_rows, heart_rows, hrv_rows, sleep_segments)
    if result is None:
        return []

    confidence = result.confidence
    baseline_rr = result.baseline_rr
    baseline_hr = result.baseline_hr
    baseline_hrv = result.baseline_hrv
    sleep_hours_context = result.sleep_hours

    heart_pts = sorted(to_points(heart_rows), key=lambda p: p.timestamp)
    hrv_pts = sorted(to_points(hrv_rows), key=lambda p: p.timestamp)
    baseline_hr_v = result.baseline_hr
    baseline_hrv_v = result.baseline_hrv

    rows: list[dict[str, object]] = []
    for ep in result.risk_episodes:
        max_hr_spike = 0.0
        max_hrv_drop_pct = 0.0
        for p in ep.points:
            hr_near = nearest_value(heart_pts, p.timestamp, max_seconds=120)
            if hr_near is not None and baseline_hr_v > 0:
                max_hr_spike = max(max_hr_spike, hr_near - baseline_hr_v)
            hrv_near = nearest_value(hrv_pts, p.timestamp, max_seconds=120)
            if hrv_near is not None and baseline_hrv_v > 0:
                drop_pct = max(0.0, (baseline_hrv_v - hrv_near) / baseline_hrv_v * 100.0)
                max_hrv_drop_pct = max(max_hrv_drop_pct, drop_pct)

        rows.append(
            {
                "start_time": ep.start_time,
                "end_time": ep.end_time,
                "respiratory_rate_drop": baseline_rr - float(median([x.rr for x in ep.points])),
                "heart_rate_spike": max_hr_spike if max_hr_spike > 0 else None,
                "hrv_change": -max_hrv_drop_pct if max_hrv_drop_pct > 0 else None,
                "severity": ep.support_level,
                "detected_by": detected_by,
                "point_count": len(ep.points),
                "support_level": ep.support_level,
                "confidence": confidence,
                "baseline_rr": baseline_rr,
                "baseline_hr": baseline_hr,
                "baseline_hrv": baseline_hrv,
                "sleep_hours_context": sleep_hours_context,
            }
        )
    return rows


def assess_sleep_apnea_risk(
    respiratory_rows: Iterable[tuple],
    heart_rows: Iterable[tuple],
    hrv_rows: Iterable[tuple],
    sleep_segments: list[tuple[datetime, datetime]] | None = None,
    *,
    window: TimeWindow,
) -> RiskAssessment:
    result = _analyze_sleep_apnea(respiratory_rows, heart_rows, hrv_rows, sleep_segments)
    if result is None:
        return RiskAssessment(
            condition="sleep_apnea_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных для интерпретации уровня риска и достоверности сигнала.",
            summary="Недостаточно ночных данных сна или дыхания для оценки подозрения на апноэ.",
            recommendation="Проверь, что Apple Watch носится во время сна и данные синхронизируются.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    score = result.score
    confidence = result.confidence
    valid_count = result.valid_episode_count

    if score >= 0.75:
        severity = "high"
    elif score >= 0.45:
        severity = "medium"
    elif score > 0:
        severity = "low"
    else:
        severity = "none"

    summary = (
        f"По данным ночного сна (~{result.sleep_hours:.1f} ч): подтверждённых подозрительных эпизодов "
        f"дыхания (RR<10 с поддержкой HR/HRV): {valid_count}."
    )
    recommendation = (
        "Сигнал не является клиническим диагнозом и не заменяет полисомнографию; AHI по этим данным не считается. "
        "Если паттерн повторяется, обсуди результаты с врачом."
    )

    interpretation = (
        "Оценка отражает вероятностный риск по данным Apple Health; это не диагноз и не замена полисомнографии."
    )

    return RiskAssessment(
        condition="sleep_apnea_risk",
        window=window,
        score=round(score, 3),
        confidence=round(confidence, 3),
        severity=severity,
        interpretation=interpretation,
        summary=summary,
        recommendation=recommendation,
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
    )
