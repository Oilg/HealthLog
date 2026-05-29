"""Интеграционные тесты планировщика silent-пушей.

Регрессионные тесты к багу, при котором планировщик использовал хардкоженый
"UTC" как fallback таймзоны для пользователей без записей в `sync_schedules`,
игнорируя поле `users.timezone`. В результате пользователь с timezone="Europe/Moscow"
получал ежедневный push в 10:00 UTC (13:00 МСК) вместо 07:00 UTC (10:00 МСК).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from health_log.repositories.v1 import tables
from health_log.services import sync_scheduler
from tests.integration.conftest import requires_db

pytestmark = [pytest.mark.asyncio, requires_db]


@pytest.fixture
def unique_creds():
    import uuid

    suffix = uuid.uuid4().hex[:10]
    return {
        "email": f"sched_{suffix}@test.local",
        "phone": f"+7{uuid.uuid4().int % 10**10:010d}",
    }


async def _insert_user(
    db_conn,
    *,
    email: str,
    phone: str,
    tz: str,
    apns_token: str = "stub-device-token",
    is_active: bool = True,
) -> int:
    """Создать пользователя с конкретными timezone/токеном и вернуть id."""
    result = await db_conn.execute(
        tables.users.insert()
        .values(
            first_name="Sched",
            last_name="Test",
            sex="male",
            email=email,
            phone=phone,
            password_hash="hash",
            timezone=tz,
            apns_device_token=apns_token,
            is_active=is_active,
        )
        .returning(tables.users.c.id)
    )
    return result.scalar_one()


class _StubEngine:
    """Минимальная заглушка `engine` для `_send_daily_10am_pushes`.

    Планировщик использует `async with engine.begin() as conn`. Мы переиспользуем
    одно подключение из фикстуры `db_conn`, чтобы видеть данные созданные в тесте
    (внутри той же транзакции).
    """

    def __init__(self, conn):
        self._conn = conn

    def begin(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return _Ctx()


async def test_daily_push_uses_user_timezone_when_no_sync_schedule(
    db_conn, unique_creds
) -> None:
    """Регрессия: при отсутствии sync_schedule используется users.timezone, а не UTC.

    Пользователь с tz=Europe/Moscow должен получить push в 07:00 UTC
    (10:00 локального), а не в 10:00 UTC (13:00 локального).
    """
    await _insert_user(db_conn, tz="Europe/Moscow", **unique_creds)

    # 07:00 UTC = 10:00 МСК → push должен уйти.
    fake_now = datetime(2026, 5, 29, 7, 0, tzinfo=timezone.utc)
    send_mock = AsyncMock(return_value=True)

    with (
        patch.object(sync_scheduler, "engine", _StubEngine(db_conn)),
        patch.object(sync_scheduler, "send_silent_push", send_mock),
        patch("health_log.services.sync_scheduler.datetime") as dt_mock,
    ):
        dt_mock.now.return_value = fake_now
        # Сохраняем доступ к настоящим конструкторам datetime.
        dt_mock.side_effect = lambda *a, **kw: datetime(*a, **kw)

        await sync_scheduler._send_daily_10am_pushes()

    assert send_mock.await_count == 1
    send_mock.assert_awaited_with("stub-device-token")


async def test_daily_push_not_sent_at_10am_utc_for_moscow_user(
    db_conn, unique_creds
) -> None:
    """В 10:00 UTC московский пользователь (13:00 локального) НЕ должен получить push."""
    await _insert_user(db_conn, tz="Europe/Moscow", **unique_creds)

    fake_now = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)
    send_mock = AsyncMock(return_value=True)

    with (
        patch.object(sync_scheduler, "engine", _StubEngine(db_conn)),
        patch.object(sync_scheduler, "send_silent_push", send_mock),
        patch("health_log.services.sync_scheduler.datetime") as dt_mock,
    ):
        dt_mock.now.return_value = fake_now
        dt_mock.side_effect = lambda *a, **kw: datetime(*a, **kw)

        await sync_scheduler._send_daily_10am_pushes()

    send_mock.assert_not_awaited()


async def test_daily_push_utc_user_at_10am_utc(db_conn, unique_creds) -> None:
    """Пользователь с tz=UTC получает push в 10:00 UTC."""
    await _insert_user(db_conn, tz="UTC", **unique_creds)

    fake_now = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)
    send_mock = AsyncMock(return_value=True)

    with (
        patch.object(sync_scheduler, "engine", _StubEngine(db_conn)),
        patch.object(sync_scheduler, "send_silent_push", send_mock),
        patch("health_log.services.sync_scheduler.datetime") as dt_mock,
    ):
        dt_mock.now.return_value = fake_now
        dt_mock.side_effect = lambda *a, **kw: datetime(*a, **kw)

        await sync_scheduler._send_daily_10am_pushes()

    assert send_mock.await_count == 1


async def test_sync_schedule_timezone_overrides_user_timezone(
    db_conn, unique_creds
) -> None:
    """Приоритет: sync_schedules.timezone выше, чем users.timezone."""
    uid = await _insert_user(db_conn, tz="Europe/Moscow", **unique_creds)

    # Записываем sync_schedule с другой таймзоной — он должен победить.
    await db_conn.execute(
        tables.sync_schedules.insert().values(
            user_id=uid,
            day_of_week="monday",
            sync_time="08:00",
            timezone="Asia/Tokyo",
        )
    )

    # 01:00 UTC = 10:00 Asia/Tokyo → push должен уйти.
    fake_now = datetime(2026, 5, 29, 1, 0, tzinfo=timezone.utc)
    send_mock = AsyncMock(return_value=True)

    with (
        patch.object(sync_scheduler, "engine", _StubEngine(db_conn)),
        patch.object(sync_scheduler, "send_silent_push", send_mock),
        patch("health_log.services.sync_scheduler.datetime") as dt_mock,
    ):
        dt_mock.now.return_value = fake_now
        dt_mock.side_effect = lambda *a, **kw: datetime(*a, **kw)

        await sync_scheduler._send_daily_10am_pushes()

    assert send_mock.await_count == 1


async def test_inactive_user_does_not_receive_push(db_conn, unique_creds) -> None:
    """Неактивные пользователи не должны получать push даже в правильное время."""
    await _insert_user(
        db_conn, tz="Europe/Moscow", is_active=False, **unique_creds
    )

    fake_now = datetime(2026, 5, 29, 7, 0, tzinfo=timezone.utc)
    send_mock = AsyncMock(return_value=True)

    with (
        patch.object(sync_scheduler, "engine", _StubEngine(db_conn)),
        patch.object(sync_scheduler, "send_silent_push", send_mock),
        patch("health_log.services.sync_scheduler.datetime") as dt_mock,
    ):
        dt_mock.now.return_value = fake_now
        dt_mock.side_effect = lambda *a, **kw: datetime(*a, **kw)

        await sync_scheduler._send_daily_10am_pushes()

    send_mock.assert_not_awaited()
