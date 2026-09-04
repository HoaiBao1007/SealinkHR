"""Finalize employee status when an offboarding request is approved.

Revision ID: 20260904_0040
Revises: 20260828_0039
Create Date: 2026-09-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260904_0040"
down_revision: Union[str, None] = "20260828_0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("last_working_date", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("last_pay_date", sa.Date(), nullable=True))

    employees = sa.table(
        "employees",
        sa.column("id", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
        sa.column("status", sa.String()),
        sa.column("resignation_period", sa.String()),
        sa.column("last_working_date", sa.Date()),
        sa.column("last_pay_date", sa.Date()),
    )
    requests = sa.table(
        "offboarding_requests",
        sa.column("id", sa.Integer()),
        sa.column("employee_id", sa.Integer()),
        sa.column("status", sa.String()),
        sa.column("confirmed_last_working_date", sa.Date()),
        sa.column("desired_last_working_date", sa.Date()),
        sa.column("last_pay_date", sa.Date()),
    )
    connection = op.get_bind()
    approved_rows = connection.execute(
        sa.select(
            requests.c.employee_id,
            requests.c.confirmed_last_working_date,
            requests.c.desired_last_working_date,
            requests.c.last_pay_date,
        )
        .where(
            requests.c.employee_id.is_not(None),
            requests.c.status == "APPROVED",
        )
        .order_by(requests.c.id.desc())
    ).mappings()
    updated_employee_ids: set[int] = set()
    for row in approved_rows:
        employee_id = int(row["employee_id"])
        if employee_id in updated_employee_ids:
            continue
        final_day = row["confirmed_last_working_date"] or row["desired_last_working_date"]
        if final_day is None:
            continue
        connection.execute(
            employees.update()
            .where(employees.c.id == employee_id)
            .values(
                is_active=False,
                status="RESIGNED",
                resignation_period=final_day.strftime("%Y-%m"),
                last_working_date=final_day,
                last_pay_date=row["last_pay_date"],
            )
        )
        updated_employee_ids.add(employee_id)


def downgrade() -> None:
    op.drop_column("employees", "last_pay_date")
    op.drop_column("employees", "last_working_date")
