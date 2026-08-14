"""Store employee-type promotions with their effective date.

Revision ID: 20260722_0005
Revises: 20260714_0004
"""
from alembic import op
import sqlalchemy as sa


revision = "20260722_0005"
down_revision = "20260714_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("salary_decisions", sa.Column("old_employee_type", sa.String(length=50), nullable=True))
    op.add_column("salary_decisions", sa.Column("new_employee_type", sa.String(length=50), nullable=True))
    op.add_column("salary_decisions", sa.Column("old_meal_allowance", sa.Integer(), nullable=True))
    op.add_column("salary_decisions", sa.Column("old_trans_allowance", sa.Integer(), nullable=True))
    op.add_column("salary_decisions", sa.Column("old_phone_allowance", sa.Integer(), nullable=True))
    op.add_column("salary_decisions", sa.Column("old_other_allowance", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("salary_decisions", "old_other_allowance")
    op.drop_column("salary_decisions", "old_phone_allowance")
    op.drop_column("salary_decisions", "old_trans_allowance")
    op.drop_column("salary_decisions", "old_meal_allowance")
    op.drop_column("salary_decisions", "new_employee_type")
    op.drop_column("salary_decisions", "old_employee_type")
