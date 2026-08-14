"""Add versioned payroll policy configuration.

Revision ID: 20260804_0018
Revises: 20260803_0017
Create Date: 2026-08-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260804_0018"
down_revision: Union[str, None] = "20260803_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "salary_policies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("legal_basis", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("common_minimum_wage", sa.Integer(), nullable=False, server_default="2530000"),
        sa.Column("regional_minimum_wage_i", sa.Integer(), nullable=False, server_default="5310000"),
        sa.Column("regional_minimum_wage_ii", sa.Integer(), nullable=False, server_default="4730000"),
        sa.Column("regional_minimum_wage_iii", sa.Integer(), nullable=False, server_default="4140000"),
        sa.Column("regional_minimum_wage_iv", sa.Integer(), nullable=False, server_default="3700000"),
        sa.Column("default_region", sa.String(length=8), nullable=False, server_default="I"),
        sa.Column("social_health_salary_cap", sa.Integer(), nullable=False, server_default="50600000"),
        sa.Column("unemployment_cap_multiplier", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("social_employee_rate", sa.Float(), nullable=False, server_default="0.08"),
        sa.Column("health_employee_rate", sa.Float(), nullable=False, server_default="0.015"),
        sa.Column("unemployment_employee_rate", sa.Float(), nullable=False, server_default="0.01"),
        sa.Column("social_employer_rate", sa.Float(), nullable=False, server_default="0.175"),
        sa.Column("health_employer_rate", sa.Float(), nullable=False, server_default="0.03"),
        sa.Column("unemployment_employer_rate", sa.Float(), nullable=False, server_default="0.01"),
        sa.Column("union_fund_employer_rate", sa.Float(), nullable=False, server_default="0.02"),
        sa.Column("union_employee_rate", sa.Float(), nullable=False, server_default="0.005"),
        sa.Column("union_employee_cap", sa.Integer(), nullable=False, server_default="234000"),
        sa.Column("personal_deduction", sa.Integer(), nullable=False, server_default="15500000"),
        sa.Column("dependent_deduction", sa.Integer(), nullable=False, server_default="6200000"),
        sa.Column("probation_withholding_rate", sa.Float(), nullable=False, server_default="0.1"),
        sa.Column("probation_withholding_threshold", sa.Integer(), nullable=False, server_default="2000000"),
        sa.Column("pit_brackets_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_code"),
    )
    op.create_index("ix_salary_policies_version_code", "salary_policies", ["version_code"])
    op.create_index("ix_salary_policies_effective_from", "salary_policies", ["effective_from"])
    op.add_column("monthly_salary_inputs", sa.Column("salary_policy_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_monthly_salary_inputs_salary_policy", "monthly_salary_inputs", "salary_policies", ["salary_policy_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_monthly_salary_inputs_salary_policy", "monthly_salary_inputs", type_="foreignkey")
    op.drop_column("monthly_salary_inputs", "salary_policy_id")
    op.drop_index("ix_salary_policies_effective_from", table_name="salary_policies")
    op.drop_index("ix_salary_policies_version_code", table_name="salary_policies")
    op.drop_table("salary_policies")
