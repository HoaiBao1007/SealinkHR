"""Backfill notifications for pending employee bonus payout requests.

Revision ID: 20260803_0014
Revises: 20260803_0013
Create Date: 2026-08-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260803_0014"
down_revision: Union[str, None] = "20260803_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PAYMENT_HOLD_TYPES = {
    "ACCRUAL_HELD",
    "ADJUSTMENT_HELD",
    "REVERSAL_HELD",
    "PAYMENT_STATUS_HOLD",
}


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    verifications = sa.Table("commission_payment_verifications", metadata, autoload_with=bind)
    jobs = sa.Table("commission_jobs", metadata, autoload_with=bind)
    periods = sa.Table("commission_periods", metadata, autoload_with=bind)
    ledger = sa.Table("commission_wallet_ledger", metadata, autoload_with=bind)
    users = sa.Table("users", metadata, autoload_with=bind)
    notifications = sa.Table("notifications", metadata, autoload_with=bind)

    pending_rows = bind.execute(
        sa.select(
            verifications.c.job_id,
            verifications.c.sales_rep,
            verifications.c.reported_by,
            verifications.c.reported_at,
            jobs.c.job_no,
            jobs.c.period_id,
            periods.c.period_label,
        )
        .join(jobs, jobs.c.id == verifications.c.job_id)
        .join(periods, periods.c.id == jobs.c.period_id)
        .where(verifications.c.status == "PENDING")
    ).mappings().all()

    for row in pending_rows:
        exists = bind.execute(
            sa.select(notifications.c.id).where(
                notifications.c.event_type == "BONUS_PAYOUT_REQUESTED",
                notifications.c.resource_type == "COMMISSION_JOB",
                notifications.c.resource_id == str(row["job_id"]),
            )
        ).first()
        if exists:
            continue

        payment_held = 0.0
        released = 0.0
        for entry in bind.execute(
            sa.select(ledger.c.entry_type, ledger.c.amount).where(ledger.c.job_id == row["job_id"])
        ).mappings():
            amount = float(entry["amount"] or 0.0)
            if entry["entry_type"] in PAYMENT_HOLD_TYPES:
                payment_held += amount
            elif entry["entry_type"] == "RELEASED":
                released += amount
        held_amount = max(0.0, round(payment_held - released, 2))

        actor_user_id = bind.execute(
            sa.select(users.c.id).where(users.c.username == row["reported_by"])
        ).scalar_one_or_none()
        bind.execute(
            notifications.insert().values(
                category="BONUS",
                event_type="BONUS_PAYOUT_REQUESTED",
                title=f"Yêu cầu duyệt chi trả bonus JOB {row['job_no']}",
                message=(
                    f"{row['sales_rep']} đã yêu cầu kế toán kiểm tra và duyệt chi trả "
                    f"{held_amount:,.0f} VND đang giữ của JOB {row['job_no']}, "
                    f"kỳ nguồn {row['period_label']}."
                ),
                target_user_id=None,
                actor_user_id=actor_user_id,
                resource_type="COMMISSION_JOB",
                resource_id=str(row["job_id"]),
                action_url="/admin/salary-matrix",
                created_at=row["reported_at"],
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    notifications = sa.Table("notifications", metadata, autoload_with=bind)
    bind.execute(
        notifications.delete().where(notifications.c.event_type == "BONUS_PAYOUT_REQUESTED")
    )
