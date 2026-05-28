"""add user timezone

Revision ID: b7c8e9f0a1d2
Revises: a4d8c2e3f5b1
Create Date: 2026-05-28 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7c8e9f0a1d2"
down_revision = "a4d8c2e3f5b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("timezone", sa.String(), nullable=False, server_default="UTC"),
    )


def downgrade() -> None:
    op.drop_column("users", "timezone")
