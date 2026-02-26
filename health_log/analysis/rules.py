from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Iterable

from health_log.analysis.models import RiskAssessment, SignalEvidence, TimeWindow


CLINICAL_SAFETY_NOTE = (
    "Это не медицинский диагноз. Сервис показывает риск-сигнал и не заменяет врача. "
    "Если симптомы повторяются или есть ухудшение самочувствия, обратись к специалисту."
)


def build_score_confidence_interpretation(score: float, confidence: float) -> str:
    if score >= 0.6 and confidence < 0.5:
        return "Высокий уровень риска при низкой достоверности сигнала: подозрение есть, но данных пока мало."
    if score >= 0.6 and confidence >= 0.5:
        return "Высокий уровень риска и высокая достоверность сигнала: сигнал устойчивый, стоит проверить у врача."
    if score < 0.3 and confidence >= 0.5:
        return "Низкий уровень риска при нормальной достоверности сигнала: явного устойчивого риска по текущим данным нет."
    return "Сигнал промежуточный: наблюдай динамику и собирай данные дальше."


@dataclass(slots=True)
class EventPoint:
    timestamp: datetime
    value: float


def _safe_float(raw: object) -> float | None:
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


def _to_points(rows: Iterable[tuple[datetime, object]]) -> list[EventPoint]:
    points: list[EventPoint] = []
    for ts, raw in rows:
        value = _safe_float(raw)
        if ts is None or value is None:
            continue
        points.append(EventPoint(timestamp=ts, value=value))
    return points


def _nearest_value(points: list[EventPoint], target_ts: datetime, max_seconds: int) -> float | None:
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


def build_sleep_apnea_event_rows(
    respiratory_rows: Iterable[tuple[datetime, object]],
    heart_rows: Iterable[tuple[datetime, object]],
    hrv_rows: Iterable[tuple[datetime, object]],
    *,
    detected_by: str = "rule_engine_v1",
) -> list[dict[str, object]]:
    respiratory = _to_points(respiratory_rows)
    heart = _to_points(heart_rows)
    hrv = _to_points(hrv_rows)

    if len(respiratory) < 2:
        return []

    heart_baseline = median([p.value for p in heart]) if heart else None
    hrv_baseline = median([p.value for p in hrv]) if hrv else None

    events: list[dict[str, object]] = []
    for idx in range(1, len(respiratory)):
        prev_point = respiratory[idx - 1]
        current = respiratory[idx]
        if current.value >= 10:
            continue

        duration = (current.timestamp - prev_point.timestamp).total_seconds()
        if duration < 10:
            continue

        heart_near = _nearest_value(heart, current.timestamp, max_seconds=120)
        hrv_near = _nearest_value(hrv, current.timestamp, max_seconds=120)

        respiratory_drop = None
        if idx >= 10:
            prev_window = [respiratory[i].value for i in range(max(0, idx - 10), idx)]
            baseline_resp = median(prev_window) if prev_window else None
            if baseline_resp is not None:
                respiratory_drop = max(0.0, baseline_resp - current.value)

        heart_spike = None
        if heart_near is not None and heart_baseline is not None:
            heart_spike = heart_near - heart_baseline

        hrv_change = None
        if hrv_near is not None and hrv_baseline is not None:
            hrv_change = hrv_near - hrv_baseline

        severity = "mild"
        if (heart_spike is not None and heart_spike >= 20) or (respiratory_drop is not None and respiratory_drop >= 4):
            severity = "moderate"
        if (heart_spike is not None and heart_spike >= 30) and (hrv_change is not None and hrv_change <= -10):
            severity = "severe"

        events.append(
            {
                "start_time": prev_point.timestamp,
                "end_time": current.timestamp,
                "respiratory_rate_drop": respiratory_drop,
                "heart_rate_spike": heart_spike,
                "hrv_change": hrv_change,
                "severity": severity,
                "detected_by": detected_by,
            }
        )

    return events


def assess_sleep_apnea_risk(
    respiratory_rows: Iterable[tuple[datetime, object]],
    heart_rows: Iterable[tuple[datetime, object]],
    hrv_rows: Iterable[tuple[datetime, object]],
    *,
    window: TimeWindow,
) -> RiskAssessment:
    respiratory = _to_points(respiratory_rows)
    heart = _to_points(heart_rows)
    hrv = _to_points(hrv_rows)

    evidence = SignalEvidence(data_points=len(respiratory))

    if not respiratory:
        return RiskAssessment(
            condition="sleep_apnea_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных для интерпретации уровня риска и достоверности сигнала.",
            summary="Недостаточно данных дыхания для оценки.",
            recommendation="Проверь, что Apple Watch носится во время сна и данные синхронизируются.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
        )

    baseline_hr = median([p.value for p in heart]) if heart else None
    baseline_hrv = median([p.value for p in hrv]) if hrv else None

    for point in respiratory:
        if point.value < 10:
            evidence.low_respiratory_events += 1

            hr_near = _nearest_value(heart, point.timestamp, max_seconds=120)
            if hr_near is not None and baseline_hr is not None and hr_near >= baseline_hr + 12:
                evidence.hr_spike_events += 1

            hrv_near = _nearest_value(hrv, point.timestamp, max_seconds=120)
            if hrv_near is not None and baseline_hrv is not None and hrv_near <= baseline_hrv * 0.8:
                evidence.hrv_drop_events += 1

    score = min(
        1.0,
        evidence.low_respiratory_events * 0.1
        + evidence.hr_spike_events * 0.18
        + evidence.hrv_drop_events * 0.22,
    )

    signal_coverage = min(1.0, (len(heart) + len(hrv)) / max(1, len(respiratory)))
    confidence = min(1.0, (len(respiratory) / 120.0) * 0.6 + signal_coverage * 0.4)

    if score >= 0.75:
        severity = "high"
    elif score >= 0.45:
        severity = "medium"
    elif score > 0:
        severity = "low"
    else:
        severity = "none"

    summary = (
        f"Обнаружено случаев пониженной частоты дыхания: {evidence.low_respiratory_events}; "
        f"из них со всплеском пульса: {evidence.hr_spike_events}; "
        f"со снижением вариабельности сердечного ритма (HRV): {evidence.hrv_drop_events}."
    )

    recommendation = (
        "Если сигнал повторяется несколько ночей подряд, стоит обсудить результаты с сомнологом "
        "и рассмотреть клиническое обследование сна."
    )

    return RiskAssessment(
        condition="sleep_apnea_risk",
        window=window,
        score=round(score, 3),
        confidence=round(confidence, 3),
        severity=severity,
        interpretation=build_score_confidence_interpretation(score, confidence),
        summary=summary,
        recommendation=recommendation,
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
    )


def assess_tachycardia_risk(
    heart_rows: Iterable[tuple[datetime, object]],
    *,
    window: TimeWindow,
) -> RiskAssessment:
    heart = _to_points(heart_rows)

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

    episodes = 0
    for point in heart:
        if point.value >= 100:
            episodes += 1

    score = min(1.0, episodes * 0.03)
    confidence = min(1.0, len(heart) / 300.0)

    if score >= 0.7:
        severity = "high"
    elif score >= 0.35:
        severity = "medium"
    elif score > 0:
        severity = "low"
    else:
        severity = "none"

    summary = f"Обнаружено случаев пульса >= 100 уд/мин: {episodes}."
    recommendation = (
        "Если такие эпизоды частые или есть симптомы (одышка, слабость, боль в груди), "
        "обратись к кардиологу."
    )

    return RiskAssessment(
        condition="tachycardia_risk",
        window=window,
        score=round(score, 3),
        confidence=round(confidence, 3),
        severity=severity,
        interpretation=build_score_confidence_interpretation(score, confidence),
        summary=summary,
        recommendation=recommendation,
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
    )


def resolve_window_range(window: TimeWindow, now: datetime) -> tuple[datetime, datetime]:
    if window == TimeWindow.NIGHT:
        end = now
        start = now - timedelta(hours=12)
        return start, end
    if window == TimeWindow.WEEK:
        end = now
        start = now - timedelta(days=7)
        return start, end
    end = now
    start = now - timedelta(days=30)
    return start, end
