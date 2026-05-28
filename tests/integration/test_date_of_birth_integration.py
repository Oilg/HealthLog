"""Интеграционные тесты для DOB: репозиторий пользователя и вычисление возраста в engine."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from health_log.analysis.engine import HealthRiskAnalyzer
from health_log.repositories.auth import UsersRepository
from tests.integration.conftest import requires_db

pytestmark = [pytest.mark.asyncio, requires_db]


@pytest.fixture
def unique_email():
    import uuid

    return f"dob_test_{uuid.uuid4().hex[:8]}@test.local"


@pytest.fixture
def unique_phone():
    import uuid

    return f"+7{uuid.uuid4().int % 10**10:010d}"


async def test_create_user_with_dob_persists_value(db_conn, unique_email, unique_phone) -> None:
    repo = UsersRepository(db_conn)
    dob = date(1980, 5, 15)
    user = await repo.create_user(
        first_name="Test",
        last_name="DOB",
        sex="male",
        email=unique_email,
        phone=unique_phone,
        password_hash="hash",
        date_of_birth=dob,
    )
    assert user.date_of_birth == dob

    fetched = await repo.get_public_user(user.id)
    assert fetched is not None
    assert fetched.date_of_birth == dob


async def test_create_user_without_dob_stores_null(db_conn, unique_email, unique_phone) -> None:
    repo = UsersRepository(db_conn)
    user = await repo.create_user(
        first_name="Test",
        last_name="NoDOB",
        sex="male",
        email=unique_email,
        phone=unique_phone,
        password_hash="hash",
    )
    assert user.date_of_birth is None


async def test_update_me_sets_dob(db_conn, unique_email, unique_phone) -> None:
    repo = UsersRepository(db_conn)
    user = await repo.create_user(
        first_name="Test",
        last_name="Update",
        sex="male",
        email=unique_email,
        phone=unique_phone,
        password_hash="hash",
    )
    assert user.date_of_birth is None

    dob = date(1995, 8, 20)
    updated = await repo.update_me(
        user.id,
        date_of_birth=dob,
        update_date_of_birth=True,
    )
    assert updated.date_of_birth == dob


async def test_update_me_does_not_clear_dob_without_flag(
    db_conn, unique_email, unique_phone
) -> None:
    repo = UsersRepository(db_conn)
    dob = date(1990, 1, 1)
    user = await repo.create_user(
        first_name="Test",
        last_name="Keep",
        sex="male",
        email=unique_email,
        phone=unique_phone,
        password_hash="hash",
        date_of_birth=dob,
    )

    # Обновление имени без явного update_date_of_birth — DOB сохраняется
    updated = await repo.update_me(user.id, first_name="Changed")
    assert updated.date_of_birth == dob
    assert updated.first_name == "Changed"


async def test_db_rejects_dob_for_too_young(db_conn, unique_email, unique_phone) -> None:
    # CHECK на стороне БД должен отвергать DOB младше 5 лет
    too_young = date.today() - timedelta(days=3 * 365)
    with pytest.raises(Exception):  # noqa: B017 — может быть CheckViolationError или IntegrityError
        await db_conn.execute(
            text(
                "INSERT INTO users (first_name, last_name, sex, email, phone, password_hash, "
                "updated_at, date_of_birth) "
                "VALUES (:fn, :ln, 'male', :email, :phone, 'hash', now(), :dob)"
            ).bindparams(
                fn="Too",
                ln="Young",
                email=unique_email,
                phone=unique_phone,
                dob=too_young,
            )
        )


async def test_db_rejects_dob_for_too_old(db_conn, unique_email, unique_phone) -> None:
    too_old = date.today() - timedelta(days=140 * 366)
    with pytest.raises(Exception):  # noqa: B017
        await db_conn.execute(
            text(
                "INSERT INTO users (first_name, last_name, sex, email, phone, password_hash, "
                "updated_at, date_of_birth) "
                "VALUES (:fn, :ln, 'male', :email, :phone, 'hash', now(), :dob)"
            ).bindparams(
                fn="Too",
                ln="Old",
                email=unique_email,
                phone=unique_phone,
                dob=too_old,
            )
        )


async def test_engine_fetches_user_dob_and_age(db_conn, unique_email, unique_phone) -> None:
    repo = UsersRepository(db_conn)
    dob = date(1955, 3, 10)  # возраст ~71 → SENIOR
    user = await repo.create_user(
        first_name="Senior",
        last_name="Test",
        sex="male",
        email=unique_email,
        phone=unique_phone,
        password_hash="hash",
        date_of_birth=dob,
    )

    analyzer = HealthRiskAnalyzer(db_conn, user.id)
    fetched_dob = await analyzer._fetch_user_dob()
    assert fetched_dob == dob

    # Кэш: повторный вызов не должен ходить в БД (но если ходит — тоже корректно)
    fetched_dob_again = await analyzer._fetch_user_dob()
    assert fetched_dob_again == dob

    age = HealthRiskAnalyzer._compute_age(fetched_dob, datetime(2026, 5, 27, 12, 0))
    assert age == 71


async def test_engine_returns_none_dob_for_user_without_dob(
    db_conn, unique_email, unique_phone
) -> None:
    repo = UsersRepository(db_conn)
    user = await repo.create_user(
        first_name="NoDOB",
        last_name="User",
        sex="female",
        email=unique_email,
        phone=unique_phone,
        password_hash="hash",
    )

    analyzer = HealthRiskAnalyzer(db_conn, user.id)
    assert await analyzer._fetch_user_dob() is None


async def test_restore_user_preserves_dob_when_not_provided(
    db_conn, unique_email, unique_phone
) -> None:
    """Замечание 1: restore_user не должна затирать DOB при date_of_birth=None."""
    repo = UsersRepository(db_conn)
    dob = date(1985, 7, 10)

    # Создаём пользователя с DOB
    user = await repo.create_user(
        first_name="Restore",
        last_name="Test",
        sex="male",
        email=unique_email,
        phone=unique_phone,
        password_hash="oldhash",
        date_of_birth=dob,
    )
    assert user.date_of_birth == dob

    # Деактивируем вручную
    from sqlalchemy import update as sa_update

    from health_log.repositories.v1 import tables

    await db_conn.execute(
        sa_update(tables.users).where(tables.users.c.id == user.id).values(is_active=False)
    )

    # restore_user без date_of_birth → DOB должен сохраниться
    restored = await repo.restore_user(
        user.id,
        first_name="Restore",
        last_name="Test",
        sex="male",
        email=unique_email,
        phone=unique_phone,
        password_hash="newhash",
    )
    assert restored.date_of_birth == dob
