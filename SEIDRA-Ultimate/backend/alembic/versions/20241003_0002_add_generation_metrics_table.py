"""add generation metrics table"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

revision = "20241003_0002"
down_revision = "20240925_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(length=36),
            sa.ForeignKey("generation_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "persona_id",
            sa.Integer(),
            sa.ForeignKey("personas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("media_type", sa.String(length=50), nullable=False, server_default="image"),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("outputs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("throughput", sa.Float(), nullable=True),
        sa.Column("vram_allocated_mb", sa.Float(), nullable=True),
        sa.Column("vram_reserved_mb", sa.Float(), nullable=True),
        sa.Column("vram_peak_mb", sa.Float(), nullable=True),
        sa.Column("vram_delta_mb", sa.Float(), nullable=True),
        sa.Column("extra", sqlite.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_generation_metrics_job_id", "generation_metrics", ["job_id"])
    op.create_index("ix_generation_metrics_user_id", "generation_metrics", ["user_id"])
    op.create_index("ix_generation_metrics_persona_id", "generation_metrics", ["persona_id"])
    op.create_index("ix_generation_metrics_media_type", "generation_metrics", ["media_type"])
    op.create_index("ix_generation_metrics_created_at", "generation_metrics", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_generation_metrics_created_at", table_name="generation_metrics")
    op.drop_index("ix_generation_metrics_media_type", table_name="generation_metrics")
    op.drop_index("ix_generation_metrics_persona_id", table_name="generation_metrics")
    op.drop_index("ix_generation_metrics_user_id", table_name="generation_metrics")
    op.drop_index("ix_generation_metrics_job_id", table_name="generation_metrics")
    op.drop_table("generation_metrics")
