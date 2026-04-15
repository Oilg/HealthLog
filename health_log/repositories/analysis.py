from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.repositories.v1 import tables


class AnalysisReportsRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def save_report(
        self,
        *,
        user_id: int,
        analyzed_at: datetime,
        period_from: datetime,
        period_to: datetime,
        window: str,
        risks: list[dict],
    ) -> int:
        stmt = (
            pg_insert(tables.analysis_reports)
            .values(
                user_id=user_id,
                analyzed_at=analyzed_at,
                period_from=period_from,
                period_to=period_to,
                window=window,
                risks=risks,
            )
            .returning(tables.analysis_reports.c.id)
        )
        result = await self._connection.execute(stmt)
        return result.scalar_one()

    async def get_latest_report(self, user_id: int) -> dict | None:
        row = (
            await self._connection.execute(
                select(
                    tables.analysis_reports.c.analyzed_at,
                    tables.analysis_reports.c.period_from,
                    tables.analysis_reports.c.period_to,
                    tables.analysis_reports.c.window,
                    tables.analysis_reports.c.risks,
                )
                .where(tables.analysis_reports.c.user_id == user_id)
                .order_by(desc(tables.analysis_reports.c.analyzed_at))
                .limit(1)
            )
        ).one_or_none()

        if row is None:
            return None

        return {
            "analyzed_at": row.analyzed_at,
            "period_from": row.period_from,
            "period_to": row.period_to,
            "window": row.window,
            "risks": row.risks,
        }

    async def get_history(self, user_id: int, *, limit: int = 30, offset: int = 0) -> tuple[list[dict], int]:
        total = (
            await self._connection.execute(
                select(func.count())
                .select_from(tables.analysis_reports)
                .where(tables.analysis_reports.c.user_id == user_id)
            )
        ).scalar_one()

        rows = (
            await self._connection.execute(
                select(
                    tables.analysis_reports.c.analyzed_at,
                    tables.analysis_reports.c.period_from,
                    tables.analysis_reports.c.period_to,
                    tables.analysis_reports.c.window,
                    tables.analysis_reports.c.risks,
                )
                .where(tables.analysis_reports.c.user_id == user_id)
                .order_by(desc(tables.analysis_reports.c.analyzed_at))
                .limit(limit)
                .offset(offset)
            )
        ).all()

        items = [
            {
                "analyzed_at": row.analyzed_at,
                "period_from": row.period_from,
                "period_to": row.period_to,
                "window": row.window,
                "risks": row.risks,
            }
            for row in rows
        ]
        return items, total


class SyncScheduleRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

    async def get_schedule(self, user_id: int) -> dict | None:
        rows = (
            await self._connection.execute(
                select(
                    tables.sync_schedules.c.day_of_week,
                    tables.sync_schedules.c.sync_time,
                    tables.sync_schedules.c.timezone,
                ).where(tables.sync_schedules.c.user_id == user_id)
            )
        ).all()

        if not rows:
            return None

        schedule: dict[str, str] = {}
        timezone = "UTC"
        for row in rows:
            schedule[row.day_of_week] = row.sync_time
            timezone = row.timezone

        return {"schedule": schedule, "timezone": timezone}

    async def upsert_schedule(self, user_id: int, *, schedule: dict[str, str], timezone: str) -> None:
        from sqlalchemy import and_, delete

        await self._connection.execute(
            delete(tables.sync_schedules).where(tables.sync_schedules.c.user_id == user_id)
        )

        rows = [
            {
                "user_id": user_id,
                "day_of_week": day,
                "sync_time": time_str,
                "timezone": timezone,
            }
            for day, time_str in schedule.items()
            if day in self.DAYS
        ]

        if rows:
            await self._connection.execute(
                pg_insert(tables.sync_schedules).values(rows)
            )

    async def get_users_due_now(self, current_time_str: str, current_day: str) -> list[tuple[int, str]]:
        """Return (user_id, apns_device_token) for users scheduled at current_time on current_day."""
        rows = (
            await self._connection.execute(
                select(
                    tables.sync_schedules.c.user_id,
                    tables.users.c.apns_device_token,
                )
                .select_from(
                    tables.sync_schedules.join(
                        tables.users, tables.sync_schedules.c.user_id == tables.users.c.id
                    )
                )
                .where(
                    tables.sync_schedules.c.day_of_week == current_day,
                    tables.sync_schedules.c.sync_time == current_time_str,
                    tables.users.c.is_active.is_(True),
                    tables.users.c.apns_device_token.isnot(None),
                )
            )
        ).all()
        return [(row.user_id, row.apns_device_token) for row in rows]
