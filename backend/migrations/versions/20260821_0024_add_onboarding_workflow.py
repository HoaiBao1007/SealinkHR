"""Add configurable onboarding form and staging workflow.

Revision ID: 20260821_0024
Revises: 20260818_0023
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260821_0024"
down_revision: Union[str, None] = "20260818_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "onboarding_form_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("success_message", sa.Text(), nullable=False),
        sa.Column("fields_json", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_onboarding_form_versions_status", "onboarding_form_versions", ["status"])
    op.create_index(
        "ix_onboarding_form_versions_status_version",
        "onboarding_form_versions",
        ["status", "version_number"],
    )

    op.create_table(
        "onboarding_submissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("form_version_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("application_type", sa.String(length=30), nullable=False),
        sa.Column("answers_json", sa.Text(), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewer_id", sa.Integer(), nullable=True),
        sa.Column("employee_id", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["form_version_id"], ["onboarding_form_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_onboarding_submissions_public_id", "onboarding_submissions", ["public_id"])
    op.create_index("ix_onboarding_submissions_status", "onboarding_submissions", ["status"])
    op.create_index("ix_onboarding_submissions_status_submitted", "onboarding_submissions", ["status", "submitted_at"])
    op.create_index("ix_onboarding_submissions_email", "onboarding_submissions", ["email"])

    op.create_table(
        "onboarding_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("field_key", sa.String(length=80), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["onboarding_submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_onboarding_attachments_submission_id", "onboarding_attachments", ["submission_id"])


def downgrade() -> None:
    op.drop_index("ix_onboarding_attachments_submission_id", table_name="onboarding_attachments")
    op.drop_table("onboarding_attachments")
    op.drop_index("ix_onboarding_submissions_email", table_name="onboarding_submissions")
    op.drop_index("ix_onboarding_submissions_status_submitted", table_name="onboarding_submissions")
    op.drop_index("ix_onboarding_submissions_status", table_name="onboarding_submissions")
    op.drop_index("ix_onboarding_submissions_public_id", table_name="onboarding_submissions")
    op.drop_table("onboarding_submissions")
    op.drop_index("ix_onboarding_form_versions_status_version", table_name="onboarding_form_versions")
    op.drop_index("ix_onboarding_form_versions_status", table_name="onboarding_form_versions")
    op.drop_table("onboarding_form_versions")
