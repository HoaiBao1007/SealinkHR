"""Convert offboarding to a public, versioned form workflow.

Revision ID: 20260828_0039
Revises: 20260828_0038
Create Date: 2026-08-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260828_0039"
down_revision: Union[str, None] = "20260828_0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "offboarding_form_versions",
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
    op.create_index("ix_offboarding_form_versions_status", "offboarding_form_versions", ["status"])
    op.create_index("ix_offboarding_form_versions_status_version", "offboarding_form_versions", ["status", "version_number"])

    op.add_column("offboarding_requests", sa.Column("form_version_id", sa.Integer(), nullable=True))
    op.add_column("offboarding_requests", sa.Column("email_snapshot", sa.String(length=150), nullable=True))
    op.add_column("offboarding_requests", sa.Column("answers_json", sa.Text(), nullable=True))
    op.add_column("offboarding_requests", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column("offboarding_requests", sa.Column("reviewer_id", sa.Integer(), nullable=True))
    op.add_column("offboarding_requests", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("offboarding_requests", "employee_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("offboarding_requests", "requester_user_id", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key("fk_offboarding_request_form_version", "offboarding_requests", "offboarding_form_versions", ["form_version_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_offboarding_request_reviewer", "offboarding_requests", "users", ["reviewer_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_offboarding_requests_form_version_id", "offboarding_requests", ["form_version_id"])
    op.create_index("ix_offboarding_requests_email_snapshot", "offboarding_requests", ["email_snapshot"])

    op.create_table(
        "offboarding_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("field_key", sa.String(length=80), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["offboarding_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offboarding_attachments_submission_id", "offboarding_attachments", ["submission_id"])


def downgrade() -> None:
    op.drop_index("ix_offboarding_attachments_submission_id", table_name="offboarding_attachments")
    op.drop_table("offboarding_attachments")
    op.drop_index("ix_offboarding_requests_email_snapshot", table_name="offboarding_requests")
    op.drop_index("ix_offboarding_requests_form_version_id", table_name="offboarding_requests")
    op.drop_constraint("fk_offboarding_request_reviewer", "offboarding_requests", type_="foreignkey")
    op.drop_constraint("fk_offboarding_request_form_version", "offboarding_requests", type_="foreignkey")
    op.alter_column("offboarding_requests", "requester_user_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("offboarding_requests", "employee_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("offboarding_requests", "reviewed_at")
    op.drop_column("offboarding_requests", "reviewer_id")
    op.drop_column("offboarding_requests", "review_note")
    op.drop_column("offboarding_requests", "answers_json")
    op.drop_column("offboarding_requests", "email_snapshot")
    op.drop_column("offboarding_requests", "form_version_id")
    op.drop_index("ix_offboarding_form_versions_status_version", table_name="offboarding_form_versions")
    op.drop_index("ix_offboarding_form_versions_status", table_name="offboarding_form_versions")
    op.drop_table("offboarding_form_versions")
