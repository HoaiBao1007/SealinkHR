from __future__ import annotations

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.timesheet import Timesheet


INACTIVE_EMPLOYEE_STATUSES = {"RESIGNED", "INACTIVE"}


def is_current_employee(employee: Employee) -> bool:
    """Return whether an employee belongs in current organization views."""

    status = str(employee.status or "").strip().upper()
    return bool(employee.is_active) and status not in INACTIVE_EMPLOYEE_STATUSES


def salary_period_bounds(period: str) -> tuple[date, date]:
    """Map a payroll month to the company's 23 -> 22 attendance cycle."""

    year, month = map(int, period.split("-"))
    previous_year, previous_month = (year - 1, 12) if month == 1 else (year, month - 1)
    return date(previous_year, previous_month, 23), date(year, month, 22)


def salary_period_working_employee_ids(db: Session, period: str) -> set[int]:
    """Employees with payable attendance in the exact payroll cycle.

    A persisted monthly salary row is deliberately not evidence of attendance:
    legacy/default rows can contain 22 days even when no timesheet was imported.
    """

    period_start, period_end = salary_period_bounds(period)
    payable_days = (
        func.coalesce(Timesheet.total_work_days, 0)
        + func.coalesce(Timesheet.total_paid_leave_days, 0)
        + func.coalesce(Timesheet.total_business_trip_days, 0)
    )
    rows = (
        db.query(Timesheet.employee_id)
        .filter(
            Timesheet.period_start == period_start,
            Timesheet.period_end == period_end,
            payable_days > 0,
        )
        .all()
    )
    return {int(employee_id) for (employee_id,) in rows}


def salary_period_payable_days(db: Session, employee_id: int, period: str) -> float:
    """Return accountant-approved payable days for the attendance cycle.

    New periods store the workbook's ``Ngày công`` verbatim. The derived
    actual-work-plus-paid-leave value is only a compatibility fallback for
    legacy periods created before that dedicated field existed.
    """

    period_start, period_end = salary_period_bounds(period)
    timesheet = (
        db.query(Timesheet)
        .filter(
            Timesheet.employee_id == employee_id,
            Timesheet.period_start == period_start,
            Timesheet.period_end == period_end,
            Timesheet.approval_status == "approved",
        )
        .first()
    )
    if timesheet is None:
        return 0.0
    if timesheet.total_payroll_days is not None:
        return float(timesheet.total_payroll_days)
    return float(timesheet.total_work_days or 0) + float(timesheet.total_paid_leave_days or 0)


def should_include_employee_in_salary_period(
    employee: Employee,
    period: str,
    working_employee_ids: set[int],
) -> bool:
    """Keep current staff, plus departed staff who worked in this payroll cycle."""

    period_start, period_end = salary_period_bounds(period)
    if employee.start_date and employee.start_date > period_end:
        return False

    # An old/default timesheet row must never bring a resigned employee back
    # into a payroll cycle that starts after their final working day.
    if employee.last_working_date and period_start > employee.last_working_date:
        return False

    if is_current_employee(employee):
        return True

    # Preserve earlier history when HR recorded a later resignation month.
    if employee.resignation_period and period < employee.resignation_period:
        return True

    return employee.id in working_employee_ids
