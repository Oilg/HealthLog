from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncConnection

from health_log.db import engine


async def db_connect() -> AsyncIterator[AsyncConnection]:
    async with engine.begin() as conn:
        yield conn
