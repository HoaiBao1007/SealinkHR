from datetime import date, datetime, timezone, timedelta
from hashlib import sha256
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_attendance_manager_user
from app.models.attendance_log import AttendanceLog
from app.models.employee import Employee
from app.models.user import User
from app.models.upload_batch import UploadBatch
from app.models.attendance_daily import AttendanceDaily
from app.models.timesheet import Timesheet
from app.models.timesheet_entry import TimesheetEntry
from app.models.monthly_salary_input import MonthlySalaryInput
from app.api.importer import resolve_period_for_work_date
from app.services.final_timesheet_report import (
    _clocked_work_units_for_symbol,
    _work_units_for_symbol,
    _paid_leave_units_for_symbol,
    _absent_units_for_symbol,
)
from app.core.roles import BUSINESS_ADMIN_ROLES
from app.services.audit_service import record_audit

router = APIRouter(dependencies=[Depends(get_attendance_manager_user)])


def clean_machine_id(val: str | None) -> str:
    if not val:
        return ""
    val_str = str(val).strip()
    val_str = re.sub(r"^[#＃]+\s*", "", val_str)
    if val_str.endswith(".0"):
        val_str = val_str[:-2]
    return val_str



class CheckinCommitItem(BaseModel):
    machine_employee_id: str
    work_date: Optional[date] = None
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    raw_times: str
    department: Optional[str] = None
    error: Optional[str] = None
    attendance_symbol: Optional[str] = None

    @field_validator("work_date", "period_start", "period_end", mode="before")
    @classmethod
    def parse_flexible_date(cls, v):
        if not v:
            return None
        if isinstance(v, (date, datetime)):
            return v
        v_str = str(v).strip()
        if " " in v_str:
            v_str = v_str.split(" ")[0]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(v_str, fmt).date()
            except Exception:
                continue
        return None


class CheckinCommitRequest(BaseModel):
    file_name: str
    period_start: date
    period_end: date
    items: list[CheckinCommitItem]

    @field_validator("period_start", "period_end", mode="before")
    @classmethod
    def parse_flexible_date(cls, v):
        if not v:
            return None
        if isinstance(v, (date, datetime)):
            return v
        v_str = str(v).strip()
        if " " in v_str:
            v_str = v_str.split(" ")[0]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(v_str, fmt).date()
            except Exception:
                continue
        return v


def calculate_late_early(check_in: str | None, check_out: str | None) -> tuple[int, int]:
    late = 0
    early = 0
    if check_in:
        try:
            h, m = map(int, check_in.split(":"))
            in_mins = h * 60 + m
            start_mins = 8 * 60 + 30  # 08:30
            if in_mins > start_mins:
                late = in_mins - start_mins
        except Exception:
            pass
    if check_out:
        try:
            h, m = map(int, check_out.split(":"))
            out_mins = h * 60 + m
            end_mins = 17 * 60 + 30  # 17:30
            if out_mins < end_mins:
                early = end_mins - out_mins
        except Exception:
            pass
    return late, early


def extract_punch_times(item: CheckinCommitItem) -> list[str]:
    values = [item.raw_times or "", item.check_in or "", item.check_out or ""]
    return sorted({
        match.group(0)
        for value in values
        for match in re.finditer(r"(?:[01]?\d|2[0-3]):[0-5]\d", value)
    })


@router.post("/api/import/checkin-profile/commit")
def commit_checkin_profile(
    data: CheckinCommitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_attendance_manager_user),
):

    digest_seed = f"{data.file_name}|{data.period_start.isoformat()}|{data.period_end.isoformat()}|{datetime.now(timezone.utc).isoformat()}"
    file_hash = sha256(digest_seed.encode("utf-8")).hexdigest()

    batch = UploadBatch(
        uploaded_by_user_id=current_user.id,
        source_type="checkin_profile",
        file_name=data.file_name,
        file_hash=file_hash,
        period_start=data.period_start,
        period_end=data.period_end,
        status="processing",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    inserted = 0
    skipped: list[dict[str, str]] = []
    affected_timesheets = set()

    # Resolve the single authoritative machine ID, then merge duplicate rows
    # belonging to the same employee/day within the imported file.
    grouped_items: dict[tuple[int, date], dict] = {}
    for item in data.items:
        if not item.work_date:
            skipped.append({
                "machine_employee_id": item.machine_employee_id,
                "cleaned_id": clean_machine_id(item.machine_employee_id),
                "work_date": "Invalid Date",
                "reason": "invalid_work_date",
            })
            continue

        cleaned_id = clean_machine_id(item.machine_employee_id)
        emp = db.query(Employee).filter(Employee.machine_employee_id == cleaned_id).first()
        if not emp:
            skipped.append(
                {
                    "machine_employee_id": item.machine_employee_id,
                    "cleaned_id": cleaned_id,
                    "work_date": item.work_date.isoformat(),
                    "reason": "employee_not_found",
                }
            )
            continue

        key = (emp.id, item.work_date)
        group = grouped_items.setdefault(key, {"employee": emp, "items": [], "punches": set()})
        group["items"].append(item)
        group["punches"].update(extract_punch_times(item))

    for (employee_id, work_date), group in grouped_items.items():
        emp = group["employee"]
        source_items: list[CheckinCommitItem] = group["items"]
        punches = sorted(group["punches"])
        check_in = punches[0] if punches else None
        check_out = punches[-1] if len(punches) > 1 else None
        raw_times = ", ".join(punches)
        requested_symbol = next((item.attendance_symbol for item in reversed(source_items) if item.attendance_symbol), None)
        error = None if len(punches) > 1 else ("missing_checkout" if punches else "missing_all")

        log = AttendanceLog(
            upload_batch_id=batch.id,
            employee_id=emp.id,
            work_date=work_date,
            raw_time_values=raw_times,
            first_check_in=check_in,
            last_check_out=check_out,
            note=error,
            missing_flag=bool(error),
        )
        db.add(log)
        inserted += 1

        p_start, p_end = resolve_period_for_work_date(work_date)
        affected_timesheets.add((emp.id, p_start, p_end))

        late_mins, early_mins = calculate_late_early(check_in, check_out)
        if work_date.weekday() >= 5:
            symbol = ""
        elif requested_symbol:
            symbol = requested_symbol
        else:
            if check_in or check_out:
                symbol = "X"
            else:
                symbol = "Ro"

        abnormal = None
        if error or (bool(check_in) != bool(check_out)):
            abnormal = "L1"

        daily = db.query(AttendanceDaily).filter(
            AttendanceDaily.employee_id == emp.id,
            AttendanceDaily.work_date == work_date
        ).first()

        if not daily:
            daily = AttendanceDaily(
                employee_id=emp.id,
                work_date=work_date,
                period_start=p_start,
                period_end=p_end,
                check_in_time=check_in,
                check_out_time=check_out,
                late_minutes=late_mins,
                early_minutes=early_mins,
                attendance_symbol=symbol,
                abnormal_level=abnormal,
                source_priority=1,
                generated_from_batch_id=batch.id
            )
            db.add(daily)
        else:
            merged_punches = sorted({
                value
                for value in [daily.check_in_time, daily.check_out_time, check_in, check_out]
                if value
            })
            daily.check_in_time = merged_punches[0] if merged_punches else None
            daily.check_out_time = merged_punches[-1] if len(merged_punches) > 1 else None
            late_mins, early_mins = calculate_late_early(daily.check_in_time, daily.check_out_time)
            symbol = "" if work_date.weekday() >= 5 else (requested_symbol or ("X" if merged_punches else "Ro"))
            abnormal = "L1" if len(merged_punches) == 1 else None
            daily.late_minutes = late_mins
            daily.early_minutes = early_mins
            daily.attendance_symbol = symbol
            daily.abnormal_level = abnormal
            daily.generated_from_batch_id = batch.id
            daily.period_start = p_start
            daily.period_end = p_end

    db.commit()

    timesheet_errors: list[str] = []
    for employee_id, p_start, p_end in affected_timesheets:
        try:
            employee = db.get(Employee, employee_id)
            ts = db.query(Timesheet).filter(
                Timesheet.employee_id == employee_id,
                Timesheet.period_start == p_start,
                Timesheet.period_end == p_end
            ).first()

            if not ts:
                ts = Timesheet(
                    employee_id=employee_id,
                    period_start=p_start,
                    period_end=p_end,
                    approval_status="draft"
                )
                db.add(ts)
                db.commit()
                db.refresh(ts)

            cursor = p_start
            while cursor <= p_end:
                daily = db.query(AttendanceDaily).filter(
                    AttendanceDaily.employee_id == employee_id,
                    AttendanceDaily.work_date == cursor
                ).first()

                if daily:
                    if cursor.weekday() >= 5:
                        default_symbol = ""
                    else:
                        default_symbol = "Ro"
                    orig_symbol = daily.attendance_symbol or default_symbol
                    check_in = daily.check_in_time
                    check_out = daily.check_out_time
                    late_mins = daily.late_minutes or 0
                    early_mins = daily.early_minutes or 0
                else:
                    if cursor.weekday() >= 5:
                        orig_symbol = ""
                    else:
                        orig_symbol = "Ro"
                    check_in = None
                    check_out = None
                    late_mins = 0
                    early_mins = 0

                # Submitted Notion leave is an active attendance exception as
                # well: it must not be written as V while awaiting approval.
                if cursor.weekday() < 5:
                    from app.models.off_request import OffRequest
                    leave_req = db.query(OffRequest).filter(
                        OffRequest.employee_id == employee_id,
                        OffRequest.status.in_(["approved", "approve", "pending", "submitted", "under review", "under_review"]),
                        OffRequest.start_date <= cursor,
                        OffRequest.end_date >= cursor
                    ).first()

                    # Website-native requests only affect attendance after the
                    # assigned Manager has approved them. Legacy/Notion rows
                    # retain their existing behaviour.
                    website_request_type = str(leave_req.request_type or "").upper() if leave_req else ""
                    website_request_pending = (
                        website_request_type in {"LEAVE_REQUEST", "WORK_FROM_HOME_REQUEST", "BUSINESS_TRAVEL_REQUEST"}
                        and str(leave_req.status or "").upper() != "APPROVED"
                    )

                    if leave_req and not website_request_pending:
                        is_unpaid = (
                            "unpaid" in leave_req.request_type.lower()
                            or leave_req.request_type.lower() in {"unpaid_leave", "v", "ro"}
                            or str(getattr(employee, "employee_type", "FULLTIME") or "FULLTIME").upper() != "FULLTIME"
                        )
                        is_business = "business" in leave_req.request_type.lower() or leave_req.request_type.lower() in {"business_trip", "ct"}
                        is_work_from_home = leave_req.request_type.lower() in {"work_from_home_request", "work_from_home", "wfh"}
                        is_morning = "am" in leave_req.request_type.lower()
                        is_afternoon = "pm" in leave_req.request_type.lower()

                        in_mins = None
                        if check_in:
                            try:
                                h, m = map(int, check_in.split(":"))
                                in_mins = h * 60 + m
                            except Exception: pass
                        out_mins = None
                        if check_out:
                            try:
                                h, m = map(int, check_out.split(":"))
                                out_mins = h * 60 + m
                            except Exception: pass
                            
                        has_morning_work = in_mins is not None and in_mins <= 12 * 60
                        has_afternoon_work = out_mins is not None and out_mins >= 13 * 60 + 30

                        if is_work_from_home:
                            # WFH is a paid working day and does not consume
                            # the employee's annual leave entitlement.
                            orig_symbol = "X"
                        elif is_business:
                            orig_symbol = "CT"
                        elif is_morning:
                            leave_sym = "Ro" if is_unpaid else "P"
                            if has_afternoon_work:
                                orig_symbol = f"{leave_sym}/X"
                            else:
                                orig_symbol = f"{leave_sym}/Ro"
                        elif is_afternoon:
                            leave_sym = "Ro" if is_unpaid else "P"
                            if has_morning_work:
                                orig_symbol = f"X/{leave_sym}"
                            else:
                                orig_symbol = f"Ro/{leave_sym}"
                        else:
                            leave_sym = "Ro" if is_unpaid else "P"
                            if has_morning_work and has_afternoon_work:
                                orig_symbol = "X"
                            elif has_morning_work and not has_afternoon_work:
                                orig_symbol = f"X/{leave_sym}"
                            elif not has_morning_work and has_afternoon_work:
                                orig_symbol = f"{leave_sym}/X"
                            else:
                                orig_symbol = leave_sym
                    else:
                        if check_in or check_out:
                            orig_symbol = "" if cursor.weekday() >= 5 else "X"

                if cursor.weekday() >= 5:
                    orig_symbol = ""

                entry = db.query(TimesheetEntry).filter(
                    TimesheetEntry.timesheet_id == ts.id,
                    TimesheetEntry.employee_id == employee_id,
                    TimesheetEntry.work_date == cursor
                ).first()

                if not entry:
                    entry = TimesheetEntry(
                        timesheet_id=ts.id,
                        employee_id=employee_id,
                        work_date=cursor,
                        original_symbol=orig_symbol,
                        final_symbol=orig_symbol,
                        check_in_time=check_in,
                        check_out_time=check_out,
                        late_minutes=late_mins,
                        early_minutes=early_mins,
                        is_overridden=False
                    )
                    db.add(entry)
                else:
                    entry.original_symbol = orig_symbol
                    if not entry.is_overridden:
                        entry.final_symbol = orig_symbol
                    
                    # Always update physical check-in/out data regardless of override status
                    entry.check_in_time = check_in
                    entry.check_out_time = check_out
                    entry.late_minutes = late_mins
                    entry.early_minutes = early_mins

                cursor += timedelta(days=1)

            db.commit()

            entries = db.query(TimesheetEntry).filter(TimesheetEntry.timesheet_id == ts.id).all()

            ts.total_work_days = float(sum(
                _clocked_work_units_for_symbol(e.final_symbol, e.check_in_time, e.check_out_time)
                for e in entries
            ))
            ts.total_paid_leave_days = float(sum(_paid_leave_units_for_symbol(e.final_symbol) for e in entries))
            # Raw machine imports have no accountant-approved column yet. Keep
            # an existing approved accountant value immutable; otherwise set a
            # provisional payable value from the currently available rules.
            if ts.total_payroll_days is None or str(ts.approval_status or "").lower() != "approved":
                ts.total_payroll_days = float(
                    sum(_work_units_for_symbol(e.final_symbol) for e in entries)
                ) + ts.total_paid_leave_days

            unpaid = float(sum(_absent_units_for_symbol(e.final_symbol) for e in entries))
            ts.total_unpaid_leave_days = unpaid
            ts.total_absent_days = unpaid
            ts.total_late_minutes = sum(e.late_minutes for e in entries)
            ts.total_business_trip_days = float(sum(1.0 if e.final_symbol == "CT" else 0.0 for e in entries))

            db.commit()

            # TỰ ĐỘNG ĐẨY THÔNG TIN NGÀY CÔNG VỀ BẢNG LƯƠNG CÁ NHÂN (MonthlySalaryInput)
            salary_period = p_end.strftime("%Y-%m")
            salary_input = db.query(MonthlySalaryInput).filter(
                MonthlySalaryInput.employee_id == employee_id,
                MonthlySalaryInput.salary_period == salary_period
            ).first()

            if not salary_input and current_user.role in BUSINESS_ADMIN_ROLES:
                salary_input = MonthlySalaryInput(
                    employee_id=employee_id,
                    salary_period=salary_period,
                    actual_working_days=ts.total_payroll_days,
                    meal_allowance_free=1200000,
                    meal_allowance_tax=0,
                    phone_allowance_free=2000000,
                    trans_allowance_tax=2000000,
                    perf_allowance_tax=0,
                    other_income=0,
                    bonus=0,
                    bonus_14=0,
                    advance_payment=0,
                    pit_refund=0,
                    other_deductions=0,
                    is_published=False
                )
                db.add(salary_input)
            elif salary_input:
                salary_input.actual_working_days = ts.total_payroll_days

            db.commit()

        except Exception as exc:
            db.rollback()
            timesheet_errors.append(f"emp_id={employee_id} period={p_start}~{p_end}: {exc}")

    batch.status = "completed" if not skipped else "completed_with_errors"
    error_parts: list[str] = []
    if skipped:
        error_parts.append(f"Skipped {len(skipped)} row(s) due to employee_not_found")
    if timesheet_errors:
        error_parts.append(f"Timesheet errors: {'; '.join(timesheet_errors)}")
        batch.status = "completed_with_errors"
    if error_parts:
        batch.error_message = " | ".join(error_parts)
    record_audit(
        db,
        actor=current_user,
        action="ATTENDANCE_IMPORT_COMMIT",
        resource_type="UPLOAD_BATCH",
        resource_id=batch.id,
        summary=f"Import bảng công {data.period_start.isoformat()} đến {data.period_end.isoformat()}",
        after={
            "file_name": data.file_name,
            "inserted": inserted,
            "skipped": len(skipped),
            "timesheet_errors": len(timesheet_errors),
        },
        status="SUCCESS" if not timesheet_errors else "PARTIAL",
    )
    db.commit()

    return {
        "batch_id": batch.id,
        "status": batch.status,
        "inserted": inserted,
        "skipped": skipped,
        "timesheet_errors": timesheet_errors,
        "message": "Đã lưu dữ liệu và lịch sử upload.",
    }
