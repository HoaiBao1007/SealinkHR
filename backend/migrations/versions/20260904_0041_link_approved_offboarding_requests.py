"""Link and finalize previously approved offboarding requests.

Revision ID: 20260904_0041
Revises: 20260904_0040
Create Date: 2026-09-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260904_0041"
down_revision: Union[str, None] = "20260904_0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _unique_match(connection, employees, condition) -> int | None:
    ids = connection.execute(sa.select(employees.c.id).where(condition).limit(2)).scalars().all()
    return int(ids[0]) if len(ids) == 1 else None


def upgrade() -> None:
    employees = sa.table(
        "employees",
        sa.column("id", sa.Integer()),
        sa.column("machine_employee_id", sa.String()),
        sa.column("employee_code", sa.String()),
        sa.column("full_name", sa.String()),
        sa.column("personal_email", sa.String()),
        sa.column("company_email", sa.String()),
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
        sa.column("employee_name_snapshot", sa.String()),
        sa.column("employee_code_snapshot", sa.String()),
        sa.column("email_snapshot", sa.String()),
        sa.column("status", sa.String()),
        sa.column("confirmed_last_working_date", sa.Date()),
        sa.column("desired_last_working_date", sa.Date()),
        sa.column("last_pay_date", sa.Date()),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(requests).where(
            requests.c.status == "APPROVED",
            requests.c.employee_id.is_(None),
        ).order_by(requests.c.id.asc())
    ).mappings()

    for row in rows:
        employee_id = None
        code = (row["employee_code_snapshot"] or "").strip()
        if code:
            employee_id = _unique_match(
                connection,
                employees,
                sa.or_(employees.c.machine_employee_id == code, employees.c.employee_code == code),
            )
        email = (row["email_snapshot"] or "").strip().lower()
        if employee_id is None and email:
            employee_id = _unique_match(
                connection,
                employees,
                sa.or_(
                    sa.func.lower(employees.c.personal_email) == email,
                    sa.func.lower(employees.c.company_email) == email,
                ),
            )
        name = (row["employee_name_snapshot"] or "").strip().lower()
        if employee_id is None and name:
            employee_id = _unique_match(
                connection,
                employees,
                sa.func.lower(employees.c.full_name) == name,
            )
        final_day = row["confirmed_last_working_date"] or row["desired_last_working_date"]
        if employee_id is None or final_day is None:
            continue
        connection.execute(
            requests.update().where(requests.c.id == row["id"]).values(employee_id=employee_id)
        )
        connection.execute(
            employees.update().where(employees.c.id == employee_id).values(
                is_active=False,
                status="RESIGNED",
                resignation_period=final_day.strftime("%Y-%m"),
                last_working_date=final_day,
                last_pay_date=row["last_pay_date"],
            )
        )


def downgrade() -> None:
    # The linkage is valid business data and remains intact on downgrade.
    pass
