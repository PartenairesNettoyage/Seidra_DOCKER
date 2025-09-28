"""create core tables"""

from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

revision = "20240925_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=50), nullable=False, unique=True),
        sa.Column("email", sa.String(length=100), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_nsfw_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("age_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("settings", sqlite.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "personas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("style_prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("lora_models", sqlite.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("generation_params", sqlite.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("tags", sqlite.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_nsfw", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata", sqlite.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_personas_user_id", "personas", ["user_id"])

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("persona_id", sa.Integer(), sa.ForeignKey("personas.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_type", sa.String(length=50), nullable=False, server_default="image"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("lora_models", sqlite.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("parameters", sqlite.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("result_images", sqlite.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metadata", sqlite.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_nsfw", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("nsfw_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_generation_jobs_user_id", "generation_jobs", ["user_id"])
    op.create_index("ix_generation_jobs_status", "generation_jobs", ["status"])

    op.create_table(
        "lora_models",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("download_url", sa.String(length=500), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("tags", sqlite.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_downloaded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "media_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(length=36), sa.ForeignKey("generation_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("thumbnail_path", sa.String(length=500), nullable=True),
        sa.Column("file_type", sa.String(length=50), nullable=False, server_default="image"),
        sa.Column("mime_type", sa.String(length=100), nullable=False, server_default="image/png"),
        sa.Column("metadata", sqlite.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("tags", sqlite.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_nsfw", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("nsfw_tags", sqlite.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_media_items_user_id", "media_items", ["user_id"])
    op.create_index("ix_media_items_job_id", "media_items", ["job_id"])

    op.create_table(
        "nsfw_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("age_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("intensity", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("categories", sqlite.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("overrides", sqlite.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_nsfw_settings_user_id", "nsfw_settings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_nsfw_settings_user_id", table_name="nsfw_settings")
    op.drop_table("nsfw_settings")
    op.drop_index("ix_media_items_job_id", table_name="media_items")
    op.drop_index("ix_media_items_user_id", table_name="media_items")
    op.drop_table("media_items")
    op.drop_table("lora_models")
    op.drop_index("ix_generation_jobs_status", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_user_id", table_name="generation_jobs")
    op.drop_table("generation_jobs")
    op.drop_index("ix_personas_user_id", table_name="personas")
    op.drop_table("personas")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
