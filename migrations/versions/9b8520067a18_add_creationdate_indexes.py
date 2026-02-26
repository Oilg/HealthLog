"""add creationDate indexes

Revision ID: 9b8520067a18
Revises: 42b73e081090
Create Date: 2025-10-27 23:08:47.515741

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9b8520067a18'
down_revision = '42b73e081090'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index('ix_sleep_analysis_creationDate', 'sleep_analysis', ['creationDate'])
    op.create_index('ix_sleep_duration_goal_creationDate', 'sleep_duration_goal', ['creationDate'])
    op.create_index('ix_heart_rate_creationDate', 'heart_rate', ['creationDate'])
    op.create_index('ix_heart_rate_variability_creationDate', 'heart_rate_variability', ['creationDate'])
    op.create_index('ix_respiratory_rate_creationDate', 'respiratory_rate', ['creationDate'])
    op.create_index('ix_vo2max_creationDate', 'vo_2_max', ['creationDate'])


def downgrade() -> None:
    op.drop_index('ix_sleep_analysis_creationDate')
    op.drop_index('ix_sleep_duration_goal_creationDate')
    op.drop_index('ix_heart_rate_creationDate')
    op.drop_index('ix_heart_rate_variability_creationDate')
    op.drop_index('ix_respiratory_rate_creationDate')
    op.drop_index('ix_vo2max_creationDate')
