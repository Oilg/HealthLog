from pydantic import PositiveInt, field_validator
from pydantic.networks import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="local.env")

    postgres_dsn: PostgresDsn = PostgresDsn("postgresql://admin:root@localhost:5433/postgres")
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

    @field_validator("postgres_dsn", mode="before")
    @classmethod
    def validate_postgres_dsn(cls, value: object) -> object:
        if not value:
            raise ValueError("POSTGRES_DSN is required")
        return value


settings = Settings()
