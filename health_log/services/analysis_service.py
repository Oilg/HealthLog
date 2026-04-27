"""Background analysis service: run health risk analysis after data sync."""
from __future__ import annotations

import logging

from sqlalchemy import select

from health_log.analysis.engine import HealthRiskAnalyzer
from health_log.db import engine
from health_log.repositories.v1 import tables

logger = logging.getLogger(__name__)


async def analyze_for_user(user_id: int) -> None:
    """Run full health risk analysis for a user.

    Intended to be called as a FastAPI BackgroundTask after a successful sync
    so that fresh analysis results are available without a separate API call.
    Opens its own DB connection so the sync transaction is already committed.
    """
    try:
        async with engine.begin() as conn:
            analyzer = HealthRiskAnalyzer(conn, user_id)
            await analyzer.analyze_all_windows()

            # Fetch device token to send push notification
            row = (
                await conn.execute(
                    select(tables.users.c.apns_device_token).where(tables.users.c.id == user_id)
                )
            ).one_or_none()
            device_token = row.apns_device_token if row else None

        logger.info("Background analysis completed for user_id=%d", user_id)

        if device_token:
            from health_log.services.apns import send_analysis_ready_push
            await send_analysis_ready_push(device_token)

    except Exception:
        logger.exception("Background analysis failed for user_id=%d", user_id)
