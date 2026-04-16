"""rename xml_uploads to health_uploads and raw_xml to raw_payload

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-04-16 00:00:00.000000

"""

from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop FK from raw_health_records that references xml_uploads
    op.drop_constraint("raw_health_records_upload_id_fkey", "raw_health_records", type_="foreignkey")

    # Rename table
    op.rename_table("xml_uploads", "health_uploads")

    # Rename column
    op.alter_column("health_uploads", "raw_xml", new_column_name="raw_payload")

    # Recreate FK pointing to new table name
    op.create_foreign_key(
        "raw_health_records_upload_id_fkey",
        "raw_health_records",
        "health_uploads",
        ["upload_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("raw_health_records_upload_id_fkey", "raw_health_records", type_="foreignkey")

    op.alter_column("health_uploads", "raw_payload", new_column_name="raw_xml")

    op.rename_table("health_uploads", "xml_uploads")

    op.create_foreign_key(
        "raw_health_records_upload_id_fkey",
        "raw_health_records",
        "xml_uploads",
        ["upload_id"],
        ["id"],
    )
