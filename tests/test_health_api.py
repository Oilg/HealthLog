"""Unit tests for GET /api/v1/health/sync/status endpoint.

Tests are structured to avoid importing DB-dependent modules at module level
so they can be collected even without asyncpg installed locally.
"""

from datetime import datetime

import pytest

# ─── Fakes ────────────────────────────────────────────────────────────────────


def _make_user():
    from health_log.repositories.auth import AuthUser

    return AuthUser(
        id=1,
        first_name="Test",
        last_name="User",
        sex="male",
        email="test@example.com",
        phone="+79001234567",
        password_hash="hash",
        is_active=True,
    )


class FakeUsersRepository:
    def __init__(self, result: dict | None):
        self._result = result

    async def get_health_sync_status(self, user_id: int) -> dict | None:
        return self._result


class FakeConn:
    pass


async def _call(repo_result: dict | None):
    from unittest.mock import patch

    from health_log.api.v1.health import get_health_sync_status

    with patch(
        "health_log.api.v1.health.UsersRepository",
        return_value=FakeUsersRepository(repo_result),
    ):
        return await get_health_sync_status(
            current_user=_make_user(),
            conn=FakeConn(),  # type: ignore[arg-type]
        )


# ─── has_data = True (user has synced before) ────────────────────────────────


@pytest.mark.asyncio
async def test_has_data_true_when_last_sync_at_set():
    last_sync = datetime(2026, 5, 20, 10, 0, 0)
    result = await _call({"has_data": True, "last_sync_at": last_sync})
    assert result.has_data is True


@pytest.mark.asyncio
async def test_last_sync_at_is_iso_string_with_z_suffix():
    last_sync = datetime(2026, 5, 20, 10, 0, 0)
    result = await _call({"has_data": True, "last_sync_at": last_sync})
    assert result.last_sync_at == "2026-05-20T10:00:00Z"


@pytest.mark.asyncio
async def test_last_sync_at_preserves_time_components():
    last_sync = datetime(2025, 12, 31, 23, 59, 59)
    result = await _call({"has_data": True, "last_sync_at": last_sync})
    assert result.last_sync_at == "2025-12-31T23:59:59Z"


# ─── has_data = False (user never synced) ────────────────────────────────────


@pytest.mark.asyncio
async def test_has_data_false_when_last_sync_at_is_none():
    result = await _call({"has_data": False, "last_sync_at": None})
    assert result.has_data is False


@pytest.mark.asyncio
async def test_last_sync_at_is_none_when_never_synced():
    result = await _call({"has_data": False, "last_sync_at": None})
    assert result.last_sync_at is None


# ─── 404 when user not found ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_raises_404_when_user_not_found():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await _call(None)
    assert exc_info.value.status_code == 404


# ─── Response model fields ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_has_has_data_field():
    result = await _call({"has_data": True, "last_sync_at": datetime(2026, 1, 1)})
    assert hasattr(result, "has_data")


@pytest.mark.asyncio
async def test_response_has_last_sync_at_field():
    result = await _call({"has_data": True, "last_sync_at": datetime(2026, 1, 1)})
    assert hasattr(result, "last_sync_at")
