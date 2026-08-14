from datetime import date
from pathlib import Path

import pandas as pd

from app.services.attendance_parser import AttendanceParser


def _build_cycle_days() -> list[int]:
    return list(range(23, 32)) + list(range(1, 23))


def _build_matrix_row(prefix: list[object], values_by_day: dict[int, object]) -> list[object]:
    cycle_days = _build_cycle_days()
    return prefix + [values_by_day.get(day, "") for day in cycle_days]


def test_attendance_parser_merges_five_sheets_into_clean_json(tmp_path: Path):
    workbook_path = tmp_path / "attendance_full_cycle.xlsx"
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
            _build_matrix_row(
                ["", "", ""],
                {
                    23: "08:15\n17:30",
                    24: "08:45*\n17:30",
                    26: "08:15",
                },
            ),
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

    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        schedule_df.to_excel(writer, index=False, header=False, sheet_name="Bảng thông tin lịch trình")
        checkin_report_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo check-in")
        abnormal_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo bất thường")
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Hồ sơ check-in")
        summary_df.to_excel(writer, index=False, header=False, sheet_name="Bảng tóm tắt check-in")

    parser = AttendanceParser()
    payload = parser.parse(workbook_path)

    assert len(payload) == 1
    employee = payload[0]
    assert employee["employee_id"] == "2"
    assert employee["employee_name"] == "NGUYEN THANH TR"
    assert employee["department"] == "Not Set1"
    assert employee["summary_from_machine"] == {"total_late_minutes": 1050, "total_absent_days": 8}

    details = employee["attendance_details"]
    assert details["2026-03-23"] == {
        "scheduled_to_work": True,
        "check_in": "08:15",
        "check_out": "17:30",
        "status": "Normal",
        "late_minutes": 0,
    }
    assert details["2026-03-24"] == {
        "scheduled_to_work": True,
        "check_in": "08:45",
        "check_out": "17:30",
        "status": "Normal",
        "late_minutes": 15,
    }
    assert details["2026-03-26"] == {
        "scheduled_to_work": True,
        "check_in": "08:15",
        "check_out": None,
        "status": "Missing_Punch",
        "late_minutes": 0,
    }
    assert details["2026-03-27"] == {
        "scheduled_to_work": True,
        "check_in": None,
        "check_out": None,
        "status": "Absent",
        "late_minutes": 0,
    }

    assert parser.last_validation_summary["2"] == {
        "computed_total_late_minutes": 15,
        "computed_total_absent_days": 1,
        "machine_total_late_minutes": 1050,
        "machine_total_absent_days": 8,
        "late_minutes_match": False,
        "absent_days_match": False,
    }


def test_attendance_parser_handles_real_machine_workbook_layout(tmp_path: Path):
    workbook_path = tmp_path / "attendance_real_layout.xlsx"
    cycle_days = _build_cycle_days()
    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] * 5

    schedule_df = pd.DataFrame(
        [
            ["Bảng thông tin lịch trình", "", "", *([""] * len(cycle_days))],
            ["Lưu ý", "", "", *([""] * len(cycle_days))],
            ["Ngày ：", "2026-03-23 ~ 2026-04-22", "", *([""] * len(cycle_days))],
            ["ID", "Tên", "P.Ban", *cycle_days],
            ["", "", "", *weekday_labels[: len(cycle_days)]],
            ["2", "NGUYEN THANH TR", "Not Set1", *[1 if day in {23, 24, 26, 27} else "" for day in cycle_days]],
        ]
    )

    profile_df = pd.DataFrame(
        [
            ["Hồ sơ check-in", "", "", *([""] * (len(cycle_days) - 1))],
            *[[""] * (len(cycle_days) + 3)],
            ["Ngày ：", "", "2026-03-23 ~ 2026-04-22", *([""] * (len(cycle_days)))],
            cycle_days,
            ["ID:", "", "2", "", "", "", "", "Tên ：", "", "NGUYEN THANH TR", "", "", "", "", "", "P.Ban:", "", "Not Set1", *([""] * (len(cycle_days) - 15))],
            [
                "08:15\n17:30\n",
                "08:45*\n17:30\n",
                "",
                "08:15\n",
                "",
                *([""] * (len(cycle_days) - 5)),
            ],
        ]
    )

    abnormal_df = pd.DataFrame(
        [
            ["Báo cáo bất thường", "", "", "", "", "", "", "", "", "", "", ""],
            ["Ngày ：", "2026-03-23 ~ 2026-04-22", "", "", "", "", "", "", "", "", "", ""],
            ["Lưu ý", "", "", "", "", "", "", "", "", "", "", ""],
            ["ID", "Tên", "P.Ban", "Ngày", "Buổi 1", "", "Buổi 2", "", "Thời gian trễ", "Thời gian sớm", "Tổng cộng", "Ghi chú"],
            ["", "", "", "", "Vào làm", "Ra nghỉ", "Vào làm", "Ra nghỉ", "", "", "", ""],
            ["2", "NGUYEN THANH TR", "Not Set1", "2026-03-24", "08:45", "17:30", "", "", 15, 0, 15, ""],
            ["2", "NGUYEN THANH TR", "Not Set1", "2026-03-26", "08:15", "Bỏ lỡ", "", "", 0, 0, 0, ""],
            ["2", "NGUYEN THANH TR", "Not Set1", "2026-03-27", "Bỏ lỡ", "Bỏ lỡ", "", "", 0, 0, 0, ""],
        ]
    )

    summary_df = pd.DataFrame(
        [
            ["Bảng tóm tắt check-in", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["Ngày ：", "2026-03-23 ~ 2026-04-22", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["ID", "Tên", "P.Ban", "Giờ làm", "", "Đi muộn", "", "Nghỉ sớm", "", "Giờ tăng ca", "", "Check-in (Tiêu chuẩn / Thực tế)", "Vắng mặt", "Nghỉ", "Công tác", "Lương bổ sung", "", ""],
            ["", "", "", "Tiêu chuẩn", "Thực tế", "Thời gian", "Phút", "Thời gian", "Phút", "Bình thường", "Đặc biệt", "", "", "", "", "Chú thích", "Tăng ca", "Phụ cấp"],
            ["2", "NGUYEN THANH TR", "Not Set1", "294:30", "181:11", "23", "1050", "8", "672", "00:00", "0", "31/23", "8", "0", "0", "", "", ""],
        ]
    )

    checkin_report_df = pd.DataFrame(
        [
            ["Báo cáo check-in", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["Công ty:CÔNG TY TNHH SEALINK INTERNATIONAL", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["ID:2", "", "Tên:NGUYEN THANH TR", "", "", "", "Phòng ban:Not Set1", "", "", "", "Lịch trình:P.Ban", "", "", "Ngày:2026-03-23 ~ 2026-04-22", "", ""],
            ["Ngày làm:31", "", "Ngày check-in:23", "", "Đi muộn:23", "", "Nghỉ sớm:8", "", "Ngày vắng:8", "", "Giờ tăng ca:00:00", "", "Nghỉ (ngày):0", "", "Công tác (ngày):0", ""],
            ["Lương ngày:", "", "", "Lương ngoài giờ:", "", "", "Phụ cấp khác:", "", "", "Khoản khấu trừ:", "", "", "Lương thực tế:", "", "", ""],
            ["Số thiết bị:1", "", "Buổi 1", "", "Buổi 2", "", "Tăng ca", "", "", "", "Buổi 1", "", "Buổi 2", "", "Tăng ca", ""],
            ["Ngày", "Tuần", "Vào làm", "Ra nghỉ", "Vào làm", "Ra nghỉ", "Vào làm", "Ra nghỉ", "Ngày", "Tuần", "Vào làm", "Ra nghỉ", "Vào làm", "Ra nghỉ", "Vào làm", "Ra nghỉ"],
            ["03-23", "Thứ hai", "08:15*", "17:30", "", "", "", "", "04-08", "Thứ tư", "", "", "", "", "", ""],
        ]
    )

    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        schedule_df.to_excel(writer, index=False, header=False, sheet_name="Bảng thông tin lịch trình")
        checkin_report_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo check-in")
        abnormal_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo bất thường")
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Hồ sơ check-in")
        summary_df.to_excel(writer, index=False, header=False, sheet_name="Bảng tóm tắt check-in")

    parser = AttendanceParser()
    payload = parser.parse(workbook_path)

    assert len(payload) == 1
    employee = payload[0]
    assert employee["employee_id"] == "2"
    assert employee["employee_name"] == "NGUYEN THANH TR"
    assert employee["department"] == "Not Set1"
    assert employee["summary_from_machine"] == {"total_late_minutes": 1050, "total_absent_days": 8}
    assert employee["attendance_details"]["2026-03-24"] == {
        "scheduled_to_work": True,
        "check_in": "08:45",
        "check_out": "17:30",
        "status": "Normal",
        "late_minutes": 15,
    }
    assert employee["attendance_details"]["2026-03-26"] == {
        "scheduled_to_work": True,
        "check_in": "08:15",
        "check_out": None,
        "status": "Missing_Punch",
        "late_minutes": 0,
    }
    assert employee["attendance_details"]["2026-03-27"] == {
        "scheduled_to_work": True,
        "check_in": None,
        "check_out": None,
        "status": "Absent",
        "late_minutes": 0,
    }


def test_attendance_parser_reads_times_from_combined_abnormal_columns_and_skips_weekends(tmp_path: Path):
    workbook_path = tmp_path / "attendance_abnormal_combined_header.xlsx"
    cycle_days = _build_cycle_days()

    schedule_df = pd.DataFrame(
        [
            ["Bảng thông tin lịch trình", "", "", *( [""] * len(cycle_days) )],
            ["ID", "Tên", "P.Ban", *cycle_days],
            ["", "", "", *([""] * len(cycle_days))],
            ["2", "NGUYEN THANH TR", "Not Set1", *[1 if day in {23, 24, 25, 26, 27} else "" for day in cycle_days]],
        ]
    )

    profile_df = pd.DataFrame([["ID", "Ten", "Phong ban", *cycle_days], ["2", "NGUYEN THANH TR", "Not Set1", *["" for _ in cycle_days]]])
    abnormal_df = pd.DataFrame(
        [
            ["Báo cáo bất thường", "", "", "", "", "", "", "", "", "", "", ""],
            ["Ngày ：", "2026-03-23 ~ 2026-04-22", "", "", "", "", "", "", "", "", "", ""],
            ["Lưu ý", "", "", "", "", "", "", "", "", "", "", ""],
            ["ID", "Tên", "P.Ban", "Ngày", "Buổi 1", "", "Buổi 2", "", "Thời gian trễ", "Thời gian sớm", "Tổng cộng", "Ghi chú"],
            ["", "", "", "", "Vào làm", "Ra nghỉ", "Vào làm", "Ra nghỉ", "", "", "", ""],
            ["2", "NGUYEN THANH TR", "Not Set1", "2026-03-23", "08:16", "16:16", "", "", 16, 74, 90, ""],
            ["2", "NGUYEN THANH TR", "Not Set1", "2026-03-24", "11:21", "21:02", "", "", 201, 0, 201, ""],
            ["2", "NGUYEN THANH TR", "Not Set1", "2026-03-28", "Bỏ lỡ", "Bỏ lỡ", "", "", 0, 0, 0, ""],
        ]
    )
    summary_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", "Tong so phut di muon trong thang", "Tong so ngay vang mat"],
            ["2", "NGUYEN THANH TR", "Not Set1", 217, 0],
        ]
    )
    checkin_report_df = pd.DataFrame([["ID", "Ten", "Phong ban", "Ngay", "Gio vao", "Gio ra"]])

    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        schedule_df.to_excel(writer, index=False, header=False, sheet_name="Bảng thông tin lịch trình")
        checkin_report_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo check-in")
        abnormal_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo bất thường")
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Hồ sơ check-in")
        summary_df.to_excel(writer, index=False, header=False, sheet_name="Bảng tóm tắt check-in")

    parser = AttendanceParser()
    payload = parser.parse(workbook_path)

    details = payload[0]["attendance_details"]
    assert details["2026-03-23"] == {
        "scheduled_to_work": True,
        "check_in": "08:16",
        "check_out": "16:16",
        "status": "Normal",
        "late_minutes": 16,
    }
    assert details["2026-03-24"] == {
        "scheduled_to_work": True,
        "check_in": "11:21",
        "check_out": "21:02",
        "status": "Normal",
        "late_minutes": 201,
    }
    assert "2026-03-29" not in details


def test_attendance_parser_reads_block_style_checkin_report_days(tmp_path: Path):
    workbook_path = tmp_path / "attendance_checkin_report_block.xlsx"
    cycle_days = _build_cycle_days()

    schedule_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            ["7", "VO THI BICH", "Not Set1", *[1 if day in {23, 24, 25, 26, 27, 11, 12} else "" for day in cycle_days]],
        ]
    )
    profile_df = pd.DataFrame([["ID", "Ten", "Phong ban", *cycle_days], ["7", "VO THI BICH", "Not Set1", *["" for _ in cycle_days]]])
    abnormal_df = pd.DataFrame([["ID", "Ngay", "Buoi 1 Vao lam", "Buoi 1 Ra nghi", "Thoi gian tre", "Thoi gian som"]])
    summary_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", "Tong so phut di muon trong thang", "Tong so ngay vang mat"],
            ["7", "VO THI BICH", "Not Set1", 0, 0],
        ]
    )
    checkin_report_df = pd.DataFrame(
        [
            ["Báo cáo check-in", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["Công ty:CÔNG TY TNHH SEALINK INTERNATIONAL", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["ID:7", "", "Tên:VO THI BICH", "", "", "", "Phòng ban:Not Set1", "", "", "", "Lịch trình:P.Ban", "", "", "Ngày:2026-02-23 ~ 2026-03-22", "", ""],
            ["Ngày làm:28", "", "Ngày check-in:19", "", "Đi muộn:18", "", "Nghỉ sớm:2", "", "Ngày vắng:9", "", "Giờ tăng ca:00:00", "", "Nghỉ (ngày):0", "", "Công tác (ngày):0", ""],
            ["Lương ngày:", "", "", "Lương ngoài giờ:", "", "", "Phụ cấp khác:", "", "", "Khoản khấu trừ:", "", "", "Lương thực tế:", "", "", ""],
            ["Số thiết bị:1", "", "Buổi 1", "", "Buổi 2", "", "Tăng ca", "", "", "", "Buổi 1", "", "Buổi 2", "", "Tăng ca", ""],
            ["Ngày", "Tuần", "Vào làm", "Ra nghỉ", "Vào làm", "Ra nghỉ", "Vào làm", "Ra nghỉ", "Ngày", "Tuần", "Vào làm", "Ra nghỉ", "Vào làm", "Ra nghỉ", "Vào làm", "Ra nghỉ"],
            ["02-23", "Thứ hai", "08:06", "18:13", "", "", "", "", "03-11", "Thứ tư", "08:12*", "18:26", "", "", "", ""],
            ["02-24", "Thứ ba", "08:22*", "18:18", "", "", "", "", "03-12", "Thứ năm", "08:29*", "17:58", "", "", "", ""],
        ]
    )

    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        schedule_df.to_excel(writer, index=False, header=False, sheet_name="Bảng thông tin lịch trình")
        checkin_report_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo check-in")
        abnormal_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo bất thường")
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Hồ sơ check-in")
        summary_df.to_excel(writer, index=False, header=False, sheet_name="Bảng tóm tắt check-in")

    parser = AttendanceParser()
    payload = parser.parse(workbook_path)

    assert len(payload) == 1
    details = payload[0]["attendance_details"]
    assert details["2026-02-23"] == {
        "scheduled_to_work": True,
        "check_in": "08:06",
        "check_out": "18:13",
        "status": "Normal",
        "late_minutes": 0,
    }
    assert details["2026-02-24"] == {
        "scheduled_to_work": True,
        "check_in": "08:22",
        "check_out": "18:18",
        "status": "Normal",
        "late_minutes": 0,
    }
    assert details["2026-03-11"] == {
        "scheduled_to_work": True,
        "check_in": "08:12",
        "check_out": "18:26",
        "status": "Normal",
        "late_minutes": 0,
    }


def test_attendance_parser_excludes_schedule_only_employees_from_result(tmp_path: Path):
    workbook_path = tmp_path / "attendance_schedule_only_employee.xlsx"
    cycle_days = _build_cycle_days()

    schedule_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            _build_matrix_row(["2", "NGUYEN THANH TR", "Not Set1"], {23: 1, 24: 1}),
            _build_matrix_row(["9", "LE VAN MOCK", "Kho Mock"], {23: 1, 24: 1}),
        ]
    )

    profile_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            _build_matrix_row(["2", "NGUYEN THANH TR", "Not Set1"], {}),
            _build_matrix_row(["", "", ""], {23: "08:15\n17:30", 24: "08:45\n17:30"}),
        ]
    )

    abnormal_df = pd.DataFrame(
        [
            ["ID", "Ngay", "Buoi 1 Vao lam", "Buoi 1 Ra nghi", "Thoi gian tre", "Thoi gian som"],
            ["2", "2026-03-24", "08:45", "17:30", 15, 0],
        ]
    )

    summary_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", "Tong so phut di muon trong thang", "Tong so ngay vang mat"],
            ["2", "NGUYEN THANH TR", "Not Set1", 15, 0],
            ["9", "LE VAN MOCK", "Kho Mock", 0, 0],
        ]
    )

    checkin_report_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", "Ngay", "Gio vao", "Gio ra"],
            ["2", "NGUYEN THANH TR", "Not Set1", "2026-03-23", "08:15", "17:30"],
        ]
    )

    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        schedule_df.to_excel(writer, index=False, header=False, sheet_name="Bảng thông tin lịch trình")
        checkin_report_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo check-in")
        abnormal_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo bất thường")
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Hồ sơ check-in")
        summary_df.to_excel(writer, index=False, header=False, sheet_name="Bảng tóm tắt check-in")

    parser = AttendanceParser()
    payload = parser.parse(workbook_path)

    assert len(payload) == 1
    assert payload[0]["employee_id"] == "2"
    assert payload[0]["employee_name"] == "NGUYEN THANH TR"


def test_attendance_parser_ignores_weekend_schedule_without_attendance(tmp_path: Path):
    workbook_path = tmp_path / "attendance_ignore_weekend_schedule.xlsx"
    cycle_days = _build_cycle_days()

    schedule_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            _build_matrix_row(["2", "NGUYEN THANH TR", "Not Set1"], {28: 1, 30: 1}),
        ]
    )

    profile_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", *cycle_days],
            _build_matrix_row(["2", "NGUYEN THANH TR", "Not Set1"], {}),
            _build_matrix_row(["", "", ""], {30: "08:15\n17:30"}),
        ]
    )

    abnormal_df = pd.DataFrame(
        [["ID", "Ngay", "Buoi 1 Vao lam", "Buoi 1 Ra nghi", "Thoi gian tre", "Thoi gian som"]]
    )
    summary_df = pd.DataFrame(
        [
            ["ID", "Ten", "Phong ban", "Tong so phut di muon trong thang", "Tong so ngay vang mat"],
            ["2", "NGUYEN THANH TR", "Not Set1", 0, 0],
        ]
    )
    checkin_report_df = pd.DataFrame([["ID", "Ten", "Phong ban", "Ngay", "Gio vao", "Gio ra"]])

    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        schedule_df.to_excel(writer, index=False, header=False, sheet_name="Bảng thông tin lịch trình")
        checkin_report_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo check-in")
        abnormal_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo bất thường")
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Hồ sơ check-in")
        summary_df.to_excel(writer, index=False, header=False, sheet_name="Bảng tóm tắt check-in")

    parser = AttendanceParser()
    payload = parser.parse(workbook_path, period_start=date(2026, 3, 23))

    assert len(payload) == 1
    details = payload[0]["attendance_details"]
    assert "2026-03-29" not in details
    assert details["2026-03-30"] == {
        "scheduled_to_work": True,
        "check_in": "08:15",
        "check_out": "17:30",
        "status": "Normal",
        "late_minutes": 0,
    }