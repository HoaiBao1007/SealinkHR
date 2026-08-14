"""add immutable commission wallet ledger and payout policy

Revision ID: 20260713_0001
Revises: 637b01338b98
"""
from alembic import op
import sqlalchemy as sa

revision = "20260713_0001"
down_revision = "637b01338b98"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commission_wallet_ledger",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("commission_periods.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("commission_jobs.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("sales_rep", sa.String(length=150), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("payout_period", sa.String(length=7), nullable=True),
        sa.Column("payout_batch", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for column in ("period_id", "job_id", "sales_rep", "employee_id", "entry_type", "payout_period", "payout_batch"):
        op.create_index(f"ix_commission_wallet_ledger_{column}", "commission_wallet_ledger", [column])
    op.create_table(
        "commission_payout_policies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sales_rep", sa.String(length=150), nullable=False, unique=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payout_mode", sa.String(length=24), nullable=False, server_default="MANUAL"),
        sa.Column("minimum_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_commission_payout_policies_sales_rep", "commission_payout_policies", ["sales_rep"])
    op.create_index("ix_commission_payout_policies_employee_id", "commission_payout_policies", ["employee_id"])


def downgrade() -> None:
    op.drop_index("ix_commission_payout_policies_employee_id", table_name="commission_payout_policies")
    op.drop_index("ix_commission_payout_policies_sales_rep", table_name="commission_payout_policies")
    op.drop_table("commission_payout_policies")
    for column in ("payout_batch", "payout_period", "entry_type", "employee_id", "sales_rep", "job_id", "period_id"):
        op.drop_index(f"ix_commission_wallet_ledger_{column}", table_name="commission_wallet_ledger")
    op.drop_table("commission_wallet_ledger")
