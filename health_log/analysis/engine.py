from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.analysis.detectors import (
    assess_illness_onset_risk,
    assess_sleep_apnea_risk,
    assess_tachycardia_risk,
    build_sleep_apnea_event_rows,
)
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.windows import resolve_window_range
from health_log.repositories.repository import RecordsRepository
from health_log.repositories.v1 import tables


class HealthRiskAnalyzer:
    def __init__(self, connection: AsyncConnection):
        self._connection = connection
        self._records_repo = RecordsRepository(connection)

    async def _fetch_rows(self, table, start: datetime, end: datetime):
        query = (
            select(table.c.startDate, table.c.value)
            .where(and_(table.c.startDate >= start, table.c.startDate <= end))
            .order_by(table.c.startDate)
        )
        return (await self._connection.execute(query)).all()

    async def analyze_window(self, window: TimeWindow, now: datetime | None = None) -> dict[str, object]:
        now = now or datetime.utcnow()
        start, end = resolve_window_range(window, now)

        respiratory_rows = await self._fetch_rows(tables.respiratory_rate, start, end)
        heart_rows = await self._fetch_rows(tables.heart_rate, start, end)
        hrv_rows = await self._fetch_rows(tables.heart_rate_variability, start, end)

        sleep_apnea_result = assess_sleep_apnea_risk(
            respiratory_rows,
            heart_rows,
            hrv_rows,
            window=window,
        )
        tachycardia_result = assess_tachycardia_risk(heart_rows, window=window)
        illness_onset_result = assess_illness_onset_risk(heart_rows, hrv_rows, window=window)

        inserted_events = 0
        if window == TimeWindow.NIGHT:
            events = build_sleep_apnea_event_rows(respiratory_rows, heart_rows, hrv_rows)
            inserted_events = await self._records_repo.insert_sleep_apnea_events(events)

        return {
            "window": window,
            "start": start,
            "end": end,
            "assessments": [sleep_apnea_result, tachycardia_result, illness_onset_result],
            "inserted_sleep_apnea_events": inserted_events,
        }

    async def analyze_all_windows(self, now: datetime | None = None) -> dict[TimeWindow, dict[str, object]]:
        return {
            window: await self.analyze_window(window, now=now)
            for window in (TimeWindow.NIGHT, TimeWindow.WEEK, TimeWindow.MONTH)
        }


def serialize_assessment(assessment: RiskAssessment) -> dict[str, object]:
    condition_label = {
        "sleep_apnea_risk": "Подозрение на апноэ сна",
        "tachycardia_risk": "Подозрение на тахикардию",
        "illness_onset_risk": "Подозрение на начало простуды/воспалительного процесса",
    }.get(assessment.condition, assessment.condition)
    final_message = (
        f"{condition_label}. Уровень риска: {assessment.score:.2f}, "
        f"достоверность сигнала: {assessment.confidence:.2f}. "
        f"{assessment.interpretation} {assessment.recommendation}"
    )

    return {
        "condition": assessment.condition,
        "подозреваемое_состояние": condition_label,
        "window": assessment.window.value,
        "score": assessment.score,
        "confidence": assessment.confidence,
        "уровень_риска": assessment.score,
        "достоверность_сигнала": assessment.confidence,
        "severity": assessment.severity,
        "interpretation": assessment.interpretation,
        "summary": assessment.summary,
        "recommendation": assessment.recommendation,
        "итоговое_сообщение": final_message,
        "clinical_safety_note": assessment.clinical_safety_note,
        "created_at": assessment.created_at.isoformat(),
    }
