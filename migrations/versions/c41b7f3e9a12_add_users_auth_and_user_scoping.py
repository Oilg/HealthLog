"""add users auth and user scoping

Revision ID: c41b7f3e9a12
Revises: 1f6e2c7ab412
Create Date: 2026-03-05 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c41b7f3e9a12"
down_revision = "1f6e2c7ab412"
branch_labels = None
depends_on = None

LEGACY_EMAIL = "legacy-user@local"
LEGACY_PHONE = "0000000000"
LEGACY_FIRST_NAME = "Legacy"
LEGACY_LAST_NAME = "User"
LEGACY_PASSWORD_HASH = (
    "pbkdf2_sha256$260000$00112233445566778899aabbccddeeff$"
    "fcc8040322cdb95de35ac62079c5aa57f47292f4b5d1a69ec39a767b7e7ee8f6"
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("phone"),
    )

    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_type", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO users (first_name, last_name, email, phone, password_hash, is_active)
            VALUES (:first_name, :last_name, :email, :phone, :password_hash, true)
            ON CONFLICT (email) DO NOTHING
            """
        ).bindparams(
            first_name=LEGACY_FIRST_NAME,
            last_name=LEGACY_LAST_NAME,
            email=LEGACY_EMAIL,
            phone=LEGACY_PHONE,
            password_hash=LEGACY_PASSWORD_HASH,
        )
    )

    scoped_tables = [
        "xml_uploads",
        "raw_health_records",
        "sleep_analysis",
        "sleep_duration_goal",
        "heart_rate",
        "heart_rate_variability",
        "respiratory_rate",
        "vo_2_max",
        "sleep_apnea_events",
    ]

    for table_name in scoped_tables:
        op.add_column(table_name, sa.Column("user_id", sa.Integer(), nullable=True))
        op.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET user_id = (SELECT id FROM users WHERE email = :email)
                WHERE user_id IS NULL
                """
            ).bindparams(email=LEGACY_EMAIL)
        )
        op.alter_column(table_name, "user_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table_name}_user_id",
            table_name,
            "users",
            ["user_id"],
            ["id"],
        )

    op.drop_constraint("uq_raw_record_fingerprint", "raw_health_records", type_="unique")
    op.create_unique_constraint(
        "uq_raw_record_fingerprint",
        "raw_health_records",
        ["user_id", "provider", "record_fingerprint"],
    )

    op.drop_constraint("uq_sleep_analysis_record", "sleep_analysis", type_="unique")
    op.create_unique_constraint(
        "uq_sleep_analysis_record",
        "sleep_analysis",
        ["user_id", "sourceName", "startDate", "endDate"],
    )

    op.drop_constraint("uq_sleep_duration_goal_record", "sleep_duration_goal", type_="unique")
    op.create_unique_constraint(
        "uq_sleep_duration_goal_record",
        "sleep_duration_goal",
        ["user_id", "sourceName", "startDate", "endDate"],
    )

    op.drop_constraint("uq_heart_rate_record", "heart_rate", type_="unique")
    op.create_unique_constraint(
        "uq_heart_rate_record",
        "heart_rate",
        ["user_id", "sourceName", "startDate", "endDate"],
    )

    op.drop_constraint("uq_hrv_record", "heart_rate_variability", type_="unique")
    op.create_unique_constraint(
        "uq_hrv_record",
        "heart_rate_variability",
        ["user_id", "sourceName", "startDate", "endDate"],
    )

    op.drop_constraint("uq_respiratory_rate_record", "respiratory_rate", type_="unique")
    op.create_unique_constraint(
        "uq_respiratory_rate_record",
        "respiratory_rate",
        ["user_id", "sourceName", "startDate", "endDate"],
    )

    op.drop_constraint("uq_vo2max_record", "vo_2_max", type_="unique")
    op.create_unique_constraint(
        "uq_vo2max_record",
        "vo_2_max",
        ["user_id", "sourceName", "startDate", "endDate"],
    )

    op.drop_constraint("uq_sleep_apnea_event", "sleep_apnea_events", type_="unique")
    op.create_unique_constraint(
        "uq_sleep_apnea_event",
        "sleep_apnea_events",
        ["user_id", "start_time", "end_time", "detected_by"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_sleep_apnea_event", "sleep_apnea_events", type_="unique")
    op.create_unique_constraint(
        "uq_sleep_apnea_event",
        "sleep_apnea_events",
        ["start_time", "end_time", "detected_by"],
    )

    op.drop_constraint("uq_vo2max_record", "vo_2_max", type_="unique")
    op.create_unique_constraint("uq_vo2max_record", "vo_2_max", ["sourceName", "startDate", "endDate"])

    op.drop_constraint("uq_respiratory_rate_record", "respiratory_rate", type_="unique")
    op.create_unique_constraint(
        "uq_respiratory_rate_record",
        "respiratory_rate",
        ["sourceName", "startDate", "endDate"],
    )

    op.drop_constraint("uq_hrv_record", "heart_rate_variability", type_="unique")
    op.create_unique_constraint("uq_hrv_record", "heart_rate_variability", ["sourceName", "startDate", "endDate"])

    op.drop_constraint("uq_heart_rate_record", "heart_rate", type_="unique")
    op.create_unique_constraint("uq_heart_rate_record", "heart_rate", ["sourceName", "startDate", "endDate"])

    op.drop_constraint("uq_sleep_duration_goal_record", "sleep_duration_goal", type_="unique")
    op.create_unique_constraint(
        "uq_sleep_duration_goal_record",
        "sleep_duration_goal",
        ["sourceName", "startDate", "endDate"],
    )

    op.drop_constraint("uq_sleep_analysis_record", "sleep_analysis", type_="unique")
    op.create_unique_constraint(
        "uq_sleep_analysis_record",
        "sleep_analysis",
        ["sourceName", "startDate", "endDate"],
    )

    op.drop_constraint("uq_raw_record_fingerprint", "raw_health_records", type_="unique")
    op.create_unique_constraint(
        "uq_raw_record_fingerprint",
        "raw_health_records",
        ["provider", "record_fingerprint"],
    )

    scoped_tables = [
        "sleep_apnea_events",
        "vo_2_max",
        "respiratory_rate",
        "heart_rate_variability",
        "heart_rate",
        "sleep_duration_goal",
        "sleep_analysis",
        "raw_health_records",
        "xml_uploads",
    ]

    for table_name in scoped_tables:
        op.drop_constraint(f"fk_{table_name}_user_id", table_name, type_="foreignkey")
        op.drop_column(table_name, "user_id")

    op.drop_table("auth_tokens")
    op.drop_table("users")
