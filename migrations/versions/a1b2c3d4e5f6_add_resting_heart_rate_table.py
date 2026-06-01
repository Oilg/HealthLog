"""add resting_heart_rate table

Revision ID: a1b2c3d4e5f6
Revises: e3a91c2d7f40
Create Date: 2026-06-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "e3a91c2d7f40"
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
