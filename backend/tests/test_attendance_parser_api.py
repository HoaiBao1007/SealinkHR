from io import BytesIO

import pandas as pd


def _build_cycle_days() -> list[int]:
    return list(range(23, 32)) + list(range(1, 23))


def _build_matrix_row(prefix: list[object], values_by_day: dict[int, object]) -> list[object]:
    cycle_days = _build_cycle_days()
    return prefix + [values_by_day.get(day, "") for day in cycle_days]


def test_import_attendance_json_returns_merged_employee_payload(client):
    cycle_days = _build_cycle_days()
    schedule_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            _build_matrix_row(["2", "NGUYEN THANH TR", "Not Set1"], {23: 1, 24: 1, 26: 1, 27: 1}),
        ]
    )
    profile_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            _build_matrix_row(["2", "NGUYEN THANH TR", "Not Set1"], {}),
            _build_matrix_row(["", "", ""], {23: "08:15\n17:30", 24: "08:45*\n17:30", 26: "08:15"}),
        ]
    )
    abnormal_df = pd.DataFrame(
        [
            ["ID", "Ngay", "Buoi 1 Vao lam", "Buoi 1 Ra nghi", "Thoi gian tre", "Thoi gian som"],
            ["2", "2026-03-24", "08:45", "17:30", 15, 0],
            ["2", "2026-03-26", "08:15", "Bỏ lỡ", 0, 0],
            ["2", "2026-03-27", "Bỏ lỡ", "Bỏ lỡ", 0, 0],
        ]
    )
    summary_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", "Tong so phut di muon trong thang", "Tong so ngay vang mat"],
            ["2", "NGUYEN THANH TR", "Not Set1", 1050, 8],
        ]
    )
    checkin_report_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", "Ngay", "Gio vao", "Gio ra"],
            ["2", "NGUYEN THANH TR", "Not Set1", "2026-03-23", "08:15", "17:30"],
        ]
    )

    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        schedule_df.to_excel(writer, index=False, header=False, sheet_name="Bảng thông tin lịch trình")
        checkin_report_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo check-in")
        abnormal_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo bất thường")
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Hồ sơ check-in")
        summary_df.to_excel(writer, index=False, header=False, sheet_name="Bảng tóm tắt check-in")
    stream.seek(0)

    files = {
        "file": (
            "attendance_full_cycle.xlsx",
            stream,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    response = client.post("/api/import/attendance-json", files=files)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["employees"]) == 1
    employee = payload["employees"][0]
    assert employee["employee_id"] == "2"
    assert employee["attendance_details"]["2026-03-26"]["status"] == "Missing_Punch"
    assert employee["attendance_details"]["2026-03-27"]["status"] == "Absent"
    assert payload["validation_summary"]["2"]["computed_total_late_minutes"] == 15


def test_import_attendance_json_rejects_invalid_period_start(client):
    files = {
        "file": (
            "empty.xlsx",
            BytesIO(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    response = client.post("/api/import/attendance-json", files=files, data={"period_start": "not-a-date"})

    assert response.status_code == 400
    assert response.json()["detail"] == "period_start must be a valid date"


def test_import_attendance_json_applies_notion_half_day_symbols(client):
    cycle_days = _build_cycle_days()
    schedule_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            _build_matrix_row(["2", "NGUYEN THANH TR", "Not Set1"], {26: 1, 27: 1, 31: 1, 1: 1}),
        ]
    )
    profile_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            _build_matrix_row(["2", "NGUYEN THANH TR", "Not Set1"], {}),
            _build_matrix_row(["", "", ""], {26: "08:15\n12:00", 27: "13:05\n17:30"}),
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
            ["2", "NGUYEN THANH TR", "Not Set1", 0, 0],
        ]
    )
    checkin_report_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", "Ngay", "Gio vao", "Gio ra"],
            ["2", "NGUYEN THANH TR", "Not Set1", "2026-03-26", "08:15", "12:00"],
            ["2", "NGUYEN THANH TR", "Not Set1", "2026-03-27", "13:05", "17:30"],
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

    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "Leave Request,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,Cá nhân,01/02/2026 8:00 AM (GMT+7) → 5:30 PM,1,Approved",
            "Leave Request,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,Cá nhân,03/26/2026 12:00 PM (GMT+7) → 5:30 PM,0.5,Approved",
            "Leave Request,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,Cá nhân,03/27/2026 8:00 AM (GMT+7) → 1:00 PM,0.5,Approved",
            "Leave Request,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,Cá nhân,03/31/2026 8:30 AM (GMT+7) → 12:00 PM,0.5,Approved",
            "Leave Request,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,Cá nhân,04/01/2026 12:00 PM (GMT+7) → 5:30 PM,0.5,Approved",
        ]
    ).encode("utf-8")

    response = client.post(
        "/api/import/attendance-json",
        files={
            "file": (
                "attendance_half_day.xlsx",
                workbook_stream,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "notion_file": ("leave_request.csv", notion_csv, "text/csv"),
        },
        data={"period_start": "2026-03-23"},
    )

    assert response.status_code == 200
    payload = response.json()
    employee = payload["employees"][0]
    details = employee["attendance_details"]

    assert details["2026-03-26"]["attendance_symbol"] == "X/P"
    assert details["2026-03-27"]["attendance_symbol"] == "P/X"
    assert details["2026-03-31"]["attendance_symbol"] == "P/Ro"
    assert details["2026-04-01"]["attendance_symbol"] == "Ro/P"
    assert "2026-01-02" not in details


def test_import_attendance_json_keeps_full_day_symbol_when_leave_units_are_1_day(client):
    cycle_days = _build_cycle_days()
    schedule_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            _build_matrix_row(["61", "kimkt", "Accounting"], {13: 1, 22: 1}),
        ]
    )
    profile_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            _build_matrix_row(["61", "kimkt", "Accounting"], {}),
            _build_matrix_row(["", "", ""], {13: "07:46", 22: "18:12"}),
        ]
    )
    abnormal_df = pd.DataFrame(
        [
            ["ID", "Ngay", "Buoi 1 Vao lam", "Buoi 1 Ra nghi", "Thoi gian tre", "Thoi gian som"],
            ["61", "2026-04-13", "07:46", "Bỏ lỡ", 0, 0],
            ["61", "2026-04-22", "18:12", "Bỏ lỡ", 0, 0],
        ]
    )
    summary_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", "Tong so phut di muon trong thang", "Tong so ngay vang mat"],
            ["61", "kimkt", "Accounting", 0, 0],
        ]
    )
    checkin_report_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", "Ngay", "Gio vao", "Gio ra"],
            ["61", "kimkt", "Accounting", "2026-04-13", "07:46", ""],
            ["61", "kimkt", "Accounting", "2026-04-22", "18:12", ""],
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

    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "Leave Request,kimkt,kimkt,Đau ốm,04/13/2026 12:00 PM (GMT+7) → 5:30 PM,1.0,Approved",
            "Leave Request,kimkt,kimkt,Cá nhân,04/22/2026 8:00 AM (GMT+7) → 1:00 PM,1.0,Approved",
        ]
    ).encode("utf-8")

    response = client.post(
        "/api/import/attendance-json",
        files={
            "file": (
                "attendance_half_day_fallback.xlsx",
                workbook_stream,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "notion_file": ("leave_request.csv", notion_csv, "text/csv"),
        },
        data={"period_start": "2026-03-23"},
    )

    assert response.status_code == 200
    payload = response.json()
    employee = payload["employees"][0]
    details = employee["attendance_details"]

    assert details["2026-04-13"]["attendance_symbol"] == "X/P"
    assert details["2026-04-22"]["attendance_symbol"] == "P/X"


def test_import_attendance_json_marks_work_symbol_when_full_day_notion_leave_overlaps_attendance(client):
    cycle_days = _build_cycle_days()
    schedule_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            _build_matrix_row(["2", "NGUYEN THANH TR", "Not Set1"], {8: 1, 9: 1, 10: 1}),
        ]
    )
    profile_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            _build_matrix_row(["2", "NGUYEN THANH TR", "Not Set1"], {}),
            _build_matrix_row(["", "", ""], {8: "08:53", 9: "08:37\n18:08", 10: "08:35\n16:13"}),
        ]
    )
    abnormal_df = pd.DataFrame(
        [
            ["ID", "Ngay", "Buoi 1 Vao lam", "Buoi 1 Ra nghi", "Thoi gian tre", "Thoi gian som"],
            ["2", "2026-04-08", "08:53", "Bỏ lỡ", 0, 0],
            ["2", "2026-04-09", "08:37", "18:08", 0, 0],
            ["2", "2026-04-10", "08:35", "16:13", 0, 107],
        ]
    )
    summary_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", "Tong so phut di muon trong thang", "Tong so ngay vang mat"],
            ["2", "NGUYEN THANH TR", "Not Set1", 0, 0],
        ]
    )
    checkin_report_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", "Ngay", "Gio vao", "Gio ra"],
            ["2", "NGUYEN THANH TR", "Not Set1", "2026-04-08", "08:53", ""],
            ["2", "NGUYEN THANH TR", "Not Set1", "2026-04-09", "08:37", "18:08"],
            ["2", "NGUYEN THANH TR", "Not Set1", "2026-04-10", "08:35", "16:13"],
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

    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "Leave Request,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,Cá nhân,04/08/2026 12:00 AM (GMT+7) → 04/10/2026 5:00 PM (GMT+7),3.0,Approved",
        ]
    ).encode("utf-8")

    response = client.post(
        "/api/import/attendance-json",
        files={
            "file": (
                "attendance_leave_overlap.xlsx",
                workbook_stream,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "notion_file": ("leave_request.csv", notion_csv, "text/csv"),
        },
        data={"period_start": "2026-03-23"},
    )

    assert response.status_code == 200
    payload = response.json()
    employee = payload["employees"][0]
    details = employee["attendance_details"]

    assert details["2026-04-08"]["attendance_symbol"] == "X/P"
    assert details["2026-04-08"]["status"] == "Notion_Submitted"
    assert details["2026-04-08"]["notion_submitted"] is True
    assert details["2026-04-09"]["attendance_symbol"] == "X"
    assert details["2026-04-09"]["status"] == "Normal"
    assert details["2026-04-10"]["attendance_symbol"] == "X"
    assert details["2026-04-10"]["status"] == "Normal"
