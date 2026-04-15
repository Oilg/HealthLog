"""add sync status, analysis reports, sync schedules, apns token

Revision ID: b1c2d3e4f5a6
Revises: e3a91c2d7f40
Create Date: 2026-04-15 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "e3a91c2d7f40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add sync status columns and APNs token to users
    op.add_column("users", sa.Column("last_sync_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("last_sync_records_count", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("apns_device_token", sa.String(), nullable=True))

    # Create analysis_reports table
    op.create_table(
        "analysis_reports",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(), nullable=False),
        sa.Column("period_from", sa.DateTime(), nullable=False),
        sa.Column("period_to", sa.DateTime(), nullable=False),
        sa.Column("window", sa.String(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_reports_user_analyzed", "analysis_reports", ["user_id", "analyzed_at"])

    # Create sync_schedules table
    op.create_table(
        "sync_schedules",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("day_of_week", sa.String(), nullable=False),
        sa.Column("sync_time", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False, server_default="UTC"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "day_of_week", name="uq_sync_schedule_day"),
    )


def downgrade() -> None:
    op.drop_table("sync_schedules")
    op.drop_index("ix_analysis_reports_user_analyzed")
    op.drop_table("analysis_reports")
    op.drop_column("users", "apns_device_token")
    op.drop_column("users", "last_sync_records_count")
    op.drop_column("users", "last_sync_at")
