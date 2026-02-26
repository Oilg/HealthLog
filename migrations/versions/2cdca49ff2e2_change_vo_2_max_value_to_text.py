"""change vo_2_max.value to text

Revision ID: 2cdca49ff2e2
Revises: 9b8520067a18
Create Date: 2025-10-28 23:07:54.081666

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2cdca49ff2e2'
down_revision = '9b8520067a18'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "vo_2_max",
        "value",
        existing_type=sa.Float(),
        type_=sa.Text(),
        postgresql_using="value::text",
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "vo_2_max",
        "value",
        existing_type=sa.Text(),
        type_=sa.Float(),
        postgresql_using="NULLIF(trim(value), '')::double precision",
        nullable=True,
    )
