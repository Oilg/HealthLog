"""sleep apnea events metadata columns

Revision ID: a8f3c1d2e4b5
Revises: f7a12d0e4b21
Create Date: 2026-04-09 12:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "a8f3c1d2e4b5"
down_revision = "f7a12d0e4b21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sleep_apnea_events", sa.Column("point_count", sa.Integer(), nullable=True))
    op.add_column("sleep_apnea_events", sa.Column("support_level", sa.String(), nullable=True))
    op.add_column("sleep_apnea_events", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("sleep_apnea_events", sa.Column("baseline_rr", sa.Float(), nullable=True))
    op.add_column("sleep_apnea_events", sa.Column("baseline_hr", sa.Float(), nullable=True))
    op.add_column("sleep_apnea_events", sa.Column("baseline_hrv", sa.Float(), nullable=True))
    op.add_column("sleep_apnea_events", sa.Column("sleep_hours_context", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("sleep_apnea_events", "sleep_hours_context")
    op.drop_column("sleep_apnea_events", "baseline_hrv")
    op.drop_column("sleep_apnea_events", "baseline_hr")
    op.drop_column("sleep_apnea_events", "baseline_rr")
    op.drop_column("sleep_apnea_events", "confidence")
    op.drop_column("sleep_apnea_events", "support_level")
    op.drop_column("sleep_apnea_events", "point_count")
