"""add resting_heart_rate table

Revision ID: b3c4d5e6f7a8
Revises: b7c8e9f0a1d2
Create Date: 2026-06-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "b7c8e9f0a1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resting_heart_rate",
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
        sa.UniqueConstraint(
            "user_id", "sourceName", "startDate", "endDate", name="uq_resting_heart_rate_record"
        ),
    )


def downgrade() -> None:
    op.drop_table("resting_heart_rate")
