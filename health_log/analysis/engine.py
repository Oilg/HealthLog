from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.analysis.detectors import (
    assess_illness_onset_risk,
    assess_menstrual_cycle_delay_risk,
    assess_menstrual_cycle_start_forecast,
    assess_ovulation_window_forecast,
    assess_sleep_apnea_risk,
    assess_tachycardia_risk,
    build_sleep_apnea_event_rows,
)
from health_log.analysis.detectors.illness.constants import ILLNESS_TREND_LOOKBACK_DAYS
from health_log.analysis.models import RiskAssessment, TimeWindow
from health_log.analysis.windows import resolve_window_range
from health_log.repositories.repository import RecordsRepository
from health_log.repositories.v1 import tables


class HealthRiskAnalyzer:
    def __init__(self, connection: AsyncConnection, user_id: int):
        self._connection = connection
        self._user_id = user_id
        self._user_sex: str | None = None
        self._records_repo = RecordsRepository(connection)

    async def _fetch_rows(self, table, start: datetime, end: datetime):
        query = (
            select(table.c.startDate, table.c.value)
            .where(
                and_(
                    table.c.user_id == self._user_id,
                    table.c.startDate >= start,
                    table.c.startDate <= end,
                )
            )
            .order_by(table.c.startDate)
        )
        return (await self._connection.execute(query)).all()

    async def _fetch_sleep_segments(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        query = (
            select(tables.sleep_analysis.c.startDate, tables.sleep_analysis.c.endDate)
            .where(
                and_(
                    tables.sleep_analysis.c.user_id == self._user_id,
                    tables.sleep_analysis.c.startDate <= end,
                    tables.sleep_analysis.c.endDate >= start,
                )
            )
            .order_by(tables.sleep_analysis.c.startDate)
        )
        return list((await self._connection.execute(query)).all())

    async def _fetch_user_sex(self) -> str:
        if self._user_sex is not None:
            return self._user_sex
        query = select(tables.users.c.sex).where(tables.users.c.id == self._user_id)
        sex = (await self._connection.execute(query)).scalar_one_or_none() or "male"
        self._user_sex = str(sex)
        return self._user_sex

    async def analyze_window(self, window: TimeWindow, now: datetime | None = None) -> dict[str, object]:
        now = now or datetime.utcnow()
        start, end = resolve_window_range(window, now)
        illness_start = end - timedelta(days=ILLNESS_TREND_LOOKBACK_DAYS)
        cycle_start = end - timedelta(days=180)
        user_sex = await self._fetch_user_sex()

        respiratory_rows = await self._fetch_rows(tables.respiratory_rate, start, end)
        heart_rows = await self._fetch_rows(tables.heart_rate, start, end)
        hrv_rows = await self._fetch_rows(tables.heart_rate_variability, start, end)
        sleep_segments = await self._fetch_sleep_segments(start, end)
        illness_heart_rows = await self._fetch_rows(tables.heart_rate, illness_start, end)
        illness_hrv_rows = await self._fetch_rows(tables.heart_rate_variability, illness_start, end)
        illness_respiratory_rows = await self._fetch_rows(tables.respiratory_rate, illness_start, end)
        illness_sleep_segments = await self._fetch_sleep_segments(illness_start, end)
        menstrual_rows = []
        if user_sex == "female":
            menstrual_rows = await self._fetch_rows(tables.menstrual_flow, cycle_start, end)

        sleep_apnea_result = assess_sleep_apnea_risk(
            respiratory_rows,
            heart_rows,
            hrv_rows,
            sleep_segments=sleep_segments,
            window=window,
        )
        tachycardia_result = assess_tachycardia_risk(
            heart_rows,
            sleep_segments=sleep_segments,
            window=window,
        )
        illness_onset_result = assess_illness_onset_risk(
            illness_heart_rows,
            illness_hrv_rows,
            respiratory_rows=illness_respiratory_rows,
            sleep_rows=illness_sleep_segments,
            window=window,
        )
        menstrual_assessments: list[RiskAssessment] = []
        if user_sex == "female":
            menstrual_assessments = [
                assess_menstrual_cycle_start_forecast(menstrual_rows, window=window, now=now),
                assess_menstrual_cycle_delay_risk(menstrual_rows, window=window, now=now),
                assess_ovulation_window_forecast(menstrual_rows, window=window, now=now),
            ]

        inserted_events = 0
        if window == TimeWindow.NIGHT:
            events = build_sleep_apnea_event_rows(
                respiratory_rows,
                heart_rows,
                hrv_rows,
                sleep_segments=sleep_segments,
            )
            inserted_events = await self._records_repo.insert_sleep_apnea_events(self._user_id, events)

        assessments = [sleep_apnea_result, tachycardia_result, illness_onset_result, *menstrual_assessments]

        return {
            "window": window,
            "start": start,
            "end": end,
            "assessments": assessments,
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
        "menstrual_cycle_start_forecast": "Прогноз: скорое начало менструации",
        "menstrual_cycle_delay_risk": "Прогноз: возможная задержка менструации",
        "ovulation_window_forecast": "Прогноз: окно вероятной овуляции",
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
