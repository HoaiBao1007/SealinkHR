from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import OperationalError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_admin_user
from app.models.attendance_daily import AttendanceDaily
from app.models.employee import Employee

router = APIRouter(tags=["dashboard"], dependencies=[Depends(get_admin_user)])


class DashboardTrendPoint(BaseModel):
    work_date: str
    present_count: int
    absent_count: int
    abnormal_count: int


class DashboardKpiResponse(BaseModel):
    period_start: str
    period_end: str
    total_employees: int
    active_employees: int
    present_days: int
    absent_days: int
    business_trip_days: int
    paid_leave_days: int
    unpaid_leave_days: int
    total_late_minutes: int
    total_early_minutes: int
    abnormal_days: int
    symbol_counts: dict[str, int]
    trend: list[DashboardTrendPoint]


@router.get("/api/dashboard/kpi", response_model=DashboardKpiResponse)
def get_dashboard_kpi(
    period_start: date = Query(...),
    period_end: date = Query(...),
    db: Session = Depends(get_db),
) -> DashboardKpiResponse:
    if period_start > period_end:
        raise HTTPException(status_code=400, detail="period_start must be <= period_end")

    try:
        employees = db.query(Employee).all()
        daily_rows = (
            db.query(AttendanceDaily)
            .filter(AttendanceDaily.period_start == period_start, AttendanceDaily.period_end == period_end)
            .order_by(AttendanceDaily.work_date.asc())
            .all()
        )
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="database is unavailable") from exc

    total_employees = len(employees)
    active_employees = sum(1 for e in employees if bool(e.is_active))

    symbol_counts = {"X": 0, "P": 0, "V": 0, "CT": 0, "OTHER": 0}
    present_days = 0
    absent_days = 0
    business_trip_days = 0
    paid_leave_days = 0
    unpaid_leave_days = 0
    total_late_minutes = 0
    total_early_minutes = 0
    abnormal_days = 0

    trend_map: dict[str, DashboardTrendPoint] = {}

    for row in daily_rows:
        symbol = (row.attendance_symbol or "").strip().upper()
        if symbol in symbol_counts:
            symbol_counts[symbol] += 1
        else:
            symbol_counts["OTHER"] += 1

        if symbol == "X":
            present_days += 1
        elif symbol == "V":
            absent_days += 1
            unpaid_leave_days += 1
        elif symbol == "P":
            paid_leave_days += 1
        elif symbol == "CT":
            business_trip_days += 1

        late = int(row.late_minutes or 0)
        early = int(row.early_minutes or 0)
        total_late_minutes += late
        total_early_minutes += early

        is_abnormal = bool(row.abnormal_level) or late > 0 or early > 0
        if is_abnormal:
            abnormal_days += 1

        key = row.work_date.isoformat()
        if key not in trend_map:
            trend_map[key] = DashboardTrendPoint(
                work_date=key,
                present_count=0,
                absent_count=0,
                abnormal_count=0,
            )

        point = trend_map[key]
        if symbol == "X":
            point.present_count += 1
        if symbol == "V":
            point.absent_count += 1
        if is_abnormal:
            point.abnormal_count += 1

    trend = [trend_map[key] for key in sorted(trend_map.keys())]

    return DashboardKpiResponse(
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        total_employees=total_employees,
        active_employees=active_employees,
        present_days=present_days,
        absent_days=absent_days,
        business_trip_days=business_trip_days,
        paid_leave_days=paid_leave_days,
        unpaid_leave_days=unpaid_leave_days,
        total_late_minutes=total_late_minutes,
        total_early_minutes=total_early_minutes,
        abnormal_days=abnormal_days,
        symbol_counts=symbol_counts,
        trend=trend,
    )
