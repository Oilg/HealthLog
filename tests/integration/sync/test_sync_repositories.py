"""Integration tests for AnalysisReportsRepository and SyncScheduleRepository.

Requires a running PostgreSQL instance (see conftest.py / TEST_DB_URL).
Tests are skipped automatically when the DB is unavailable.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from health_log.repositories.analysis import AnalysisReportsRepository, SyncScheduleRepository
from tests.integration.conftest import requires_db


# ─── AnalysisReportsRepository ──────────────────────────────────────────────


@requires_db
@pytest.mark.asyncio
async def test_save_and_get_latest_report(db_conn, test_user_id):
    repo = AnalysisReportsRepository(db_conn)

    analyzed_at = datetime(2024, 1, 2, 5, 0, 0)
    period_from = datetime(2024, 1, 1, 22, 0, 0)
    period_to = datetime(2024, 1, 2, 5, 0, 0)
    risks = [
        {"type": "sleep_apnea", "severity": "moderate", "confidence": 0.78, "description": "Test"}
    ]

    report_id = await repo.save_report(
        user_id=test_user_id,
        analyzed_at=analyzed_at,
        period_from=period_from,
        period_to=period_to,
        window="night",
        risks=risks,
    )
    assert isinstance(report_id, int)

    latest = await repo.get_latest_report(test_user_id)
    assert latest is not None
    assert latest["window"] == "night"
    assert latest["risks"] == risks
    assert latest["analyzed_at"] == analyzed_at


@requires_db
@pytest.mark.asyncio
async def test_get_latest_returns_most_recent(db_conn, test_user_id):
    repo = AnalysisReportsRepository(db_conn)

    old_risks = [{"type": "tachycardia_risk", "severity": "low", "confidence": 0.5, "description": "Old"}]
    new_risks = [{"type": "sleep_apnea", "severity": "high", "confidence": 0.9, "description": "New"}]

    await repo.save_report(
        user_id=test_user_id,
        analyzed_at=datetime(2024, 1, 1, 5, 0, 0),
        period_from=datetime(2024, 1, 1, 0, 0, 0),
        period_to=datetime(2024, 1, 1, 5, 0, 0),
        window="night",
        risks=old_risks,
    )
    await repo.save_report(
        user_id=test_user_id,
        analyzed_at=datetime(2024, 1, 2, 5, 0, 0),
        period_from=datetime(2024, 1, 2, 0, 0, 0),
        period_to=datetime(2024, 1, 2, 5, 0, 0),
        window="night",
        risks=new_risks,
    )

    latest = await repo.get_latest_report(test_user_id)
    assert latest["risks"] == new_risks


@requires_db
@pytest.mark.asyncio
async def test_get_latest_returns_none_when_no_reports(db_conn, test_user_id):
    repo = AnalysisReportsRepository(db_conn)
    # Use an unlikely user_id to ensure no reports exist
    result = await repo.get_latest_report(999_999_999)
    assert result is None


@requires_db
@pytest.mark.asyncio
async def test_get_history_pagination(db_conn, test_user_id):
    repo = AnalysisReportsRepository(db_conn)

    for i in range(5):
        await repo.save_report(
            user_id=test_user_id,
            analyzed_at=datetime(2024, 1, i + 1, 5, 0, 0),
            period_from=datetime(2024, 1, i + 1, 0, 0, 0),
            period_to=datetime(2024, 1, i + 1, 5, 0, 0),
            window="night",
            risks=[],
        )

    items, total = await repo.get_history(test_user_id, limit=3, offset=0)
    assert total >= 5
    assert len(items) == 3

    items_page2, _ = await repo.get_history(test_user_id, limit=3, offset=3)
    assert len(items_page2) >= 2

    # Results ordered newest first
    assert items[0]["analyzed_at"] > items[1]["analyzed_at"]


@requires_db
@pytest.mark.asyncio
async def test_get_history_empty(db_conn):
    repo = AnalysisReportsRepository(db_conn)
    items, total = await repo.get_history(999_999_999, limit=10, offset=0)
    assert items == []
    assert total == 0


# ─── SyncScheduleRepository ─────────────────────────────────────────────────


@requires_db
@pytest.mark.asyncio
async def test_upsert_and_get_schedule(db_conn, test_user_id):
    repo = SyncScheduleRepository(db_conn)

    schedule = {
        "monday": "07:30",
        "tuesday": "07:30",
        "wednesday": "07:30",
        "thursday": "07:30",
        "friday": "07:30",
        "saturday": "09:00",
        "sunday": "09:00",
    }
    await repo.upsert_schedule(test_user_id, schedule=schedule, timezone="Europe/Moscow")

    result = await repo.get_schedule(test_user_id)
    assert result is not None
    assert result["timezone"] == "Europe/Moscow"
    assert result["schedule"]["monday"] == "07:30"
    assert result["schedule"]["saturday"] == "09:00"
    assert len(result["schedule"]) == 7


@requires_db
@pytest.mark.asyncio
async def test_upsert_replaces_existing_schedule(db_conn, test_user_id):
    repo = SyncScheduleRepository(db_conn)

    first = {day: "07:00" for day in repo.DAYS}
    await repo.upsert_schedule(test_user_id, schedule=first, timezone="UTC")

    updated = {day: "08:30" for day in repo.DAYS}
    await repo.upsert_schedule(test_user_id, schedule=updated, timezone="Europe/Moscow")

    result = await repo.get_schedule(test_user_id)
    assert result["schedule"]["monday"] == "08:30"
    assert result["timezone"] == "Europe/Moscow"


@requires_db
@pytest.mark.asyncio
async def test_get_schedule_returns_none_when_no_schedule(db_conn):
    repo = SyncScheduleRepository(db_conn)
    result = await repo.get_schedule(999_999_999)
    assert result is None


@requires_db
@pytest.mark.asyncio
async def test_upsert_ignores_unknown_days(db_conn, test_user_id):
    """Days not in DAYS tuple must be silently dropped."""
    repo = SyncScheduleRepository(db_conn)

    schedule = {"monday": "07:00", "funday": "10:00"}
    await repo.upsert_schedule(test_user_id, schedule=schedule, timezone="UTC")

    result = await repo.get_schedule(test_user_id)
    assert "funday" not in result["schedule"]
    assert result["schedule"]["monday"] == "07:00"


@requires_db
@pytest.mark.asyncio
async def test_get_users_due_now_matches_schedule(db_conn, test_user_id):
    """Users with matching day+time are returned; non-matching are not."""
    repo = SyncScheduleRepository(db_conn)

    schedule = {day: "07:30" for day in repo.DAYS}
    await repo.upsert_schedule(test_user_id, schedule=schedule, timezone="UTC")

    # Inject a fake apns_device_token so the query can match
    from sqlalchemy import text
    token = "a" * 64
    await db_conn.execute(
        text("UPDATE users SET apns_device_token = :t WHERE id = :id").bindparams(t=token, id=test_user_id)
    )

    users = await repo.get_users_due_now("07:30", "monday")
    matched_ids = [uid for uid, _ in users]
    assert test_user_id in matched_ids


@requires_db
@pytest.mark.asyncio
async def test_get_users_due_now_no_match(db_conn, test_user_id):
    repo = SyncScheduleRepository(db_conn)
    schedule = {day: "07:30" for day in repo.DAYS}
    await repo.upsert_schedule(test_user_id, schedule=schedule, timezone="UTC")

    users = await repo.get_users_due_now("23:59", "sunday")
    matched_ids = [uid for uid, _ in users]
    assert test_user_id not in matched_ids
