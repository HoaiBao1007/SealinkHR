from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.api.deps import get_db, get_attendance_manager_user
from app.models.holiday_setting import HolidaySetting
from app.models.employee import Employee
from app.models.timesheet import Timesheet
from app.models.timesheet_entry import TimesheetEntry
from app.schemas.holiday_schemas import HolidaySettingCreate, HolidaySettingResponse, HolidaySettingBulkCreate, HolidaySettingUpdate
from app.api.importer import resolve_period_for_work_date
from app.services.final_timesheet_report import _work_units_for_symbol, _paid_leave_units_for_symbol, _absent_units_for_symbol
from app.models.timesheet_period import TimesheetPeriod

router = APIRouter(
    prefix="/api/holidays",
    tags=["holidays"],
    dependencies=[Depends(get_attendance_manager_user)],
)

@router.get("", response_model=List[HolidaySettingResponse])
def get_holidays(db: Session = Depends(get_db)):
    holidays = db.query(HolidaySetting).order_by(HolidaySetting.holiday_date.desc()).all()
    
    # Pre-fetch locked periods and approved timesheets
    periods = db.query(TimesheetPeriod).filter(TimesheetPeriod.is_locked == True).all()
    locked_ranges = [(p.period_start, p.period_end) for p in periods]
    
    approved_ts = db.query(Timesheet).filter(Timesheet.approval_status == "approved").all()
    for ts in approved_ts:
        if (ts.period_start, ts.period_end) not in locked_ranges:
            locked_ranges.append((ts.period_start, ts.period_end))
            
    res = []
    for h in holidays:
        p_start, p_end = resolve_period_for_work_date(h.holiday_date)
        is_locked = (p_start, p_end) in locked_ranges
        res.append({
            "id": h.id,
            "holiday_name": h.holiday_name,
            "holiday_date": h.holiday_date,
            "is_custom": h.is_custom,
            "is_locked": is_locked
        })
    return res

@router.post("", response_model=HolidaySettingResponse)
def create_holiday(payload: HolidaySettingCreate, db: Session = Depends(get_db)):
    existing = db.query(HolidaySetting).filter(HolidaySetting.holiday_date == payload.holiday_date).first()
    if existing:
        raise HTTPException(status_code=400, detail="Đã tồn tại ngày lễ cho ngày này")
    
    holiday = HolidaySetting(
        holiday_name=payload.holiday_name,
        holiday_date=payload.holiday_date,
        is_custom=payload.is_custom
    )
    db.add(holiday)
    db.commit()
    db.refresh(holiday)

    apply_holiday_to_timesheets(db, holiday)

    return holiday

@router.delete("/{holiday_id}")
def delete_holiday(holiday_id: int, db: Session = Depends(get_db)):
    holiday = db.query(HolidaySetting).filter(HolidaySetting.id == holiday_id).first()
    if not holiday:
        raise HTTPException(status_code=404, detail="Không tìm thấy ngày lễ")
    
    # Check if period is locked or has approved timesheet
    p_start, p_end = resolve_period_for_work_date(holiday.holiday_date)
    period = db.query(TimesheetPeriod).filter(
        TimesheetPeriod.period_start == p_start,
        TimesheetPeriod.period_end == p_end
    ).first()
    is_locked = period.is_locked if period else False
    
    has_approved = db.query(Timesheet).filter(
        Timesheet.period_start == p_start,
        Timesheet.period_end == p_end,
        Timesheet.approval_status == "approved"
    ).first() is not None
    
    is_locked = is_locked or has_approved
    
    # Copy attributes to remove them from timesheets
    holiday_copy = HolidaySetting(holiday_name=holiday.holiday_name, holiday_date=holiday.holiday_date)
    
    db.delete(holiday)
    db.commit()

    if not is_locked:
        remove_holiday_from_timesheets(db, holiday_copy)
    return {"ok": True}

@router.post("/bulk", response_model=dict)
def create_bulk_holidays(payload: HolidaySettingBulkCreate, db: Session = Depends(get_db)):
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="Ngày kết thúc không được nhỏ hơn ngày bắt đầu")
    
    current_date = payload.start_date
    added_count = 0
    while current_date <= payload.end_date:
        existing = db.query(HolidaySetting).filter(HolidaySetting.holiday_date == current_date).first()
        if not existing:
            holiday = HolidaySetting(
                holiday_name=payload.holiday_name,
                holiday_date=current_date,
                is_custom=payload.is_custom
            )
            db.add(holiday)
            apply_holiday_to_timesheets(db, holiday)
            added_count += 1
        current_date += timedelta(days=1)
        
    db.commit()
    return {"message": f"Đã thêm thành công {added_count} ngày lễ", "added": added_count}

@router.put("/{holiday_id}", response_model=HolidaySettingResponse)
def update_holiday(holiday_id: int, payload: HolidaySettingUpdate, db: Session = Depends(get_db)):
    holiday = db.query(HolidaySetting).filter(HolidaySetting.id == holiday_id).first()
    if not holiday:
        raise HTTPException(status_code=404, detail="Không tìm thấy ngày lễ")
    
    if payload.holiday_date and payload.holiday_date != holiday.holiday_date:
        existing = db.query(HolidaySetting).filter(HolidaySetting.holiday_date == payload.holiday_date).first()
        if existing:
            raise HTTPException(status_code=400, detail="Đã tồn tại ngày lễ khác vào ngày này")
            
    old_name = holiday.holiday_name
    old_date = holiday.holiday_date

    if payload.holiday_name is not None:
        holiday.holiday_name = payload.holiday_name
    if payload.holiday_date is not None:
        holiday.holiday_date = payload.holiday_date
        
    db.commit()
    db.refresh(holiday)

    if old_name != holiday.holiday_name or old_date != holiday.holiday_date:
        old_holiday = HolidaySetting(holiday_name=old_name, holiday_date=old_date)
        remove_holiday_from_timesheets(db, old_holiday)

    apply_holiday_to_timesheets(db, holiday)
    return holiday


@router.post("/generate/{year}")
def generate_holidays_for_year(year: int, db: Session = Depends(get_db)):
    # Define hardcoded public holidays for specific years
    # Each entry: (date_str, name)
    holidays_data = []
    if year == 2024:
        holidays_data = [
            (f"{year}-01-01", "Tết Dương lịch"),
            (f"{year}-02-08", "Nghỉ Tết Âm lịch"),
            (f"{year}-02-09", "Nghỉ Tết Âm lịch"),
            (f"{year}-02-10", "Tết Âm lịch (Mùng 1)"),
            (f"{year}-02-11", "Tết Âm lịch (Mùng 2)"),
            (f"{year}-02-12", "Tết Âm lịch (Mùng 3)"),
            (f"{year}-02-13", "Nghỉ bù Tết Âm lịch"),
            (f"{year}-02-14", "Nghỉ bù Tết Âm lịch"),
            (f"{year}-04-18", "Giỗ tổ Hùng Vương (10/03 AL)"),
            (f"{year}-04-29", "Nghỉ hoán đổi 30/04"),
            (f"{year}-04-30", "Giải phóng miền Nam"),
            (f"{year}-05-01", "Quốc tế Lao động"),
            (f"{year}-08-31", "Nghỉ Lễ Quốc khánh"),
            (f"{year}-09-01", "Nghỉ Lễ Quốc khánh"),
            (f"{year}-09-02", "Quốc khánh"),
            (f"{year}-09-03", "Nghỉ Lễ Quốc khánh"),
        ]
    elif year == 2025:
        holidays_data = [
            (f"{year}-01-01", "Tết Dương lịch"),
            (f"{year}-01-25", "Nghỉ Tết Âm lịch"),
            (f"{year}-01-26", "Nghỉ Tết Âm lịch"),
            (f"{year}-01-27", "Nghỉ Tết Âm lịch"),
            (f"{year}-01-28", "Nghỉ Tết Âm lịch (29 Tết)"),
            (f"{year}-01-29", "Tết Âm lịch (Mùng 1)"),
            (f"{year}-01-30", "Tết Âm lịch (Mùng 2)"),
            (f"{year}-01-31", "Tết Âm lịch (Mùng 3)"),
            (f"{year}-02-01", "Nghỉ bù Tết Âm lịch"),
            (f"{year}-02-02", "Nghỉ bù Tết Âm lịch"),
            (f"{year}-04-07", "Giỗ tổ Hùng Vương (10/03 AL)"),
            (f"{year}-04-30", "Giải phóng miền Nam"),
            (f"{year}-05-01", "Quốc tế Lao động"),
            (f"{year}-05-02", "Nghỉ hoán đổi 30/04-01/05"),
            (f"{year}-09-01", "Nghỉ Lễ Quốc khánh"),
            (f"{year}-09-02", "Quốc khánh"),
        ]
    elif year == 2026:
        holidays_data = [
            (f"{year}-01-01", "Tết Dương lịch"),
            (f"{year}-01-02", "Nghỉ bù/Hoán đổi Tết Dương lịch"),
            (f"{year}-02-14", "Nghỉ Tết Âm lịch"),
            (f"{year}-02-15", "Nghỉ Tết Âm lịch"),
            (f"{year}-02-16", "Nghỉ Tết Âm lịch (29 Tết)"),
            (f"{year}-02-17", "Tết Âm lịch (Mùng 1)"),
            (f"{year}-02-18", "Tết Âm lịch (Mùng 2)"),
            (f"{year}-02-19", "Tết Âm lịch (Mùng 3)"),
            (f"{year}-02-20", "Nghỉ bù Tết Âm lịch"),
            (f"{year}-02-21", "Nghỉ bù Tết Âm lịch"),
            (f"{year}-02-22", "Nghỉ bù Tết Âm lịch"),
            (f"{year}-04-26", "Giỗ tổ Hùng Vương (10/03 AL)"),
            (f"{year}-04-27", "Nghỉ bù Giỗ tổ Hùng Vương"),
            (f"{year}-04-30", "Giải phóng miền Nam"),
            (f"{year}-05-01", "Quốc tế Lao động"),
            (f"{year}-09-01", "Nghỉ Lễ Quốc khánh"),
            (f"{year}-09-02", "Quốc khánh"),
        ]
    else:
        # Fallback for other years (only statutory solar dates)
        holidays_data = [
            (f"{year}-01-01", "Tết Dương lịch"),
            (f"{year}-04-30", "Giải phóng miền Nam"),
            (f"{year}-05-01", "Quốc tế Lao động"),
            (f"{year}-09-02", "Quốc khánh"),
        ]
    
    count = 0
    from datetime import datetime
    for d_str, name in holidays_data:
        d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
        existing = db.query(HolidaySetting).filter(HolidaySetting.holiday_date == d_obj).first()
        if not existing:
            h = HolidaySetting(holiday_name=name, holiday_date=d_obj, is_custom=False)
            db.add(h)
            count += 1
            # Apply to timesheets if needed
            apply_holiday_to_timesheets(db, h)
    
    db.commit()
    return {"message": f"Đã tạo thành công {count} ngày nghỉ lễ cho năm {year}.", "added": count}

def recalculate_timesheet_totals(db: Session, timesheet_id: int):
    ts = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not ts:
        return
    entries = db.query(TimesheetEntry).filter(TimesheetEntry.timesheet_id == ts.id).all()
    ts.total_work_days = float(sum(_work_units_for_symbol(e.final_symbol) for e in entries))
    ts.total_paid_leave_days = float(sum(_paid_leave_units_for_symbol(e.final_symbol) for e in entries))
    unpaid = float(sum(_absent_units_for_symbol(e.final_symbol) for e in entries))
    ts.total_unpaid_leave_days = unpaid
    ts.total_absent_days = unpaid
    ts.total_late_minutes = sum(e.late_minutes for e in entries)
    ts.total_business_trip_days = float(sum(1.0 if e.final_symbol == "CT" else 0.0 for e in entries))

def remove_holiday_from_timesheets(db: Session, holiday: HolidaySetting):
    reason_text = f"Nghỉ lễ/ bù: {holiday.holiday_name}"
    entries = db.query(TimesheetEntry).filter(
        TimesheetEntry.work_date == holiday.holiday_date
    ).all()
    
    affected_timesheet_ids = set()
    for entry in entries:
        ts = db.query(Timesheet).filter(Timesheet.id == entry.timesheet_id).first()
        if ts and ts.approval_status == "approved":
            continue
            
        if entry.override_reason:
            if entry.override_reason == reason_text:
                entry.final_symbol = entry.original_symbol
                entry.is_overridden = False
                entry.override_reason = None
                affected_timesheet_ids.add(entry.timesheet_id)
            elif reason_text in entry.override_reason:
                parts = [p.strip() for p in entry.override_reason.split("|") if p.strip() != reason_text]
                if parts:
                    entry.override_reason = " | ".join(parts)
                else:
                    entry.final_symbol = entry.original_symbol
                    entry.is_overridden = False
                    entry.override_reason = None
                affected_timesheet_ids.add(entry.timesheet_id)
    
    db.commit()
    for ts_id in affected_timesheet_ids:
        recalculate_timesheet_totals(db, ts_id)
    db.commit()

def apply_holiday_to_timesheets(db: Session, holiday: HolidaySetting):
    period_start, period_end = resolve_period_for_work_date(holiday.holiday_date)
    
    employees = db.query(Employee).filter(Employee.is_active == True).all()
    if not employees:
        return
    
    affected_timesheet_ids = set()
    for emp in employees:
        ts = db.query(Timesheet).filter(
            Timesheet.employee_id == emp.id,
            Timesheet.period_start == period_start,
            Timesheet.period_end == period_end
        ).first()
        
        if not ts:
            ts = Timesheet(
                employee_id=emp.id,
                period_start=period_start,
                period_end=period_end,
                approval_status="draft"
            )
            db.add(ts)
            db.commit()
            db.refresh(ts)
            
        if ts.approval_status == "approved":
            continue
            
        affected_timesheet_ids.add(ts.id)
            
        entry = db.query(TimesheetEntry).filter(
            TimesheetEntry.timesheet_id == ts.id,
            TimesheetEntry.work_date == holiday.holiday_date
        ).first()
        
        reason_text = f"Nghỉ lễ/ bù: {holiday.holiday_name}"
        
        if not entry:
            entry = TimesheetEntry(
                timesheet_id=ts.id,
                employee_id=emp.id,
                work_date=holiday.holiday_date,
                original_symbol="X",
                final_symbol="X",
                is_overridden=True,
                override_reason=reason_text
            )
            db.add(entry)
        else:
            entry.final_symbol = "X"
            entry.is_overridden = True
            if entry.override_reason and "Nghỉ lễ" not in entry.override_reason:
                entry.override_reason = f"{entry.override_reason} | {reason_text}"
            else:
                entry.override_reason = reason_text

    db.commit()
    for ts_id in affected_timesheet_ids:
        recalculate_timesheet_totals(db, ts_id)
    db.commit()
