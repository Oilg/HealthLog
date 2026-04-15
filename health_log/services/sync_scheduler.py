"""Cron-style scheduler: every minute checks sync_schedules and sends APNs silent pushes.

Integration pattern:
    from health_log.services.sync_scheduler import run_sync_scheduler
    asyncio.create_task(run_sync_scheduler())
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from health_log.db import engine
from health_log.repositories.analysis import SyncScheduleRepository
from health_log.services.apns import send_silent_push

logger = logging.getLogger(__name__)

WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


async def _check_and_send_pushes() -> None:
    """Fire silent APNs pushes for all users whose schedule matches the current local time."""
    utc_now = datetime.now(timezone.utc)

    async with engine.begin() as conn:
        repo = SyncScheduleRepository(conn)

        # Fetch all distinct timezones in use to avoid per-user tz conversions
        from sqlalchemy import distinct, select

        from health_log.repositories.v1 import tables

        tz_rows = (
            await conn.execute(select(distinct(tables.sync_schedules.c.timezone)))
        ).fetchall()

        for (tz_name,) in tz_rows:
            try:
                tz = ZoneInfo(tz_name)
            except ZoneInfoNotFoundError:
                logger.warning("Неизвестный часовой пояс в sync_schedules: %s", tz_name)
                continue

            local_now = utc_now.astimezone(tz)
            current_time_str = local_now.strftime("%H:%M")
            current_day = WEEKDAY_NAMES[local_now.weekday()]

            users = await repo.get_users_due_now(current_time_str, current_day)
            for user_id, device_token in users:
                if device_token:
                    ok = await send_silent_push(device_token)
                    if ok:
                        logger.info("Push отправлен пользователю user_id=%d (%s %s)", user_id, current_day, current_time_str)


async def run_sync_scheduler() -> None:
    """Infinite loop: tick every 60 seconds, check schedules, send pushes."""
    logger.info("Планировщик синхронизации запущен")
    while True:
        try:
            await _check_and_send_pushes()
        except Exception:
            logger.exception("Ошибка в планировщике синхронизации")
        await asyncio.sleep(60)
