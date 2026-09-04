"""add salary approval workflows

Revision ID: 20260821_0026
Revises: 20260821_0025
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260821_0026"
down_revision: Union[str, None] = "20260821_0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "salary_approval_workflows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("salary_period", sa.String(length=7), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("confirmed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("salary_period"),
    )
    op.create_index("ix_salary_approval_workflows_salary_period", "salary_approval_workflows", ["salary_period"], unique=True)
    op.create_index("ix_salary_approval_workflows_status", "salary_approval_workflows", ["status"], unique=False)
    op.execute(
        """
        INSERT INTO salary_approval_workflows (salary_period, status, created_at, updated_at)
        SELECT DISTINCT salary_period, 'APPROVED', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM monthly_salary_inputs
        WHERE is_published = 1
        """
    )


def downgrade() -> None:
    op.drop_index("ix_salary_approval_workflows_status", table_name="salary_approval_workflows")
    op.drop_index("ix_salary_approval_workflows_salary_period", table_name="salary_approval_workflows")
    op.drop_table("salary_approval_workflows")
