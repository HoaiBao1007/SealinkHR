import io
from io import BytesIO
from datetime import date, datetime
import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.employee import Employee
from app.models.off_request import OffRequest
from app.models.timesheet import Timesheet
from app.models.timesheet_entry import TimesheetEntry
from app.models.attendance_daily import AttendanceDaily
from app.models.monthly_salary_input import MonthlySalaryInput
from app.services.notion_leave_reconciliation import (
    save_notion_leaves_to_db,
    sync_notion_work_from_home_to_attendance_db,
)

def _build_cycle_days(start_day=23, end_day=22):
    days = []
    # 23 to 31
    for d in range(start_day, 32):
        days.append(f"03/{d:02d}")
    # 1 to 22
    for d in range(1, end_day + 1):
        days.append(f"04/{d:02d}")
    return days

def _build_matrix_row(prefix, days_values):
    row = list(prefix)
    cycle_days = _build_cycle_days()
    for day in cycle_days:
        day_num = int(day.split("/")[1])
        row.append(days_values.get(day_num, ""))
    return row

def test_notion_leaves_save_to_database(client: TestClient, db_session: Session):
    # 1. Create a test employee matching the Notion record
    # Notion name: TOMMY DAT, ID/Machine ID: 26, Full name: NGUYEN THANH DAT
    emp = Employee(
        machine_employee_id="26",
        full_name="NGUYEN THANH DAT",
        notion_name="TOMMY DAT",
        annual_leave_quota=12,
        annual_leave_used=0,
        paid_leave_balance=0,
        unpaid_leave_balance=0,
        is_active=True,
        contract_salary=10000000,
        employee_code="SL003",
        position="SALE"
    )
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)

    # Pre-populate Timesheet, AttendanceDaily, and TimesheetEntry
    ts = Timesheet(
        employee_id=emp.id,
        period_start=date(2026, 3, 23),
        period_end=date(2026, 4, 22),
        approval_status="draft"
    )
    db_session.add(ts)
    db_session.commit()
    db_session.refresh(ts)

    daily_2 = AttendanceDaily(
        employee_id=emp.id,
        work_date=date(2026, 4, 2),
        period_start=date(2026, 3, 23),
        period_end=date(2026, 4, 22),
        check_in_time="08:30",
        check_out_time="17:30",
        attendance_symbol="X",
        late_minutes=0,
        early_minutes=0,
        source_priority=1
    )
    db_session.add(daily_2)
    db_session.commit()

    entry1 = TimesheetEntry(
        timesheet_id=ts.id,
        employee_id=emp.id,
        work_date=date(2026, 4, 1),
        original_symbol="V",
        final_symbol="V",
        is_overridden=False
    )
    entry2 = TimesheetEntry(
        timesheet_id=ts.id,
        employee_id=emp.id,
        work_date=date(2026, 4, 2),
        original_symbol="X",
        final_symbol="X",
        check_in_time="08:30",
        check_out_time="17:30",
        is_overridden=False
    )
    db_session.add_all([entry1, entry2])
    db_session.commit()

    cycle_days = _build_cycle_days()
    schedule_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            _build_matrix_row(["26", "TOMMY DAT", "SALE"], {}),
        ]
    )
    profile_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            _build_matrix_row(["26", "TOMMY DAT", "SALE"], {}),
            _build_matrix_row(["", "", ""], {2: "08:30\n17:30"}), # works on 2nd April
        ]
    )
    abnormal_df = pd.DataFrame(
        [
            ["ID", "Ngay", "Buoi 1 Vao lam", "Buoi 1 Ra nghi", "Thoi gian tre", "Thoi gian som"],
        ]
    )
    summary_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", "Tong so phut di muon trong thang", "Tong so ngay vang mat"],
            ["26", "TOMMY DAT", "SALE", 0, 0],
        ]
    )
    checkin_report_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", "Ngay", "Gio vao", "Gio ra"],
            ["26", "TOMMY DAT", "SALE", "2026-04-02", "08:30", "17:30"],
        ]
    )

    workbook_stream = BytesIO()
    with pd.ExcelWriter(workbook_stream, engine="openpyxl") as writer:
        schedule_df.to_excel(writer, index=False, header=False, sheet_name="Bảng thông tin lịch trình")
        checkin_report_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo check-in")
        abnormal_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo bất thường")
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Hồ sơ check-in")
        summary_df.to_excel(writer, index=False, header=False, sheet_name="Bảng tóm tắt check-in")
    workbook_stream.seek(0)

    # Approved leave request: April 1st, 2026 (full day leave)
    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "Leave Request,SALE - TOMMY DAT (http://notion.so/123),IT - TOMMY DAT,Đau ốm,04/01/2026 8:30 AM (GMT+7) -> 5:30 PM,1,Approved",
        ]
    ).encode("utf-8")

    # 3. Request import /attendance-json
    response = client.post(
        "/api/import/attendance-json",
        files={
            "file": (
                "attendance_tommy.xlsx",
                workbook_stream,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "notion_file": ("leave_request.csv", notion_csv, "text/csv"),
        },
        data={"period_start": "2026-03-23"},
    )

    assert response.status_code == 200

    # 4. Check if OffRequest is stored in database
    db_session.expire_all()
    off_reqs = db_session.query(OffRequest).filter(OffRequest.employee_id == emp.id).all()
    assert len(off_reqs) == 1
    assert off_reqs[0].start_date == date(2026, 4, 1)
    assert off_reqs[0].end_date == date(2026, 4, 1)
    assert off_reqs[0].status == "approved"
    assert off_reqs[0].request_type == "paid_leave"

    # 5. Check if the timesheet grid queries and uses this off request
    # Call the timesheet grid API
    grid_response = client.get(
        "/api/timesheets/grid",
        params={"period_start": "2026-03-23", "period_end": "2026-04-22"}
    )
    assert grid_response.status_code == 200
    grid_data = grid_response.json()
    
    # Locate TOMMY DAT row
    tommy_row = next((r for r in grid_data["rows"] if r["machine_employee_id"] == "26"), None)
    assert tommy_row is not None
    
    # 2026-04-01 is a weekday (Wednesday) and should show "P" from the OffRequest
    assert tommy_row["days"]["2026-04-01"] == "P"
    
    # 2026-04-02 should show "X" from the work check-in
    assert tommy_row["days"]["2026-04-02"] == "X"


def test_notion_leaves_save_vietnamese_date_format(client: TestClient, db_session: Session):
    emp = Employee(
        machine_employee_id="20",
        full_name="Gia Bao",
        notion_name="BOO BAO",
        annual_leave_quota=12,
        annual_leave_used=0,
        paid_leave_balance=0,
        unpaid_leave_balance=0,
        is_active=True,
        contract_salary=10000000,
        employee_code="SL004",
        position="SALE"
    )
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)

    ts = Timesheet(
        employee_id=emp.id,
        period_start=date(2026, 5, 23),
        period_end=date(2026, 6, 22),
        approval_status="draft"
    )
    db_session.add(ts)
    db_session.commit()

    cycle_days = []
    for d in range(23, 32):
        cycle_days.append(f"05/{d:02d}")
    for d in range(1, 23):
        cycle_days.append(f"06/{d:02d}")

    schedule_df = pd.DataFrame([["ID", "Ten", "Phong ban", *cycle_days], ["20", "BOO BAO", "SALE", *["" for _ in cycle_days]]])
    profile_df = pd.DataFrame([
        ["ID", "Ten", "Phong ban", *cycle_days],
        ["20", "BOO BAO", "SALE", *["" for _ in cycle_days]],
        ["", "", "", *["" for _ in cycle_days]]
    ])
    
    # 5th June is at index 3 + 9 (May days) + 5 (June days) - 1 = 16 (since index is 0-based and starts with ID, Ten, Phong ban)
    # May 23-31 is 9 columns. June 1-5 is 5 columns. ID, Ten, Phong ban are 3 columns.
    # Total columns before June 5th: 3 + 9 + 4 = 16 columns. So June 5th is index 16.
    # Let's set it dynamically by checking columns:
    col_headers = ["ID", "Ten", "Phong ban", *cycle_days]
    june_5_idx = col_headers.index("06/05")
    june_19_idx = col_headers.index("06/19")
    
    profile_df.iloc[2, june_5_idx] = "08:57\n13:02"
    profile_df.iloc[2, june_19_idx] = "08:51\n13:16"

    abnormal_df = pd.DataFrame([["ID", "Ngay", "Buoi 1 Vao lam", "Buoi 1 Ra nghi", "Thoi gian tre", "Thoi gian som"]])
    summary_df = pd.DataFrame([
        ["ID", "Ten", "Phong ban", "Tong so phut di muon trong thang", "Tong so ngay vang mat"],
        ["20", "BOO BAO", "SALE", 0, 0]
    ])
    checkin_report_df = pd.DataFrame([
        ["ID", "Ten", "Phong ban", "Ngay", "Gio vao", "Gio ra"],
        ["20", "BOO BAO", "SALE", "2026-06-05", "08:57", "13:02"],
        ["20", "BOO BAO", "SALE", "2026-06-19", "08:51", "13:16"],
    ])

    workbook_stream = BytesIO()
    with pd.ExcelWriter(workbook_stream, engine="openpyxl") as writer:
        schedule_df.to_excel(writer, index=False, header=False, sheet_name="Bảng thông tin lịch trình")
        checkin_report_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo check-in")
        abnormal_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo bất thường")
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Hồ sơ check-in")
        summary_df.to_excel(writer, index=False, header=False, sheet_name="Bảng tóm tắt check-in")
    workbook_stream.seek(0)

    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "Leave Request,BOO BAO,BOO BAO,Cá nhân,5/6/2026 8:00 AM (GMT+7) → 12:00 PM,0.5,Approved",
            "Leave Request,BOO BAO,BOO BAO,Cá nhân,19/06/2026 12:00 PM (GMT+7) → 5:30 PM,0.5,Approved",
        ]
    ).encode("utf-8")

    response = client.post(
        "/api/import/attendance-json",
        files={
            "file": ("attendance_boobao.xlsx", workbook_stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "notion_file": ("leave_request.csv", notion_csv, "text/csv"),
        },
        data={"period_start": "2026-05-23"},
    )

    assert response.status_code == 200
    db_session.expire_all()
    off_reqs = db_session.query(OffRequest).filter(OffRequest.employee_id == emp.id).order_by(OffRequest.start_date).all()
    assert len(off_reqs) == 2
    
    assert off_reqs[0].start_date == date(2026, 6, 5)
    assert off_reqs[0].end_date == date(2026, 6, 5)
    assert off_reqs[0].total_days == 0.5
    assert off_reqs[0].request_type == "paid_leave_am"
    
    assert off_reqs[1].start_date == date(2026, 6, 19)
    assert off_reqs[1].end_date == date(2026, 6, 19)
    assert off_reqs[1].total_days == 0.5
    assert off_reqs[1].request_type == "paid_leave_pm"


def test_submitted_notion_leave_is_saved_as_approved_for_attendance(db_session: Session):
    employee = Employee(
        machine_employee_id="26",
        full_name="Nguyen Thanh Dat",
        notion_name="TOMMY DAT",
        annual_leave_quota=12,
        annual_leave_used=0,
        paid_leave_balance=0,
        unpaid_leave_balance=0,
        is_active=True,
        contract_salary=10000000,
        employee_code="SL003",
        position="SALE",
    )
    db_session.add(employee)
    db_session.commit()

    notion_csv = (
        b"Name,Ten nhan vien,Leave Balance,Ly do Nghi,Thoi Gian,So Ngay Nghi,Trang Thai\n"
        b"Leave Request,IT - TOMMY DAT,IT - TOMMY DAT,Viec gia dinh,07/06/2026 8:30 AM (GMT+7) -> 5:30 PM,1,Under Review\n"
    )
    save_notion_leaves_to_db(
        db_session,
        notion_csv,
        period_start=date(2026, 6, 23),
        period_end=date(2026, 7, 22),
    )

    request = db_session.query(OffRequest).filter(OffRequest.employee_id == employee.id).one()
    assert request.start_date == date(2026, 7, 6)
    assert request.end_date == date(2026, 7, 6)
    assert request.request_type == "paid_leave"
    assert request.status == "approved"


def test_wfh_is_persisted_as_work_without_creating_an_off_request(db_session: Session):
    employee = Employee(
        machine_employee_id="41",
        full_name="Nguyen Le Ngoc Hoa",
        notion_name="HILMAR HOA",
        annual_leave_quota=12,
        annual_leave_used=0,
        paid_leave_balance=0,
        unpaid_leave_balance=0,
        is_active=True,
        contract_salary=10000000,
        employee_code="SL041",
        position="DOCS",
    )
    db_session.add(employee)
    db_session.commit()
    timesheet = Timesheet(
        employee_id=employee.id,
        period_start=date(2026, 6, 23),
        period_end=date(2026, 7, 22),
        approval_status="approved",
        total_work_days=20,
        total_payroll_days=23,
        total_paid_leave_days=2.5,
    )
    salary_input = MonthlySalaryInput(
        employee_id=employee.id,
        salary_period="2026-07",
        actual_working_days=23,
    )
    db_session.add_all([timesheet, salary_input])
    db_session.commit()
    db_session.add(
        AttendanceDaily(
            employee_id=employee.id,
            work_date=date(2026, 7, 6),
            period_start=date(2026, 6, 23),
            period_end=date(2026, 7, 22),
            attendance_symbol="V",
            abnormal_level="L1",
        )
    )
    db_session.commit()

    notion_csv = (
        b"Name,Ten nhan vien,Leave Balance,Ly do Nghi,Thoi Gian,So Ngay Nghi,Trang Thai\n"
        b"Work From Home,DOCS - HILMAR HOA,DOCS - HILMAR HOA,Cham soc nguoi than,07/06/2026 12:00 AM (GMT+7) -> 07/08/2026 12:00 AM (GMT+7),0,Under Review\n"
    )
    affected_dates = sync_notion_work_from_home_to_attendance_db(
        db_session,
        notion_csv,
        period_start=date(2026, 6, 23),
        period_end=date(2026, 7, 22),
    )

    daily_rows = (
        db_session.query(AttendanceDaily)
        .filter(AttendanceDaily.employee_id == employee.id)
        .order_by(AttendanceDaily.work_date)
        .all()
    )
    assert affected_dates == 3
    assert [row.work_date for row in daily_rows] == [date(2026, 7, 6), date(2026, 7, 7), date(2026, 7, 8)]
    assert all(row.attendance_symbol == "X" for row in daily_rows)
    assert all(row.abnormal_level is None for row in daily_rows)
    assert db_session.query(OffRequest).filter(OffRequest.employee_id == employee.id).count() == 0
    db_session.refresh(timesheet)
    db_session.refresh(salary_input)
    assert float(timesheet.total_work_days) == 0
    assert float(timesheet.total_payroll_days) == 23
    assert salary_input.actual_working_days == 23
