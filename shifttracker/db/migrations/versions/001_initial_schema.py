"""Initial schema: all 7 tables

Revision ID: 001
Revises:
Create Date: 2026-04-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # employees
    op.create_table(
        "employees",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("employee_code", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_code"),
        sa.UniqueConstraint("telegram_user_id"),
    )

    # telegram_groups
    op.create_table(
        "telegram_groups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("shift_start_hour", sa.Integer(), nullable=False),
        sa.Column("shift_end_hour", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id"),
    )

    # group_employees
    op.create_table(
        "group_employees",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("sheet_row", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["telegram_groups.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "employee_id"),
    )

    # caption_rules
    op.create_table(
        "caption_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("pattern", sa.String(length=255), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["telegram_groups.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # shift_records
    op.create_table(
        "shift_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("shift_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_message_id", sa.BigInteger(), nullable=False),
        sa.Column("source_link", sa.String(length=500), nullable=False),
        sa.Column("sheet_write_status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "shift_date"),
    )

    # processing_log
    op.create_table(
        "processing_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=True),
        sa.Column("shift_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("source_link", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_processing_log_employee_date",
        "processing_log",
        ["employee_id", "shift_date"],
    )

    # processed_updates
    op.create_table(
        "processed_updates",
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("update_id"),
    )


def downgrade() -> None:
    op.drop_table("processed_updates")
    op.drop_index("ix_processing_log_employee_date", table_name="processing_log")
    op.drop_table("processing_log")
    op.drop_table("shift_records")
    op.drop_table("caption_rules")
    op.drop_table("group_employees")
    op.drop_table("telegram_groups")
    op.drop_table("employees")
