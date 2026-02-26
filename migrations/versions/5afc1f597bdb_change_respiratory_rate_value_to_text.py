"""change respiratory_rate.value to text

Revision ID: 5afc1f597bdb
Revises: 2cdca49ff2e2
Create Date: 2025-10-28 23:21:12.893931

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5afc1f597bdb'
down_revision = '2cdca49ff2e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "respiratory_rate",
        "value",
        existing_type=sa.Float(),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "respiratory_rate",
        "value",
        existing_type=sa.Text(),
        type_=sa.Float(),
        existing_nullable=True,
    )
