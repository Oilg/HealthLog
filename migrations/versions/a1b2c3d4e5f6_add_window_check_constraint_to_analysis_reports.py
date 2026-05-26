"""add window check constraint to analysis_reports

Revision ID: a1b2c3d4e5f6
Revises: b1c2d3e4f5a6
Create Date: 2026-05-26 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_analysis_reports_window",
        "analysis_reports",
        "window IN ('night', 'week', 'month')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_analysis_reports_window", "analysis_reports", type_="check")
