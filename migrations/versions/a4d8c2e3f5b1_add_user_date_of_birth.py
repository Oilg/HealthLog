"""add user date_of_birth

Revision ID: a4d8c2e3f5b1
Revises: a1b2c3d4e5f6
Create Date: 2026-05-27 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a4d8c2e3f5b1"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("date_of_birth", sa.Date(), nullable=True))
    # Возраст должен быть в разумных границах: от 5 до 130 лет.
    # NULL разрешён — DOB опциональное поле, при отсутствии используется дефолтный порог
    # (как для возрастной группы < 60 лет).
    op.create_check_constraint(
        "ck_users_date_of_birth_range",
        "users",
        "date_of_birth IS NULL OR ("
        "date_of_birth <= (CURRENT_DATE - INTERVAL '5 years') "
        "AND date_of_birth >= (CURRENT_DATE - INTERVAL '130 years'))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_date_of_birth_range", "users", type_="check")
    op.drop_column("users", "date_of_birth")
