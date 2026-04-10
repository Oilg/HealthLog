from __future__ import annotations

import asyncio
import os

import pytest
import pytest_asyncio

TEST_DB_URL = os.getenv(
    "TEST_DB_URL",
    "postgresql+asyncpg://admin:root@localhost:5434/postgres",
)

_DB_AVAILABLE: bool | None = None


def _check_db_available() -> bool:
    global _DB_AVAILABLE
    if _DB_AVAILABLE is not None:
        return _DB_AVAILABLE

    async def _probe():
        try:
            from sqlalchemy.ext.asyncio import create_async_engine
            engine = create_async_engine(TEST_DB_URL, connect_args={"timeout": 3})
            async with engine.connect() as conn:
                await conn.execute(
                    __import__("sqlalchemy").text("SELECT 1")
                )
            await engine.dispose()
            return True
        except Exception:
            return False

    _DB_AVAILABLE = asyncio.get_event_loop().run_until_complete(_probe())
    return _DB_AVAILABLE


requires_db = pytest.mark.skipif(
    not _check_db_available(),
    reason="Test database not available (set TEST_DB_URL or start docker-compose.test.yml)",
)


@pytest_asyncio.fixture
async def db_conn():
    from sqlalchemy.ext.asyncio import create_async_engine

    from health_log.repositories.v1.tables import metadata

    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    async with engine.connect() as conn:
        yield conn
        await conn.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def test_user_id(db_conn):
    from sqlalchemy import text
    result = await db_conn.execute(
        text(
            "INSERT INTO users (first_name, last_name, sex, email, phone, password_hash, updated_at) "
            "VALUES ('Test', 'User', 'male', :email, :phone, 'hash', now()) "
            "ON CONFLICT (email) DO UPDATE SET first_name='Test' "
            "RETURNING id"
        ).bindparams(email="test_integration@test.local", phone="+70000000001")
    )
    uid = result.scalar_one()
    return uid


@pytest_asyncio.fixture
async def test_female_user_id(db_conn):
    from sqlalchemy import text
    result = await db_conn.execute(
        text(
            "INSERT INTO users (first_name, last_name, sex, email, phone, password_hash, updated_at) "
            "VALUES ('Test', 'Female', 'female', :email, :phone, 'hash', now()) "
            "ON CONFLICT (email) DO UPDATE SET first_name='Test' "
            "RETURNING id"
        ).bindparams(email="test_female_integration@test.local", phone="+70000000002")
    )
    uid = result.scalar_one()
    return uid
