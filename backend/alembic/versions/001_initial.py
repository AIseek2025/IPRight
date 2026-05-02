"""Initial migration - create all core tables

Revision ID: 001_initial
Revises:
Create Date: 2026-04-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import JSON

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(32), server_default="V1.0"),
        sa.Column("industry", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), server_default="queued", nullable=False),
        sa.Column("current_stage", sa.String(32), nullable=True),
        sa.Column("active_build_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "task_builds",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("build_no", sa.Integer(), server_default="1"),
        sa.Column("status", sa.String(32), server_default="queued"),
        sa.Column("current_stage", sa.String(32), nullable=True),
        sa.Column("trigger_type", sa.String(32), server_default="create"),
        sa.Column("runtime_workspace", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "build_stage_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("build_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("task_builds.id"), nullable=False),
        sa.Column("stage_name", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), server_default="queued"),
        sa.Column("attempt_no", sa.Integer(), server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("metrics_json", postgresql.JSONB, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("build_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("task_builds.id"), nullable=True),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("artifact_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("local_path", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("checksum", sa.String(128), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "screenshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("build_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("task_builds.id"), nullable=True),
        sa.Column("scenario_id", sa.String(128), nullable=False),
        sa.Column("page_title", sa.String(255), nullable=False),
        sa.Column("route", sa.Text(), nullable=False),
        sa.Column("image_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("steps_markdown", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("build_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("task_builds.id"), nullable=True),
        sa.Column("export_type", sa.String(64), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifacts.id"), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("download_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), server_default="preparing"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "task_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("build_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("task_builds.id"), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("payload_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("task_events")
    op.drop_table("exports")
    op.drop_table("screenshots")
    op.drop_table("artifacts")
    op.drop_table("build_stage_runs")
    op.drop_table("task_builds")
    op.drop_table("tasks")
