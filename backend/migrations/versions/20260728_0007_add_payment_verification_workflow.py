"""Add accounting verification and JOB payment-command workflow.

Revision ID: 20260728_0007
Revises: 20260727_0006
"""
from alembic import op
import sqlalchemy as sa


revision = "20260728_0007"
down_revision = "20260727_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commission_payment_verifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("commission_periods.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("commission_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sales_rep", sa.String(length=150), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="PENDING"),
        sa.Column("report_note", sa.Text(), nullable=True),
        sa.Column("verification_note", sa.Text(), nullable=True),
        sa.Column("reported_by", sa.String(length=100), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("verified_by", sa.String(length=100), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("command_created_by", sa.String(length=100), nullable=True),
        sa.Column("command_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("job_id", name="uq_commission_payment_verification_job"),
    )
    op.create_index("ix_commission_payment_verifications_period_id", "commission_payment_verifications", ["period_id"])
    op.create_index("ix_commission_payment_verifications_sales_rep", "commission_payment_verifications", ["sales_rep"])
    op.create_index("ix_commission_payment_verifications_status", "commission_payment_verifications", ["status"])
    op.add_column("commission_payout_schedules", sa.Column("payment_verification_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_commission_payout_schedules_payment_verification", "commission_payout_schedules", "commission_payment_verifications", ["payment_verification_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_commission_payout_schedules_payment_verification_id", "commission_payout_schedules", ["payment_verification_id"])


def downgrade() -> None:
    op.drop_index("ix_commission_payout_schedules_payment_verification_id", table_name="commission_payout_schedules")
    op.drop_constraint("fk_commission_payout_schedules_payment_verification", "commission_payout_schedules", type_="foreignkey")
    op.drop_column("commission_payout_schedules", "payment_verification_id")
    op.drop_index("ix_commission_payment_verifications_status", table_name="commission_payment_verifications")
    op.drop_index("ix_commission_payment_verifications_sales_rep", table_name="commission_payment_verifications")
    op.drop_index("ix_commission_payment_verifications_period_id", table_name="commission_payment_verifications")
    op.drop_table("commission_payment_verifications")
