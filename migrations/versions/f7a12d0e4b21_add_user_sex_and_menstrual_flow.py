"""add user sex and menstrual flow

Revision ID: f7a12d0e4b21
Revises: c41b7f3e9a12
Create Date: 2026-03-05 00:00:01.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f7a12d0e4b21"
down_revision = "c41b7f3e9a12"
branch_labels = None
depends_on = None

LEGACY_EMAIL = "legacy-user@local"


def upgrade() -> None:
    op.add_column("users", sa.Column("sex", sa.String(), nullable=True))
    # Set sex only for technical legacy account used in previous migration.
    op.execute(
        sa.text(
            """
            UPDATE users
            SET sex = 'male'
            WHERE email = :legacy_email AND sex IS NULL
            """
        ).bindparams(legacy_email=LEGACY_EMAIL)
    )

    unresolved = op.get_bind().execute(sa.text("SELECT count(*) FROM users WHERE sex IS NULL")).scalar_one()
    if unresolved > 0:
        raise RuntimeError(
            "Найдены пользователи без поля sex. Заполни users.sex ('male'/'female') вручную и повтори миграцию."
        )

    op.alter_column("users", "sex", nullable=False)
    op.create_check_constraint("ck_users_sex", "users", "sex in ('male', 'female')")

    op.create_table(
        "menstrual_flow",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sourceName", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=True),
        sa.Column("creationDate", sa.DateTime(), nullable=False),
        sa.Column("startDate", sa.DateTime(), nullable=False),
        sa.Column("endDate", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "sourceName", "startDate", "endDate", name="uq_menstrual_flow_record"),
    )


def downgrade() -> None:
    op.drop_table("menstrual_flow")
    op.drop_constraint("ck_users_sex", "users", type_="check")
    op.drop_column("users", "sex")
