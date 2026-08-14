from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, aliased

from app.api.deps import get_db, get_attendance_manager_user, get_attendance_employee_actor
from app.models.attendance_daily import AttendanceDaily
from app.models.attendance_override_audit import AttendanceOverrideAudit
from app.models.employee import Employee
from app.models.timesheet_entry import TimesheetEntry
from app.models.timesheet_period import TimesheetPeriod
from app.models.user import User
from app.api.importer import resolve_period_for_work_date
from app.services.audit_service import record_audit
from app.services.attendance_audit_sync import attendance_override_summary
from app.services.trusted_device_service import request_device, request_source_ip

router = APIRouter(tags=["override"], dependencies=[Depends(get_attendance_manager_user)])


class OverrideRequest(BaseModel):
    employee_id: int
    work_date: date
    new_symbol: str = Field(min_length=1, max_length=10)
    reason: str = Field(min_length=3)
    new_check_in: Optional[str] = None
    new_check_out: Optional[str] = None
    override_lock: Optional[bool] = False


class OverrideResponse(BaseModel):
    employee_id: int
    work_date: str
    old_symbol: str
    new_symbol: str
    reason: str
    changed_by_user_id: int


class OverrideAuditRow(BaseModel):
    audit_id: int
    employee_id: int
    employee_name: str
    work_date: str
    old_symbol: str
    new_symbol: str
    old_check_in: str | None
    new_check_in: str | None
    old_check_out: str | None
    new_check_out: str | None
    reason: str
    changed_by_user_id: int
    changed_by_name: str
    changed_at: str
    source_ip: str | None
    device_address: str | None


@router.post("/api/attendance/override", response_model=OverrideResponse)
def override_attendance(
    payload: OverrideRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: Employee = Depends(get_attendance_employee_actor),
) -> OverrideResponse:

    p_start, p_end = resolve_period_for_work_date(payload.work_date)
    period = db.query(TimesheetPeriod).filter(
        TimesheetPeriod.period_start == p_start,
        TimesheetPeriod.period_end == p_end
    ).first()
    
    if period and period.is_locked and not payload.override_lock:
        raise HTTPException(status_code=403, detail="Bảng công đã chốt, không thể chỉnh sửa nếu không xác nhận ghi đè.")

    entry = (
        db.query(TimesheetEntry)
        .filter(
            TimesheetEntry.employee_id == payload.employee_id,
            TimesheetEntry.work_date == payload.work_date,
        )
        .order_by(TimesheetEntry.id.desc())
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="timesheet entry not found for employee/work_date")

    old_symbol = entry.final_symbol
    old_check_in = entry.check_in_time
    old_check_out = entry.check_out_time

    entry.final_symbol = payload.new_symbol.strip()
    entry.is_overridden = True
    entry.override_reason = payload.reason.strip()
    entry.overridden_by_user_id = actor.id
    entry.overridden_at = datetime.now(timezone.utc)
    if payload.new_check_in is not None:
        entry.check_in_time = payload.new_check_in
    if payload.new_check_out is not None:
        entry.check_out_time = payload.new_check_out

    daily = (
        db.query(AttendanceDaily)
        .filter(
            AttendanceDaily.employee_id == payload.employee_id,
            AttendanceDaily.work_date == payload.work_date,
        )
        .first()
    )
    if daily:
        daily.attendance_symbol = payload.new_symbol.strip()
        if payload.new_check_in is not None:
            daily.check_in_time = payload.new_check_in
        if payload.new_check_out is not None:
            daily.check_out_time = payload.new_check_out

    source_ip = request_source_ip(request)
    audit_user = db.query(User).filter(User.id == actor.user_id).first() if actor.user_id else None
    trusted_device = request_device(db, request, user_id=audit_user.id) if audit_user else None
    audit = AttendanceOverrideAudit(
        employee_id=payload.employee_id,
        work_date=payload.work_date,
        old_symbol=old_symbol,
        new_symbol=payload.new_symbol.strip(),
        old_check_in=old_check_in,
        new_check_in=payload.new_check_in if payload.new_check_in is not None else old_check_in,
        old_check_out=old_check_out,
        new_check_out=payload.new_check_out if payload.new_check_out is not None else old_check_out,
        reason=payload.reason.strip(),
        changed_by_user_id=actor.id,
        source_ip=source_ip,
        device_address=trusted_device.device_label if trusted_device else None,
    )
    db.add(audit)
    # Allocate the immutable override-ledger ID before writing the matching
    # system-wide audit event.  IT can now trace both views by this ID.
    db.flush()
    if audit_user:
        record_audit(
            db,
            actor=audit_user,
            action="ATTENDANCE_OVERRIDE",
            resource_type="ATTENDANCE_OVERRIDE",
            resource_id=audit.id,
            summary=attendance_override_summary(audit),
            before={"symbol": old_symbol, "check_in": old_check_in, "check_out": old_check_out},
            after={
                "symbol": entry.final_symbol,
                "check_in": entry.check_in_time,
                "check_out": entry.check_out_time,
                "reason": entry.override_reason,
                "override_audit_id": audit.id,
            },
            source_ip=source_ip,
            device_address=trusted_device.device_label if trusted_device else None,
        )
    db.commit()

    return OverrideResponse(
        employee_id=payload.employee_id,
        work_date=payload.work_date.isoformat(),
        old_symbol=old_symbol,
        new_symbol=payload.new_symbol.strip(),
        reason=payload.reason.strip(),
        changed_by_user_id=actor.id,
    )


@router.get("/api/attendance/override/history", response_model=list[OverrideAuditRow])
def get_override_history(
    period_start: date = Query(...),
    period_end: date = Query(...),
    employee_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[OverrideAuditRow]:
    if period_start > period_end:
        raise HTTPException(status_code=400, detail="period_start must be <= period_end")

    employee_alias = aliased(Employee)
    changer_alias = aliased(Employee)

    try:
        query = (
            db.query(AttendanceOverrideAudit, employee_alias.full_name, changer_alias.full_name)
            .outerjoin(employee_alias, employee_alias.id == AttendanceOverrideAudit.employee_id)
            .outerjoin(changer_alias, changer_alias.id == AttendanceOverrideAudit.changed_by_user_id)
            .filter(
                AttendanceOverrideAudit.work_date >= period_start,
                AttendanceOverrideAudit.work_date <= period_end,
            )
        )
        if employee_id is not None:
            query = query.filter(AttendanceOverrideAudit.employee_id == employee_id)

        rows = (
            query.order_by(AttendanceOverrideAudit.changed_at.desc(), AttendanceOverrideAudit.id.desc())
            .limit(limit)
            .all()
        )
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="database is unavailable") from exc

    result: list[OverrideAuditRow] = []
    for audit, employee_name, changer_name in rows:
        changed_at = audit.changed_at.isoformat() if audit.changed_at else datetime.now(timezone.utc).isoformat()
        result.append(
            OverrideAuditRow(
                audit_id=audit.id,
                employee_id=audit.employee_id,
                employee_name=employee_name or f"Nhân sự #{audit.employee_id}",
                work_date=audit.work_date.isoformat(),
                old_symbol=audit.old_symbol,
                new_symbol=audit.new_symbol,
                old_check_in=audit.old_check_in,
                new_check_in=audit.new_check_in,
                old_check_out=audit.old_check_out,
                new_check_out=audit.new_check_out,
                reason=audit.reason,
                changed_by_user_id=audit.changed_by_user_id,
                changed_by_name=changer_name or f"Tài khoản audit #{audit.changed_by_user_id}",
                changed_at=changed_at,
                source_ip=audit.source_ip,
                device_address=audit.device_address,
            )
        )

    return result
