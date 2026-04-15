from typing import cast

from pydantic import BaseSettings, PositiveInt, validator
from pydantic.networks import PostgresDsn


class Settings(BaseSettings):
    postgres_dsn: PostgresDsn = cast(PostgresDsn, "postgresql://admin:root@localhost:5433/postgres")
    pg_pool_size: PositiveInt = 10
    pg_log_queries: bool = False
    pg_connection_timeout: PositiveInt = 60
    auth_access_ttl_minutes: PositiveInt = 30
    auth_refresh_ttl_days: PositiveInt = 14

    # APNs configuration (optional — pushes are skipped if not set)
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_auth_key_path: str = ""
    apns_bundle_id: str = ""
    apns_use_sandbox: bool = True

    @validator("postgres_dsn", pre=True)
    def validate_postgres_dsn(cls, value):
        if not value:
            raise ValueError("POSTGRES_DSN is required")
        return value

    class Config:
        env_file = "local.env"
