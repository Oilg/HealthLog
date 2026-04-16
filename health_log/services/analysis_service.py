"""Background analysis service: run health risk analysis after data sync."""
from __future__ import annotations

import logging

from health_log.analysis.engine import HealthRiskAnalyzer
from health_log.db import engine

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
        logger.info("Background analysis completed for user_id=%d", user_id)
    except Exception:
        logger.exception("Background analysis failed for user_id=%d", user_id)
