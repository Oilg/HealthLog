"""add new health metric tables

Revision ID: e3a91c2d7f40
Revises: f7a12d0e4b21
Create Date: 2026-04-10 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "e3a91c2d7f40"
down_revision = "f7a12d0e4b21"
branch_labels = None
depends_on = None

_QUANTITY_TABLES = [
    ("oxygen_saturation", "uq_oxygen_saturation_record"),
    ("blood_pressure_systolic", "uq_blood_pressure_systolic_record"),
    ("blood_pressure_diastolic", "uq_blood_pressure_diastolic_record"),
    ("apple_sleeping_wrist_temperature", "uq_apple_sleeping_wrist_temperature_record"),
    ("walking_heart_rate_average", "uq_walking_heart_rate_average_record"),
    ("walking_speed", "uq_walking_speed_record"),
    ("walking_step_length", "uq_walking_step_length_record"),
    ("walking_double_support_percentage", "uq_walking_double_support_percentage_record"),
    ("walking_steadiness", "uq_walking_steadiness_record"),
    ("environmental_audio_exposure", "uq_environmental_audio_exposure_record"),
    ("headphone_audio_exposure", "uq_headphone_audio_exposure_record"),
    ("body_mass", "uq_body_mass_record"),
    ("body_mass_index", "uq_body_mass_index_record"),
    ("body_fat_percentage", "uq_body_fat_percentage_record"),
    ("lean_body_mass", "uq_lean_body_mass_record"),
    ("waist_circumference", "uq_waist_circumference_record"),
    ("step_count", "uq_step_count_record"),
    ("apple_exercise_time", "uq_apple_exercise_time_record"),
    ("apple_afib_burden", "uq_apple_afib_burden_record"),
]

_CATEGORY_TABLES = [
    ("low_heart_rate_event", "uq_low_heart_rate_event_record"),
    ("irregular_heart_rhythm_event", "uq_irregular_heart_rhythm_event_record"),
    ("intermenstrual_bleeding", "uq_intermenstrual_bleeding_record"),
]


def upgrade() -> None:
    for table_name, uq_name in _QUANTITY_TABLES:
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("sourceName", sa.String(), nullable=False),
            sa.Column("unit", sa.String(), nullable=True),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column("creationDate", sa.DateTime(), nullable=False),
            sa.Column("startDate", sa.DateTime(), nullable=False),
            sa.Column("endDate", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "sourceName", "startDate", "endDate", name=uq_name),
        )

    for table_name, uq_name in _CATEGORY_TABLES:
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("sourceName", sa.String(), nullable=False),
            sa.Column("value", sa.String(), nullable=True),
            sa.Column("creationDate", sa.DateTime(), nullable=False),
            sa.Column("startDate", sa.DateTime(), nullable=False),
            sa.Column("endDate", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "sourceName", "startDate", "endDate", name=uq_name),
        )


def downgrade() -> None:
    for table_name, _ in reversed(_CATEGORY_TABLES):
        op.drop_table(table_name)
    for table_name, _ in reversed(_QUANTITY_TABLES):
        op.drop_table(table_name)
