"""Add employee offboarding request and approval workflow.

Revision ID: 20260828_0037
Revises: 20260826_0036
Create Date: 2026-08-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260828_0037"
down_revision: Union[str, None] = "20260826_0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "offboarding_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("requester_user_id", sa.Integer(), nullable=False),
        sa.Column("manager_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("resume_status", sa.String(length=40), nullable=True),
        sa.Column("request_date", sa.Date(), nullable=False),
        sa.Column("notice_period_days", sa.Integer(), nullable=False),
        sa.Column("desired_last_working_date", sa.Date(), nullable=False),
        sa.Column("confirmed_last_working_date", sa.Date(), nullable=True),
        sa.Column("last_pay_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("personal_opinion", sa.Text(), nullable=False),
        sa.Column("no_grievance_confirmed", sa.Boolean(), nullable=False),
        sa.Column("handover_commitment_confirmed", sa.Boolean(), nullable=False),
        sa.Column("employee_name_snapshot", sa.String(length=150), nullable=False),
        sa.Column("employee_code_snapshot", sa.String(length=50), nullable=True),
        sa.Column("position_snapshot", sa.String(length=150), nullable=True),
        sa.Column("department_snapshot", sa.String(length=150), nullable=True),
        sa.Column("manager_name_snapshot", sa.String(length=150), nullable=True),
        sa.Column("department_note", sa.Text(), nullable=True),
        sa.Column("hr_note", sa.Text(), nullable=True),
        sa.Column("director_note", sa.Text(), nullable=True),
        sa.Column("department_noted_by_id", sa.Integer(), nullable=True),
        sa.Column("hr_noted_by_id", sa.Integer(), nullable=True),
        sa.Column("director_approved_by_id", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("department_noted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hr_noted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("director_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requester_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["manager_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["department_noted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["hr_noted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["director_approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_offboarding_requests_public_id", "offboarding_requests", ["public_id"])
    op.create_index("ix_offboarding_requests_employee_id", "offboarding_requests", ["employee_id"])
    op.create_index("ix_offboarding_requests_requester_user_id", "offboarding_requests", ["requester_user_id"])
    op.create_index("ix_offboarding_requests_manager_user_id", "offboarding_requests", ["manager_user_id"])
    op.create_index("ix_offboarding_requests_status", "offboarding_requests", ["status"])
    op.create_index("ix_offboarding_requests_status_submitted", "offboarding_requests", ["status", "submitted_at"])
    op.create_index("ix_offboarding_requests_employee_status", "offboarding_requests", ["employee_id", "status"])

    op.create_table(
        "offboarding_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=40), nullable=True),
        sa.Column("to_status", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["offboarding_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offboarding_actions_request_id", "offboarding_actions", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_offboarding_actions_request_id", table_name="offboarding_actions")
    op.drop_table("offboarding_actions")
    op.drop_index("ix_offboarding_requests_employee_status", table_name="offboarding_requests")
    op.drop_index("ix_offboarding_requests_status_submitted", table_name="offboarding_requests")
    op.drop_index("ix_offboarding_requests_status", table_name="offboarding_requests")
    op.drop_index("ix_offboarding_requests_manager_user_id", table_name="offboarding_requests")
    op.drop_index("ix_offboarding_requests_requester_user_id", table_name="offboarding_requests")
    op.drop_index("ix_offboarding_requests_employee_id", table_name="offboarding_requests")
    op.drop_index("ix_offboarding_requests_public_id", table_name="offboarding_requests")
    op.drop_table("offboarding_requests")
