from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from health_log.settings import Settings

settings = Settings()
database_url = str(settings.postgres_dsn)
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

DATABASE_URL = database_url

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=settings.pg_log_queries,
    pool_size=settings.pg_pool_size,
    pool_timeout=settings.pg_connection_timeout,
)
