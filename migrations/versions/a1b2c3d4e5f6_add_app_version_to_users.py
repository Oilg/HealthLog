"""add app_version to users

Revision ID: a1b2c3d4e5f6
Revises: f7a12d0e4b21
Create Date: 2026-06-02 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "f7a12d0e4b21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("app_version", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "app_version")
