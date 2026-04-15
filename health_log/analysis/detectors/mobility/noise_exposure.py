from __future__ import annotations

from datetime import datetime, timedelta
from health_log.utils import utcnow
from typing import Iterable

from health_log.analysis.constants import CLINICAL_SAFETY_NOTE
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.utils import to_points

_MIN_AUDIO_EVENTS = 3
_NOISE_LOOKBACK_7D = 7
_NOISE_LOOKBACK_30D = 30


def assess_noise_exposure_risk(
    env_audio_rows: Iterable[tuple] | None = None,
    headphone_audio_rows: Iterable[tuple] | None = None,
    *,
    window: TimeWindow,
    now: datetime | None = None,
) -> RiskAssessment:
    now = now or utcnow()
    cutoff_7d = now - timedelta(days=_NOISE_LOOKBACK_7D)
    cutoff_30d = now - timedelta(days=_NOISE_LOOKBACK_30D)

    env_points = to_points(env_audio_rows or [])
    hp_points = to_points(headphone_audio_rows or [])
    all_points = env_points + hp_points

    recent_points = [p for p in all_points if p.timestamp >= cutoff_7d]
    month_points = [p for p in all_points if p.timestamp >= cutoff_30d]

    if len(month_points) < _MIN_AUDIO_EVENTS:
        return RiskAssessment(
            condition="noise_exposure_risk",
            window=window,
            score=0.0,
            confidence=0.0,
            severity="unknown",
            interpretation="Недостаточно данных аудиоэкспозиции.",
            summary=f"Найдено {len(month_points)} событий за 30 дней (нужно ≥{_MIN_AUDIO_EVENTS}).",
            recommendation="Проверь синхронизацию данных шумовой экспозиции в Apple Health.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"events_30d": len(month_points)},
        )

    max_db_7d = max((p.value for p in recent_points), default=0.0)
    max_db_30d = max((p.value for p in month_points), default=0.0)
    avg_db_7d = sum(p.value for p in recent_points) / len(recent_points) if recent_points else 0.0
    avg_db_30d = sum(p.value for p in month_points) / len(month_points) if month_points else 0.0

    peak = max(max_db_7d, max_db_30d)

    if peak >= 90 or avg_db_7d >= 90:
        severity = "high"
        score = 0.85
    elif peak >= 85 or avg_db_7d >= 85:
        severity = "medium"
        score = 0.60
    elif peak >= 80 or avg_db_7d >= 80:
        severity = "low"
        score = 0.35
    else:
        return RiskAssessment(
            condition="noise_exposure_risk",
            window=window,
            score=0.0,
            confidence=round(min(1.0, len(month_points) / 10.0), 3),
            severity="none",
            interpretation="Вредного шумового воздействия не выявлено.",
            summary=f"Уровень шума в норме: пик {peak:.0f} dB, среднее за 7 дней {avg_db_7d:.0f} dB.",
            recommendation="Продолжай контролировать уровень шума.",
            clinical_safety_note=CLINICAL_SAFETY_NOTE,
            supporting_metrics={"max_db_30d": round(max_db_30d, 1), "avg_db_7d": round(avg_db_7d, 1)},
        )

    score = round(score, 3)
    confidence = round(min(1.0, len(month_points) / 20.0), 3)

    return RiskAssessment(
        condition="noise_exposure_risk",
        window=window,
        score=score,
        confidence=confidence,
        severity=severity,
        interpretation=(
            "Длительное воздействие звука ≥80 dB может вызывать шумовую нейросенсорную тугоухость. "
            "Оценка основана на данных Apple Health."
        ),
        summary=(
            f"Подозрение на вредное шумовое воздействие: пик {peak:.0f} dB, "
            f"среднее за 7 дней {avg_db_7d:.0f} dB."
        ),
        recommendation=(
            "Используй средства защиты слуха в шумных условиях. "
            "При снижении слуха обратись к отоларингологу (ЛОР)."
        ),
        clinical_safety_note=CLINICAL_SAFETY_NOTE,
        supporting_metrics={
            "max_db_7d": round(max_db_7d, 1),
            "max_db_30d": round(max_db_30d, 1),
            "avg_db_7d": round(avg_db_7d, 1),
            "avg_db_30d": round(avg_db_30d, 1),
            "events_7d": len(recent_points),
            "events_30d": len(month_points),
        },
    )
