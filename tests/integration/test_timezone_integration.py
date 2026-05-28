"""Интеграционные тесты для timezone: репозиторий пользователя и fetch в engine."""

from __future__ import annotations

import pytest

from health_log.analysis.engine import HealthRiskAnalyzer
from health_log.repositories.auth import UsersRepository
from tests.integration.conftest import requires_db

pytestmark = [pytest.mark.asyncio, requires_db]


@pytest.fixture
def unique_email():
    import uuid

    return f"tz_test_{uuid.uuid4().hex[:8]}@test.local"


@pytest.fixture
def unique_phone():
    import uuid

    return f"+7{uuid.uuid4().int % 10**10:010d}"


async def test_create_user_without_timezone_uses_server_default(
    db_conn, unique_email, unique_phone
) -> None:
    repo = UsersRepository(db_conn)
    user = await repo.create_user(
        first_name="Test",
        last_name="DefaultTZ",
        sex="male",
        email=unique_email,
        phone=unique_phone,
        password_hash="hash",
    )
    # Server default = "UTC", colonка NOT NULL.
    assert user.timezone == "UTC"


async def test_create_user_with_timezone_persists_value(
    db_conn, unique_email, unique_phone
) -> None:
    repo = UsersRepository(db_conn)
    user = await repo.create_user(
        first_name="Test",
        last_name="MoscowTZ",
        sex="male",
        email=unique_email,
        phone=unique_phone,
        password_hash="hash",
        timezone="Europe/Moscow",
    )
    assert user.timezone == "Europe/Moscow"

    fetched = await repo.get_public_user(user.id)
    assert fetched is not None
    assert fetched.timezone == "Europe/Moscow"


async def test_update_me_sets_timezone(db_conn, unique_email, unique_phone) -> None:
    repo = UsersRepository(db_conn)
    user = await repo.create_user(
        first_name="Test",
        last_name="Update",
        sex="female",
        email=unique_email,
        phone=unique_phone,
        password_hash="hash",
    )
    assert user.timezone == "UTC"

    updated = await repo.update_me(
        user.id,
        timezone="Asia/Tokyo",
        update_timezone=True,
    )
    assert updated.timezone == "Asia/Tokyo"


async def test_update_me_preserves_timezone_without_flag(
    db_conn, unique_email, unique_phone
) -> None:
    repo = UsersRepository(db_conn)
    user = await repo.create_user(
        first_name="Test",
        last_name="Keep",
        sex="male",
        email=unique_email,
        phone=unique_phone,
        password_hash="hash",
        timezone="America/New_York",
    )

    # Обновление имени без флага update_timezone — таймзона сохраняется.
    updated = await repo.update_me(user.id, first_name="Changed")
    assert updated.timezone == "America/New_York"
    assert updated.first_name == "Changed"


async def test_engine_fetches_user_timezone(db_conn, unique_email, unique_phone) -> None:
    repo = UsersRepository(db_conn)
    user = await repo.create_user(
        first_name="TZ",
        last_name="Test",
        sex="male",
        email=unique_email,
        phone=unique_phone,
        password_hash="hash",
        timezone="Europe/Moscow",
    )

    analyzer = HealthRiskAnalyzer(db_conn, user.id)
    tz = await analyzer._fetch_user_timezone()
    assert tz == "Europe/Moscow"

    # Повторный вызов использует кэш.
    tz_again = await analyzer._fetch_user_timezone()
    assert tz_again == "Europe/Moscow"


async def test_engine_fetch_timezone_returns_none_for_utc(
    db_conn, unique_email, unique_phone
) -> None:
    """UTC в БД должен трактоваться как None для engine (fallback на UTC-полночь)."""
    repo = UsersRepository(db_conn)
    user = await repo.create_user(
        first_name="UTC",
        last_name="User",
        sex="female",
        email=unique_email,
        phone=unique_phone,
        password_hash="hash",
    )
    assert user.timezone == "UTC"

    analyzer = HealthRiskAnalyzer(db_conn, user.id)
    tz = await analyzer._fetch_user_timezone()
    assert tz is None
