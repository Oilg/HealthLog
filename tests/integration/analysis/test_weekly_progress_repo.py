"""Integration tests for AnalysisReportsRepository.get_latest_weekly_pair."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from health_log.analysis.weekly_progress import compute_weekly_progress
from health_log.repositories.analysis import AnalysisReportsRepository
from tests.integration.conftest import requires_db

pytestmark = [pytest.mark.asyncio, requires_db]


async def _save(
    repo: AnalysisReportsRepository,
    *,
    user_id: int,
    analyzed_at: datetime,
    period_from: datetime,
    period_to: datetime,
    window: str,
    risks: list[dict],
) -> None:
    await repo.save_report(
        user_id=user_id,
        analyzed_at=analyzed_at,
        period_from=period_from,
        period_to=period_to,
        window=window,
        risks=risks,
    )


async def test_returns_none_none_when_no_reports(db_conn, test_user_id):
    repo = AnalysisReportsRepository(db_conn)
    current, previous = await repo.get_latest_weekly_pair(test_user_id)
    assert current is None
    assert previous is None


async def test_returns_one_report_when_only_one_week_exists(db_conn, test_user_id):
    repo = AnalysisReportsRepository(db_conn)
    base = datetime(2026, 3, 15, 12, 0, 0)
    await _save(
        repo,
        user_id=test_user_id,
        analyzed_at=base,
        period_from=base - timedelta(days=7),
        period_to=base,
        window="week",
        risks=[{"condition": "tachycardia_risk", "severity": "low", "confidence": 0.5}],
    )
    current, previous = await repo.get_latest_weekly_pair(test_user_id)
    assert current is not None
    assert previous is None
    assert current["window"] == "week"


async def test_returns_two_latest_week_reports(db_conn, test_user_id):
    repo = AnalysisReportsRepository(db_conn)
    base = datetime(2026, 3, 15, 12, 0, 0)
    # Older
    await _save(
        repo,
        user_id=test_user_id,
        analyzed_at=base - timedelta(days=7),
        period_from=base - timedelta(days=14),
        period_to=base - timedelta(days=7),
        window="week",
        risks=[{"condition": "tachycardia_risk", "severity": "moderate", "confidence": 0.6}],
    )
    # Newest
    await _save(
        repo,
        user_id=test_user_id,
        analyzed_at=base,
        period_from=base - timedelta(days=7),
        period_to=base,
        window="week",
        risks=[{"condition": "tachycardia_risk", "severity": "low", "confidence": 0.4}],
    )
    current, previous = await repo.get_latest_weekly_pair(test_user_id)
    assert current is not None and previous is not None
    assert current["analyzed_at"] > previous["analyzed_at"]
    assert current["risks"][0]["severity"] == "low"
    assert previous["risks"][0]["severity"] == "moderate"


async def test_ignores_non_week_windows(db_conn, test_user_id):
    repo = AnalysisReportsRepository(db_conn)
    base = datetime(2026, 3, 15, 12, 0, 0)
    await _save(
        repo,
        user_id=test_user_id,
        analyzed_at=base - timedelta(hours=1),
        period_from=base - timedelta(hours=12),
        period_to=base,
        window="night",
        risks=[],
    )
    await _save(
        repo,
        user_id=test_user_id,
        analyzed_at=base - timedelta(hours=2),
        period_from=base - timedelta(days=30),
        period_to=base,
        window="month",
        risks=[],
    )
    await _save(
        repo,
        user_id=test_user_id,
        analyzed_at=base,
        period_from=base - timedelta(days=7),
        period_to=base,
        window="week",
        risks=[{"condition": "sleep_apnea_risk", "severity": "low", "confidence": 0.3}],
    )
    current, previous = await repo.get_latest_weekly_pair(test_user_id)
    assert current is not None
    assert previous is None
    assert current["window"] == "week"


async def test_end_to_end_compute_progress_from_db(db_conn, test_user_id):
    repo = AnalysisReportsRepository(db_conn)
    base = datetime(2026, 3, 15, 12, 0, 0)
    await _save(
        repo,
        user_id=test_user_id,
        analyzed_at=base - timedelta(days=7),
        period_from=base - timedelta(days=14),
        period_to=base - timedelta(days=7),
        window="week",
        risks=[
            {"condition": "obesity_risk", "severity": "high", "confidence": 0.8},
            {"condition": "fall_risk", "severity": "moderate", "confidence": 0.6},
        ],
    )
    await _save(
        repo,
        user_id=test_user_id,
        analyzed_at=base,
        period_from=base - timedelta(days=7),
        period_to=base,
        window="week",
        risks=[
            # obesity disappeared -> improved
            {"condition": "fall_risk", "severity": "moderate", "confidence": 0.6},  # unchanged
            {
                "condition": "tachycardia_risk",
                "severity": "low",
                "confidence": 0.5,
            },  # new -> worsened
        ],
    )
    current, previous = await repo.get_latest_weekly_pair(test_user_id)
    progress = compute_weekly_progress(current, previous)
    assert progress["has_previous"] is True
    by_cond = {it["condition"]: it for it in progress["items"]}
    assert by_cond["obesity_risk"]["direction"] == "improved"
    assert by_cond["fall_risk"]["direction"] == "unchanged"
    assert by_cond["tachycardia_risk"]["direction"] == "worsened"

    # Verify ordering: worsened -> improved -> unchanged
    directions = [it["direction"] for it in progress["items"]]
    assert directions == ["worsened", "improved", "unchanged"]
