"""Add sheets fields to shift_records and telegram_groups

Revision ID: 002
Revises: 001
Create Date: 2026-04-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # shift_records: add written_at and retry_count
    op.add_column(
        "shift_records",
        sa.Column("written_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "shift_records",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # telegram_groups: add sheet_id and sheet_name
    op.add_column(
        "telegram_groups",
        sa.Column("sheet_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "telegram_groups",
        sa.Column("sheet_name", sa.String(length=200), nullable=True, server_default="Sheet1"),
    )


def downgrade() -> None:
    op.drop_column("telegram_groups", "sheet_name")
    op.drop_column("telegram_groups", "sheet_id")
    op.drop_column("shift_records", "retry_count")
    op.drop_column("shift_records", "written_at")
