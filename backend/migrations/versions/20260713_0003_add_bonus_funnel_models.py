"""add flexible bonus funnel models

Revision ID: 20260713_0003
Revises: 20260713_0002
"""
from alembic import op
import sqlalchemy as sa

revision = "20260713_0003"
down_revision = "20260713_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("commission_calculation_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("commission_periods.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sales_rep", sa.String(length=150), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("monthly_bonus", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_bonus_quarter", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for column in ("period_id", "sales_rep", "employee_id"):
        op.create_index(f"ix_commission_calculation_snapshots_{column}", "commission_calculation_snapshots", [column])
    op.create_table("commission_bonus_entitlements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("commission_calculation_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("commission_periods.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("commission_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sales_rep", sa.String(length=150), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("calculated_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_period", sa.String(length=30), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for column in ("snapshot_id", "period_id", "job_id", "sales_rep", "employee_id", "source_period", "status"):
        op.create_index(f"ix_commission_bonus_entitlements_{column}", "commission_bonus_entitlements", [column])
    op.create_table("commission_payout_schedules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sales_rep", sa.String(length=150), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payout_period", sa.String(length=7), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="SCHEDULED"),
        sa.Column("total_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("approved_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for column in ("sales_rep", "employee_id", "payout_period", "status"):
        op.create_index(f"ix_commission_payout_schedules_{column}", "commission_payout_schedules", [column])
    op.add_column("commission_wallet_ledger", sa.Column("entitlement_id", sa.Integer(), nullable=True))
    op.add_column("commission_wallet_ledger", sa.Column("schedule_id", sa.Integer(), nullable=True))
    op.add_column("commission_wallet_ledger", sa.Column("reason_code", sa.String(length=50), nullable=True))
    op.add_column("commission_wallet_ledger", sa.Column("created_by", sa.String(length=100), nullable=True))
    op.add_column("commission_wallet_ledger", sa.Column("approved_by", sa.String(length=100), nullable=True))
    op.create_foreign_key("fk_wallet_entitlement", "commission_wallet_ledger", "commission_bonus_entitlements", ["entitlement_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_wallet_schedule", "commission_wallet_ledger", "commission_payout_schedules", ["schedule_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_commission_wallet_ledger_entitlement_id", "commission_wallet_ledger", ["entitlement_id"])
    op.create_index("ix_commission_wallet_ledger_schedule_id", "commission_wallet_ledger", ["schedule_id"])
    op.create_index("ix_commission_wallet_ledger_reason_code", "commission_wallet_ledger", ["reason_code"])
    op.create_table("commission_payout_schedule_allocations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("schedule_id", sa.Integer(), sa.ForeignKey("commission_payout_schedules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entitlement_id", sa.Integer(), sa.ForeignKey("commission_bonus_entitlements.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ledger_entry_id", sa.Integer(), sa.ForeignKey("commission_wallet_ledger.id", ondelete="SET NULL"), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="SCHEDULED"),
    )
    for column in ("schedule_id", "entitlement_id", "ledger_entry_id", "status"):
        op.create_index(f"ix_commission_payout_schedule_allocations_{column}", "commission_payout_schedule_allocations", [column])


def downgrade() -> None:
    for column in ("status", "ledger_entry_id", "entitlement_id", "schedule_id"):
        op.drop_index(f"ix_commission_payout_schedule_allocations_{column}", table_name="commission_payout_schedule_allocations")
    op.drop_table("commission_payout_schedule_allocations")
    op.drop_index("ix_commission_wallet_ledger_reason_code", table_name="commission_wallet_ledger")
    op.drop_index("ix_commission_wallet_ledger_schedule_id", table_name="commission_wallet_ledger")
    op.drop_index("ix_commission_wallet_ledger_entitlement_id", table_name="commission_wallet_ledger")
    op.drop_constraint("fk_wallet_schedule", "commission_wallet_ledger", type_="foreignkey")
    op.drop_constraint("fk_wallet_entitlement", "commission_wallet_ledger", type_="foreignkey")
    for column in ("approved_by", "created_by", "reason_code", "schedule_id", "entitlement_id"):
        op.drop_column("commission_wallet_ledger", column)
    for column in ("status", "payout_period", "employee_id", "sales_rep"):
        op.drop_index(f"ix_commission_payout_schedules_{column}", table_name="commission_payout_schedules")
    op.drop_table("commission_payout_schedules")
    for column in ("status", "source_period", "employee_id", "sales_rep", "job_id", "period_id", "snapshot_id"):
        op.drop_index(f"ix_commission_bonus_entitlements_{column}", table_name="commission_bonus_entitlements")
    op.drop_table("commission_bonus_entitlements")
    for column in ("employee_id", "sales_rep", "period_id"):
        op.drop_index(f"ix_commission_calculation_snapshots_{column}", table_name="commission_calculation_snapshots")
    op.drop_table("commission_calculation_snapshots")
