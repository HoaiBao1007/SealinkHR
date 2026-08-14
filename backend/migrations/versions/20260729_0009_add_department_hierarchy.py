"""Add parent-child hierarchy to departments.

Revision ID: 20260729_0009
Revises: 20260729_0008
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_0009"
down_revision = "20260729_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("departments", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.add_column(
        "departments",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_foreign_key(
        "fk_departments_parent_id",
        "departments",
        "departments",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_departments_parent_id", "departments", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_departments_parent_id", table_name="departments")
    op.drop_constraint("fk_departments_parent_id", "departments", type_="foreignkey")
    op.drop_column("departments", "sort_order")
    op.drop_column("departments", "parent_id")
