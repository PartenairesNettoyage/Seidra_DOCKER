"""add notifications table"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

revision = "20241009_0003"
down_revision = "20241003_0002_add_generation_metrics_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=50), nullable=False, server_default="system"),
        sa.Column("metadata", sqlite.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("tags", sqlite.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_level", "notifications", ["level"])
    op.create_index("ix_notifications_category", "notifications", ["category"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_category", table_name="notifications")
    op.drop_index("ix_notifications_level", table_name="notifications")
    op.drop_table("notifications")
