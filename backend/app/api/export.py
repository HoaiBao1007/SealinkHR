from datetime import date
from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_attendance_manager_user
from app.models.attendance_daily import AttendanceDaily
from app.models.employee import Employee
from app.services.attendance_parser import AttendanceParser
from app.services.final_timesheet_report import (
    build_final_timesheet_report_from_attendance_json,
    build_final_timesheet_report_from_db,
    export_to_final_timesheet,
)
from app.services.notion_leave_reconciliation import reconcile_attendance_with_notion

router = APIRouter(tags=["export"], dependencies=[Depends(get_attendance_manager_user)])


def _build_notion_employee_directory(db: Session) -> dict[str, list[str]]:
    rows = (
        db.query(Employee.notion_name, Employee.full_name, Employee.machine_employee_id)
        .order_by(Employee.id.asc())
        .all()
    )

    directory: dict[str, list[str]] = {}
    for notion_name, full_name, machine_employee_id in rows:
        names = [notion_name, full_name]
        normalized_machine_id = str(machine_employee_id or "").strip()
        if not normalized_machine_id:
            continue
        for name in names:
            normalized_name = str(name or "").strip()
            if not normalized_name:
                continue
            directory.setdefault(normalized_name, [])
            if normalized_machine_id not in directory[normalized_name]:
                directory[normalized_name].append(normalized_machine_id)

    return directory


def _build_employee_report_directory(db: Session) -> dict[str, dict[str, str | None]]:
    rows = (
        db.query(Employee.machine_employee_id, Employee.full_name, Employee.department_name, Employee.notion_name)
        .order_by(Employee.id.asc())
        .all()
    )

    directory: dict[str, dict[str, str | None]] = {}
    for machine_employee_id, full_name, department_name, notion_name in rows:
        normalized_machine_id = str(machine_employee_id or "").strip()
        if not normalized_machine_id:
            continue
        directory[normalized_machine_id] = {
            # Keep notion_name for matching leave records only. The exported
            # report must always use the personnel profile's Vietnamese name.
            "full_name": str(full_name or "").strip() or str(notion_name or "").strip() or None,
            "department_name": str(department_name or "").strip() or None,
        }

    return directory


def _apply_employee_report_metadata(
    employees: list[dict],
    employee_report_directory: dict[str, dict[str, str | None]],
) -> list[dict]:
    for employee in employees:
        machine_employee_id = str(employee.get("employee_id") or "").strip()
        if not machine_employee_id:
            continue

        profile = employee_report_directory.get(machine_employee_id)
        if not profile:
            continue

        if profile.get("full_name"):
            employee["full_name"] = profile["full_name"]
        if profile.get("department_name"):
            employee["department_name"] = profile["department_name"]
            employee["department"] = profile["department_name"]

    return employees


def _parse_period_start(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="period_start must be a valid date") from exc


@router.get("/api/export/timesheet")
def export_timesheet(
    period_start: date = Query(...),
    period_end: date = Query(...),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        report = build_final_timesheet_report_from_db(db, period_start, period_end)
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="database is unavailable") from exc
    if not report.rows:
        raise HTTPException(status_code=404, detail="no timesheet data for selected period")
    output = export_to_final_timesheet(report)

    filename = f"timesheet_{period_start.isoformat()}_{period_end.isoformat()}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.post("/api/export/attendance-json-report")
def export_attendance_json_report(
    file: UploadFile = File(...),
    notion_file: UploadFile | None = File(default=None),
    period_start: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    period_start_date = _parse_period_start(period_start)

    try:
        payload = file.file.read()
        parser = AttendanceParser()
        employees = parser.parse(payload, period_start=period_start_date)
        employees = _apply_employee_report_metadata(employees, _build_employee_report_directory(db))
        report_period_start = parser.last_period_start
        report_period_end = parser.last_period_end
        if notion_file is not None:
            notion_payload = notion_file.file.read()
            if notion_payload:
                employees = reconcile_attendance_with_notion(
                    employees,
                    notion_payload,
                    _build_notion_employee_directory(db),
                    period_start=report_period_start,
                    period_end=report_period_end,
                )
        if report_period_start is None or report_period_end is None:
            raise ValueError("Không xác định được chu kỳ công từ workbook")
        report = build_final_timesheet_report_from_attendance_json(employees, report_period_start, report_period_end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="database is unavailable") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Không export được report từ workbook: {exc}") from exc

    output = export_to_final_timesheet(report)
    filename = f"timesheet_preview_{report.period_start.isoformat()}_{report.period_end.isoformat()}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.get("/api/export/kpi")
def export_kpi(
    period_start: date = Query(...),
    period_end: date = Query(...),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        employees = db.query(Employee).order_by(Employee.id.asc()).all()
        daily_rows = (
            db.query(AttendanceDaily)
            .filter(AttendanceDaily.period_start == period_start, AttendanceDaily.period_end == period_end)
            .order_by(AttendanceDaily.work_date.asc(), AttendanceDaily.employee_id.asc())
            .all()
        )
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="database is unavailable") from exc

    if not daily_rows:
        raise HTTPException(status_code=404, detail="no KPI data for selected period")

    emp_map = {e.id: e for e in employees}
    summary_rows: list[dict] = []
    trend_map: dict[str, dict[str, int]] = {}

    symbol_counts = {"X": 0, "P": 0, "Ro": 0, "CT": 0, "OTHER": 0}
    total_late_minutes = 0
    total_early_minutes = 0
    abnormal_days = 0

    for row in daily_rows:
        emp = emp_map.get(row.employee_id)
        symbol = (row.attendance_symbol or "").strip()
        if symbol.upper() in {"V", "O", "RO"}:
            symbol = "Ro"
        if symbol in symbol_counts:
            symbol_counts[symbol] += 1
        else:
            symbol_counts["OTHER"] += 1

        late = int(row.late_minutes or 0)
        early = int(row.early_minutes or 0)
        total_late_minutes += late
        total_early_minutes += early
        is_abnormal = bool(row.abnormal_level) or late > 0 or early > 0
        if is_abnormal:
            abnormal_days += 1

        work_key = row.work_date.isoformat()
        if work_key not in trend_map:
            trend_map[work_key] = {"present": 0, "absent": 0, "abnormal": 0}
        if symbol == "X":
            trend_map[work_key]["present"] += 1
        if symbol == "Ro":
            trend_map[work_key]["absent"] += 1
        if is_abnormal:
            trend_map[work_key]["abnormal"] += 1

        summary_rows.append(
            {
                "Work Date": work_key,
                "Employee ID": row.employee_id,
                "Machine ID": emp.machine_employee_id if emp else "",
                "Full Name": emp.full_name if emp else "",
                "Department": emp.department_name if emp else "",
                "Symbol": symbol,
                "Late Minutes": late,
                "Early Minutes": early,
                "Abnormal": "Yes" if is_abnormal else "No",
            }
        )

    overview_rows = [
        {"Metric": "Period Start", "Value": period_start.isoformat()},
        {"Metric": "Period End", "Value": period_end.isoformat()},
        {"Metric": "Total Employees", "Value": len(employees)},
        {"Metric": "Total Late Minutes", "Value": total_late_minutes},
        {"Metric": "Total Early Minutes", "Value": total_early_minutes},
        {"Metric": "Abnormal Days", "Value": abnormal_days},
        {"Metric": "Symbol X", "Value": symbol_counts["X"]},
        {"Metric": "Symbol P", "Value": symbol_counts["P"]},
        {"Metric": "Symbol Ro", "Value": symbol_counts["Ro"]},
        {"Metric": "Symbol CT", "Value": symbol_counts["CT"]},
        {"Metric": "Symbol OTHER", "Value": symbol_counts["OTHER"]},
    ]

    trend_rows = [
        {
            "Work Date": key,
            "Present Count": value["present"],
            "Absent Count": value["absent"],
            "Abnormal Count": value["abnormal"],
        }
        for key, value in sorted(trend_map.items(), key=lambda item: item[0])
    ]

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(overview_rows).to_excel(writer, sheet_name="KPI_Overview", index=False)
        pd.DataFrame(trend_rows).to_excel(writer, sheet_name="KPI_Trend", index=False)
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="KPI_Detail", index=False)
    output.seek(0)

    filename = f"kpi_{period_start.isoformat()}_{period_end.isoformat()}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
