"""Add commission bonus lock and per-JOB held payout plan.

Revision ID: 20260727_0006
Revises: 20260722_0005
"""
from alembic import op
import sqlalchemy as sa


revision = "20260727_0006"
down_revision = "20260722_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("commission_jobs", sa.Column("held_release_mode", sa.String(length=32), nullable=True))
    op.add_column("commission_jobs", sa.Column("held_release_payout_period", sa.String(length=7), nullable=True))
    op.create_table(
        "commission_bonus_locks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("commission_periods.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sales_rep", sa.String(length=150), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("period_id", "sales_rep", name="uq_commission_bonus_lock_period_rep"),
    )
    op.create_index("ix_commission_bonus_locks_period_id", "commission_bonus_locks", ["period_id"])
    op.create_index("ix_commission_bonus_locks_sales_rep", "commission_bonus_locks", ["sales_rep"])


def downgrade() -> None:
    op.drop_index("ix_commission_bonus_locks_sales_rep", table_name="commission_bonus_locks")
    op.drop_index("ix_commission_bonus_locks_period_id", table_name="commission_bonus_locks")
    op.drop_table("commission_bonus_locks")
    op.drop_column("commission_jobs", "held_release_payout_period")
    op.drop_column("commission_jobs", "held_release_mode")
