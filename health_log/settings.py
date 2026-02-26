from pydantic import BaseSettings, PositiveInt, validator
from pydantic.networks import PostgresDsn


class Settings(BaseSettings):
    postgres_dsn: PostgresDsn = "postgresql://admin:root@localhost:5433/postgres"
    pg_pool_size: PositiveInt = 10
    pg_log_queries: bool = False
    pg_connection_timeout: PositiveInt = 60

    @validator("postgres_dsn", pre=True)
    def validate_postgres_dsn(cls, value):
        if not value:
            raise ValueError("POSTGRES_DSN is required")
        return value

    class Config:
        env_file = "local.env"
