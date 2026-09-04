from datetime import date, datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_attendance_manager_user, get_attendance_employee_actor
from app.models.attendance_daily import AttendanceDaily
from app.models.attendance_log import AttendanceLog
from app.models.attendance_override_audit import AttendanceOverrideAudit
from app.models.off_request import OffRequest
from app.models.timesheet import Timesheet
from app.models.timesheet_entry import TimesheetEntry
from app.models.employee import Employee
from app.models.timesheet_period import TimesheetPeriod
from app.models.user import User
from app.models.upload_batch import UploadBatch
from app.services.final_timesheet_report import build_final_timesheet_report_from_db
from app.services.audit_service import record_audit
from app.services.notification_service import ATTENDANCE, add_employee_notifications

router = APIRouter(dependencies=[Depends(get_attendance_manager_user)])

class TimesheetSummary(BaseModel):
    timesheet_id: int
    employee_id: int
    full_name: str
    period_start: str
    period_end: str
    total_work_days: float
    total_payroll_days: float
    total_late_minutes: int
    total_absent_days: float
    total_paid_leave_days: float
    total_unpaid_leave_days: float
    total_business_trip_days: float
    approval_status: str


class TimesheetApprovalRequest(BaseModel):
    action: str


class TimesheetApprovalResponse(BaseModel):
    timesheet_id: int
    approval_status: str
    approved_by_user_id: int | None
    approved_at: str | None


class TimesheetGridRow(BaseModel):
    employee_id: int
    machine_employee_id: str
    full_name: str
    department_name: str | None
    days: dict[str, str]
    override_reasons: dict[str, str]
    abnormal_days: int
    total_late_minutes: int
    total_early_minutes: int
    total_absent_days: float
    total_work_days: float
    total_payroll_days: float
    unpaid_leave_days: float
    paid_leave_days: float
    previous_paid_leave_balance: float
    current_month_paid_leave_credit: float
    remaining_paid_leave_days: float


class TimesheetGridDayColumn(BaseModel):
    key: str
    day_number: int
    weekday_label: str
    is_weekend: bool


class TimesheetGridResponse(BaseModel):
    period_start: str
    period_end: str
    is_locked: bool
    day_keys: list[str]
    day_columns: list[TimesheetGridDayColumn]
    rows: list[TimesheetGridRow]

class TimesheetLockRequest(BaseModel):
    period_start: date
    period_end: date
    is_locked: bool


class LeavePolicyRow(BaseModel):
    employee_id: int
    machine_employee_id: str
    full_name: str
    paid_leave_days: float
    unpaid_leave_days: float
    annual_leave_quota: float
    annual_leave_used: float
    annual_leave_remaining: float


class ConflictAuditRow(BaseModel):
    employee_id: int
    work_date: str
    resolved_source: str
    final_symbol: str | None
    abnormal_level: str | None
    is_overridden: bool

@router.get("/api/timesheets", response_model=List[TimesheetSummary])
def get_timesheets(
    period_start: date = Query(...),
    period_end: date = Query(...),
    db: Session = Depends(get_db),
) -> list[TimesheetSummary]:
    try:
        rows = db.query(Timesheet, Employee).outerjoin(
            Employee, Timesheet.employee_id == Employee.id
        ).filter(
            Timesheet.period_start == period_start,
            Timesheet.period_end == period_end
        ).order_by(Timesheet.employee_id.asc()).all()

        results = []
        for t, emp in rows:
            results.append(TimesheetSummary(
                timesheet_id=t.id,
                employee_id=t.employee_id,
                full_name=emp.full_name if emp else "",
                period_start=str(t.period_start),
                period_end=str(t.period_end),
                total_work_days=float(t.total_work_days),
                total_payroll_days=(
                    float(t.total_payroll_days)
                    if t.total_payroll_days is not None
                    else float(t.total_work_days or 0) + float(t.total_paid_leave_days or 0)
                ),
                total_late_minutes=t.total_late_minutes,
                total_absent_days=float(t.total_absent_days),
                total_paid_leave_days=float(t.total_paid_leave_days),
                total_unpaid_leave_days=float(t.total_unpaid_leave_days),
                total_business_trip_days=float(t.total_business_trip_days),
                approval_status=t.approval_status
            ))
        return results
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="database is unavailable") from exc



@router.post("/api/timesheets/{timesheet_id}/approval", response_model=TimesheetApprovalResponse)
def approve_timesheet(
    timesheet_id: int,
    payload: TimesheetApprovalRequest,
    db: Session = Depends(get_db),
    actor: Employee = Depends(get_attendance_employee_actor),
) -> TimesheetApprovalResponse:
    timesheet = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not timesheet:
        raise HTTPException(status_code=404, detail="timesheet not found")

    action = payload.action.strip().lower()
    if action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="action must be approve or reject")

    timesheet.approval_status = "approved" if action == "approve" else "rejected"
    timesheet.approved_by_user_id = actor.id
    timesheet.approved_at = datetime.now(timezone.utc)
    audit_user = db.query(User).filter(User.id == actor.user_id).first() if actor.user_id else None
    if audit_user:
        record_audit(
            db,
            actor=audit_user,
            action="TIMESHEET_APPROVAL",
            resource_type="TIMESHEET",
            resource_id=timesheet.id,
            summary=f"{'Duyệt' if action == 'approve' else 'Từ chối'} bảng công #{timesheet.id}",
            before={"approval_status": "draft"},
            after={"approval_status": timesheet.approval_status},
        )
    db.commit()
    db.refresh(timesheet)

    return TimesheetApprovalResponse(
        timesheet_id=timesheet.id,
        approval_status=timesheet.approval_status,
        approved_by_user_id=timesheet.approved_by_user_id,
        approved_at=timesheet.approved_at.isoformat() if timesheet.approved_at else None,
    )


@router.get("/api/timesheets/grid", response_model=TimesheetGridResponse)
def get_timesheet_grid(
    period_start: date = Query(...),
    period_end: date = Query(...),
    db: Session = Depends(get_db),
) -> TimesheetGridResponse:
    if period_start > period_end:
        raise HTTPException(status_code=400, detail="period_start must be <= period_end")
    try:
        report = build_final_timesheet_report_from_db(db, period_start, period_end)
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="database is unavailable") from exc

    period = db.query(TimesheetPeriod).filter(
        TimesheetPeriod.period_start == period_start,
        TimesheetPeriod.period_end == period_end
    ).first()
    is_locked = period.is_locked if period else False

    return TimesheetGridResponse(
        period_start=report.period_start.isoformat(),
        period_end=report.period_end.isoformat(),
        is_locked=is_locked,
        day_keys=report.day_keys,
        day_columns=[
            TimesheetGridDayColumn(
                key=column.key,
                day_number=column.day_number,
                weekday_label=column.weekday_label,
                is_weekend=column.is_weekend,
            )
            for column in report.day_columns
        ],
        rows=[
            TimesheetGridRow(
                employee_id=row.employee_id,
                machine_employee_id=row.machine_employee_id,
                full_name=row.full_name,
                department_name=row.department_name,
                days=row.days,
                override_reasons=row.override_reasons,
                abnormal_days=row.abnormal_days,
                total_late_minutes=row.total_late_minutes,
                total_early_minutes=row.total_early_minutes,
                total_absent_days=row.total_absent_days,
                total_work_days=row.total_work_days,
                total_payroll_days=row.total_payroll_days,
                unpaid_leave_days=row.unpaid_leave_days,
                paid_leave_days=row.paid_leave_days,
                previous_paid_leave_balance=row.previous_paid_leave_balance,
                current_month_paid_leave_credit=row.current_month_paid_leave_credit,
                remaining_paid_leave_days=row.remaining_paid_leave_days,
            )
            for row in report.rows
        ],
    )


@router.post("/api/timesheets/lock-period")
def lock_timesheet_period(
    payload: TimesheetLockRequest,
    db: Session = Depends(get_db),
    admin: Employee = Depends(get_attendance_employee_actor)
):
    period = db.query(TimesheetPeriod).filter(
        TimesheetPeriod.period_start == payload.period_start,
        TimesheetPeriod.period_end == payload.period_end
    ).first()
    
    was_locked = bool(period and period.is_locked)
    if not period:
        period = TimesheetPeriod(
            period_start=payload.period_start,
            period_end=payload.period_end,
            is_locked=payload.is_locked,
            locked_by_user_id=admin.id,
            locked_at=datetime.now(timezone.utc)
        )
        db.add(period)
    else:
        period.is_locked = payload.is_locked
        period.locked_by_user_id = admin.id if payload.is_locked else None
        period.locked_at = datetime.now(timezone.utc) if payload.is_locked else None

    db.flush()

    if payload.is_locked:
        current_timesheets = (
            db.query(Timesheet)
            .filter(
                Timesheet.period_start == payload.period_start,
                Timesheet.period_end == payload.period_end,
            )
            .all()
        )
        for row in current_timesheets:
            row.previous_paid_leave_balance = None
            row.current_month_paid_leave_credit = None
            row.remaining_paid_leave_days = None
        db.flush()

        report = build_final_timesheet_report_from_db(db, payload.period_start, payload.period_end)
        report_by_employee = {row.employee_id: row for row in report.rows}
        for row in current_timesheets:
            report_row = report_by_employee.get(row.employee_id)
            if report_row is not None:
                row.previous_paid_leave_balance = report_row.previous_paid_leave_balance
                row.current_month_paid_leave_credit = report_row.current_month_paid_leave_credit
                row.remaining_paid_leave_days = report_row.remaining_paid_leave_days

    if payload.is_locked and not was_locked:
        employee_ids = [
            row[0]
            for row in db.query(Timesheet.employee_id)
            .filter(
                Timesheet.period_start == payload.period_start,
                Timesheet.period_end == payload.period_end,
            )
            .distinct()
            .all()
        ]
        notification_employees = (
            db.query(Employee)
            .filter(Employee.id.in_(employee_ids), Employee.user_id.isnot(None))
            .all()
            if employee_ids
            else []
        )
        add_employee_notifications(
            db,
            notification_employees,
            category=ATTENDANCE,
            event_type="TIMESHEET_PUBLISHED",
            title="Bảng công đã được xác nhận",
            message=f"Bảng công từ {payload.period_start.strftime('%d/%m/%Y')} đến {payload.period_end.strftime('%d/%m/%Y')} đã được khóa và phát hành.",
            actor_user_id=admin.user_id,
            resource_type="TIMESHEET_PERIOD",
            resource_id=f"{payload.period_start}:{payload.period_end}",
            action_url="/user/my-attendance",
        )
    db.commit()
    msg = "Đã khóa bảng công" if payload.is_locked else "Đã mở khóa bảng công"
    return {"ok": True, "message": msg}


@router.get("/api/timesheets/policy-summary", response_model=list[LeavePolicyRow])
def get_leave_policy_summary(
    period_start: date = Query(...),
    period_end: date = Query(...),
    db: Session = Depends(get_db),
) -> list[LeavePolicyRow]:
    employees = db.query(Employee).order_by(Employee.id.asc()).all()
    if not employees:
        return []

    # Pre-fetch all approved off requests for the given period for all employees in a single query
    emp_ids = [emp.id for emp in employees]
    all_off_requests = (
        db.query(OffRequest)
        .filter(
            OffRequest.employee_id.in_(emp_ids),
            OffRequest.status == "approved",
            OffRequest.start_date <= period_end,
            OffRequest.end_date >= period_start,
        )
        .all()
    )

    # Group requests by employee_id for instant O(1) lookup
    from collections import defaultdict
    requests_by_employee = defaultdict(list)
    for req in all_off_requests:
        requests_by_employee[req.employee_id].append(req)

    result: list[LeavePolicyRow] = []
    for emp in employees:
        off_requests = requests_by_employee[emp.id]

        paid_leave_days = 0.0
        unpaid_leave_days = 0.0
        for req in off_requests:
            request_type = (req.request_type or "").strip().lower()
            days = float(req.total_days or 0)
            if request_type in {"paid_leave", "paid", "p", "leave_request"}:
                paid_leave_days += days
            elif request_type in {"unpaid_leave", "unpaid", "v"}:
                unpaid_leave_days += days

        is_fulltime = str(emp.employee_type or "FULLTIME").upper() == "FULLTIME"
        if not is_fulltime:
            # Học việc/thử việc không có phép năm; mọi ngày nghỉ chỉ được
            # báo cáo là nghỉ không lương.
            unpaid_leave_days += paid_leave_days
            paid_leave_days = 0.0
        annual_quota = float(emp.annual_leave_quota) if is_fulltime else 0.0
        annual_used = (float(emp.annual_leave_used) + paid_leave_days) if is_fulltime else 0.0
        annual_remaining = annual_quota - annual_used

        result.append(
            LeavePolicyRow(
                employee_id=emp.id,
                machine_employee_id=emp.machine_employee_id,
                full_name=emp.full_name,
                paid_leave_days=paid_leave_days,
                unpaid_leave_days=unpaid_leave_days,
                annual_leave_quota=annual_quota,
                annual_leave_used=annual_used,
                annual_leave_remaining=annual_remaining,
            )
        )

    return result


@router.get("/api/timesheets/conflict-audit", response_model=list[ConflictAuditRow])
def get_conflict_audit(
    period_start: date = Query(...),
    period_end: date = Query(...),
    db: Session = Depends(get_db),
) -> list[ConflictAuditRow]:
    daily_rows = (
        db.query(AttendanceDaily)
        .filter(AttendanceDaily.period_start == period_start, AttendanceDaily.period_end == period_end)
        .order_by(AttendanceDaily.employee_id.asc(), AttendanceDaily.work_date.asc())
        .all()
    )

    entries = (
        db.query(TimesheetEntry)
        .filter(TimesheetEntry.work_date >= period_start, TimesheetEntry.work_date <= period_end)
        .order_by(TimesheetEntry.employee_id.asc(), TimesheetEntry.work_date.asc())
        .all()
    )
    entry_map = {(e.employee_id, e.work_date.isoformat()): e for e in entries}

    rows: list[ConflictAuditRow] = []
    for daily in daily_rows:
        key = (daily.employee_id, daily.work_date.isoformat())
        entry = entry_map.get(key)

        if entry and bool(entry.is_overridden):
            resolved_source = "override"
            final_symbol = entry.final_symbol
            is_overridden = True
        elif bool(daily.abnormal_level):
            resolved_source = "abnormal"
            final_symbol = daily.attendance_symbol
            is_overridden = False
        else:
            resolved_source = "checkin_profile"
            final_symbol = daily.attendance_symbol
            is_overridden = False

        rows.append(
            ConflictAuditRow(
                employee_id=daily.employee_id,
                work_date=daily.work_date.isoformat(),
                resolved_source=resolved_source,
                final_symbol=final_symbol,
                abnormal_level=daily.abnormal_level,
                is_overridden=is_overridden,
            )
        )
    return rows


@router.delete("/api/timesheets/period")
def delete_timesheet_period(
    period_start: date = Query(...),
    period_end: date = Query(...),
    db: Session = Depends(get_db),
    admin: Employee = Depends(get_attendance_employee_actor)
):
    from app.models.timesheet_period import TimesheetPeriod
    from app.models.monthly_salary_input import MonthlySalaryInput

    period = db.query(TimesheetPeriod).filter(
        TimesheetPeriod.period_start == period_start,
        TimesheetPeriod.period_end == period_end
    ).first()

    if period and period.is_locked:
        raise HTTPException(status_code=400, detail="Không thể xóa bảng công đã bị khóa.")

    # 1. Reset actual_working_days in MonthlySalaryInput
    salary_period = period_end.strftime("%Y-%m")
    db.query(MonthlySalaryInput).filter(
        MonthlySalaryInput.salary_period == salary_period
    ).update({"actual_working_days": 0.0}, synchronize_session=False)

    # Remove all generated data by work date. This also clears legacy rows
    # whose period metadata was not saved consistently.
    db.query(AttendanceOverrideAudit).filter(
        AttendanceOverrideAudit.work_date >= period_start,
        AttendanceOverrideAudit.work_date <= period_end,
    ).delete(synchronize_session=False)

    db.query(TimesheetEntry).filter(
        TimesheetEntry.work_date >= period_start,
        TimesheetEntry.work_date <= period_end,
    ).delete(synchronize_session=False)

    db.query(AttendanceDaily).filter(
        AttendanceDaily.work_date >= period_start,
        AttendanceDaily.work_date <= period_end,
    ).delete(synchronize_session=False)

    db.query(AttendanceLog).filter(
        AttendanceLog.work_date >= period_start,
        AttendanceLog.work_date <= period_end,
    ).delete(synchronize_session=False)

    db.query(UploadBatch).filter(
        UploadBatch.source_type == "checkin_profile",
        UploadBatch.period_start == period_start,
        UploadBatch.period_end == period_end,
    ).delete(synchronize_session=False)

    if period:
        db.delete(period)

    # 2. Delete TimesheetEntry
    ts_ids_subquery = db.query(Timesheet.id).filter(
        Timesheet.period_start == period_start,
        Timesheet.period_end == period_end
    ).scalar_subquery()
    
    db.query(TimesheetEntry).filter(
        TimesheetEntry.timesheet_id.in_(ts_ids_subquery)
    ).delete(synchronize_session=False)

    # 3. Delete Timesheet
    db.query(Timesheet).filter(
        Timesheet.period_start == period_start,
        Timesheet.period_end == period_end
    ).delete(synchronize_session=False)

    # 4. Delete AttendanceDaily
    db.query(AttendanceDaily).filter(
        AttendanceDaily.period_start == period_start,
        AttendanceDaily.period_end == period_end
    ).delete(synchronize_session=False)

    db.commit()

    return {"message": f"Đã xóa thành công dữ liệu bảng công kỳ {period_start} đến {period_end}."}
