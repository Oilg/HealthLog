"""add subscription_status to users

Revision ID: d9e3f1a2b4c5
Revises: f7a12d0e4b21
Create Date: 2026-05-25 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d9e3f1a2b4c5"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "subscription_status",
            sa.String,
            nullable=False,
            server_default="free",
        ),
    )
    op.create_check_constraint(
        "ck_users_subscription_status",
        "users",
        "subscription_status IN ('free', 'paid')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_subscription_status", "users", type_="check")
    op.drop_column("users", "subscription_status")
