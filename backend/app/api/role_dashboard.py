from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_hr_manager_user, get_personal_portal_user
from app.models.attendance_daily import AttendanceDaily
from app.models.employee import Employee
from app.models.monthly_salary_input import MonthlySalaryInput
from app.models.timesheet import Timesheet
from app.models.user import User


router = APIRouter(prefix="/api/role-dashboard", tags=["role-dashboard"])


@router.get("/hr")
def hr_dashboard(
    period_start: date | None = Query(default=None),
    period_end: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _actor: User = Depends(get_hr_manager_user),
):
    employee_total = db.query(func.count(Employee.id)).scalar() or 0
    active_total = db.query(func.count(Employee.id)).filter(Employee.is_active.is_(True)).scalar() or 0
    unassigned_total = (
        db.query(func.count(Employee.id))
        .filter(Employee.is_active.is_(True), Employee.department_id.is_(None))
        .scalar()
        or 0
    )
    timesheet_query = db.query(Timesheet)
    attendance_query = db.query(AttendanceDaily)
    if period_start and period_end:
        timesheet_query = timesheet_query.filter(
            Timesheet.period_start == period_start,
            Timesheet.period_end == period_end,
        )
        attendance_query = attendance_query.filter(
            AttendanceDaily.period_start == period_start,
            AttendanceDaily.period_end == period_end,
        )
    timesheets = timesheet_query.all()
    daily_rows = attendance_query.all()
    return {
        "employees": {
            "total": employee_total,
            "active": active_total,
            "inactive": max(0, employee_total - active_total),
            "without_department": unassigned_total,
        },
        "attendance": {
            "timesheets": len(timesheets),
            "draft": sum(row.approval_status == "draft" for row in timesheets),
            "approved": sum(row.approval_status == "approved" for row in timesheets),
            "abnormal_days": sum(
                bool(row.abnormal_level) or int(row.late_minutes or 0) > 0 or int(row.early_minutes or 0) > 0
                for row in daily_rows
            ),
            "late_minutes": sum(int(row.late_minutes or 0) for row in daily_rows),
        },
    }


@router.get("/personal")
def personal_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_personal_portal_user),
):
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return {
            "linked": False,
            "message": "Tài khoản chưa liên kết hồ sơ nhân viên.",
        }
    published_periods = [
        period
        for (period,) in (
            db.query(MonthlySalaryInput.salary_period)
            .filter(
                MonthlySalaryInput.employee_id == employee.id,
                MonthlySalaryInput.is_published.is_(True),
            )
            .order_by(MonthlySalaryInput.salary_period.desc())
            .all()
        )
    ]
    latest_timesheet = (
        db.query(Timesheet)
        .filter(Timesheet.employee_id == employee.id)
        .order_by(Timesheet.period_end.desc())
        .first()
    )
    return {
        "linked": True,
        "employee": {
            "id": employee.id,
            "full_name": employee.full_name,
            "employee_code": employee.employee_code,
            "department_name": employee.department_name,
            "position": employee.position,
        },
        "published_payslip_count": len(published_periods),
        "latest_payslip_period": published_periods[0] if published_periods else None,
        "latest_attendance": (
            {
                "period_start": latest_timesheet.period_start.isoformat(),
                "period_end": latest_timesheet.period_end.isoformat(),
                "work_days": float(latest_timesheet.total_work_days or 0),
                "late_minutes": int(latest_timesheet.total_late_minutes or 0),
                "absent_days": float(latest_timesheet.total_absent_days or 0),
                "approval_status": latest_timesheet.approval_status,
            }
            if latest_timesheet
            else None
        ),
    }
