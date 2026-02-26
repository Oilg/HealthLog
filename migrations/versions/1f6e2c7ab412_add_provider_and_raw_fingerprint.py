"""add provider and raw fingerprint

Revision ID: 1f6e2c7ab412
Revises: bc2a4f91c8de
Create Date: 2026-02-26 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1f6e2c7ab412"
down_revision = "bc2a4f91c8de"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("xml_uploads", sa.Column("provider", sa.String(), nullable=True))
    op.add_column("xml_uploads", sa.Column("data_format", sa.String(), nullable=True))

    op.execute("UPDATE xml_uploads SET provider = 'apple_health' WHERE provider IS NULL")
    op.execute("UPDATE xml_uploads SET data_format = 'xml' WHERE data_format IS NULL")

    op.alter_column("xml_uploads", "provider", nullable=False)
    op.alter_column("xml_uploads", "data_format", nullable=False)

    op.add_column("raw_health_records", sa.Column("provider", sa.String(), nullable=True))
    op.add_column("raw_health_records", sa.Column("data_format", sa.String(), nullable=True))
    op.add_column("raw_health_records", sa.Column("record_fingerprint", sa.String(length=64), nullable=True))

    op.execute("UPDATE raw_health_records SET provider = 'apple_health' WHERE provider IS NULL")
    op.execute("UPDATE raw_health_records SET data_format = 'xml' WHERE data_format IS NULL")
    op.execute(
        """
        UPDATE raw_health_records
        SET record_fingerprint = md5(
            coalesce(provider, '') || '|' ||
            coalesce(record_type, '') || '|' ||
            coalesce("sourceName", '') || '|' ||
            coalesce("startDate"::text, '') || '|' ||
            coalesce("endDate"::text, '') || '|' ||
            coalesce(payload::text, '')
        )
        WHERE record_fingerprint IS NULL
        """
    )

    op.alter_column("raw_health_records", "provider", nullable=False)
    op.alter_column("raw_health_records", "data_format", nullable=False)
    op.alter_column("raw_health_records", "record_fingerprint", nullable=False)

    op.execute(
        """
        DELETE FROM raw_health_records a
        USING raw_health_records b
        WHERE a.id > b.id
          AND a.provider = b.provider
          AND a.record_fingerprint = b.record_fingerprint;
        """
    )

    op.create_unique_constraint(
        "uq_raw_record_fingerprint",
        "raw_health_records",
        ["provider", "record_fingerprint"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_raw_record_fingerprint", "raw_health_records", type_="unique")
    op.drop_column("raw_health_records", "record_fingerprint")
    op.drop_column("raw_health_records", "data_format")
    op.drop_column("raw_health_records", "provider")

    op.drop_column("xml_uploads", "data_format")
    op.drop_column("xml_uploads", "provider")
