from datetime import date

from app.services.notion_leave_reconciliation import reconcile_attendance_with_notion


def test_reconcile_attendance_with_notion_accepts_legacy_leave_forms_and_counts_wfh_as_work():
    attendance_json = [
        {
            "employee_id": "2",
            "employee_name": "NGUYEN THANH TR",
            "department": "Not Set1",
                "attendance_details": {
                    "2026-03-27": {"status": "Absent", "check_in": None, "check_out": None},
                    "2026-03-30": {"status": "Absent", "check_in": None, "check_out": None},
            },
        }
    ]

    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "New submission,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,Cá nhân,03/27/2026 8:00 AM (GMT+7) → 5:30 PM,1,Approved",
            "Work From Home,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,,03/30/2026 8:00 AM (GMT+7) → 5:30 PM,0,Approved",
        ]
    ).encode("utf-8")

    reconciled = reconcile_attendance_with_notion(attendance_json, notion_csv)
    details = reconciled[0]["attendance_details"]

    assert details["2026-03-27"]["attendance_symbol"] == "P"
    assert details["2026-03-27"]["status"] == "Notion_Submitted"
    assert details["2026-03-30"]["attendance_symbol"] == "X"
    assert details["2026-03-30"]["status"] == "Work_From_Home"
    assert details["2026-03-30"]["notion_work_from_home"] is True


def test_reconcile_attendance_with_notion_prefers_employee_column_when_leave_balance_is_not_a_name():
    attendance_json = [
        {
            "employee_id": "2",
            "employee_name": "NGUYEN THANH TR",
            "department": "Not Set1",
            "attendance_details": {
                "2026-03-27": {"status": "Absent", "check_in": None, "check_out": None},
            },
        }
    ]

    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "Leave Request,DOCS - NGUYEN THANH TR,11.5,Cá nhân,03/27/2026 8:00 AM (GMT+7) → 5:30 PM,1,Approved",
        ]
    ).encode("utf-8")

    reconciled = reconcile_attendance_with_notion(attendance_json, notion_csv)
    details = reconciled[0]["attendance_details"]

    assert details["2026-03-27"]["attendance_symbol"] == "P"
    assert details["2026-03-27"]["status"] == "Notion_Submitted"


def test_reconcile_attendance_with_notion_matches_truncated_machine_name():
    attendance_json = [
        {
            "employee_id": "2",
            "employee_name": "NGUYEN THANH TR",
            "department": "Not Set1",
            "attendance_details": {
                "2026-03-27": {"status": "Absent", "check_in": None, "check_out": None},
            },
        }
    ]

    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "Leave Request,DOCS - NGUYEN THANH TRI,DOCS - NGUYEN THANH TRI,Cá nhân,03/27/2026 8:00 AM (GMT+7) → 5:30 PM,1,Approved",
        ]
    ).encode("utf-8")

    reconciled = reconcile_attendance_with_notion(attendance_json, notion_csv)
    details = reconciled[0]["attendance_details"]

    assert details["2026-03-27"]["attendance_symbol"] == "P"
    assert details["2026-03-27"]["status"] == "Notion_Submitted"


def test_reconcile_attendance_with_notion_uses_employee_directory_mapping_before_name_match():
    attendance_json = [
        {
            "employee_id": "E902",
            "employee_name": "MAY CHAM CONG 902",
            "department": "Operations",
            "attendance_details": {
                "2026-03-27": {"status": "Absent", "check_in": None, "check_out": None},
            },
        }
    ]

    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "Leave Request,DOCS - PARADO QUANG,DOCS - PARADO QUANG,Cá nhân,03/27/2026 8:00 AM (GMT+7) → 5:30 PM,1,Approved",
        ]
    ).encode("utf-8")

    reconciled = reconcile_attendance_with_notion(
        attendance_json,
        notion_csv,
        {"DOCS - PARADO QUANG": "E902"},
    )
    details = reconciled[0]["attendance_details"]

    assert details["2026-03-27"]["attendance_symbol"] == "P"
    assert details["2026-03-27"]["status"] == "Notion_Submitted"


def test_reconcile_attendance_with_notion_marks_half_day_leave_sessions_from_notion_time_range():
    attendance_json = [
        {
            "employee_id": "2",
            "employee_name": "NGUYEN THANH TR",
            "department": "Not Set1",
            "attendance_details": {
                "2026-03-27": {"status": "Normal", "check_in": "13:05", "check_out": "17:30"},
                "2026-03-30": {"status": "Normal", "check_in": "08:15", "check_out": "12:00"},
                "2026-03-31": {"status": "Absent", "check_in": None, "check_out": None},
                "2026-04-01": {"status": "Absent", "check_in": None, "check_out": None},
            },
        }
    ]

    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "Leave Request,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,Cá nhân,03/27/2026 8:00 AM (GMT+7) → 1:00 PM,0.5,Approved",
            "Leave Request,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,Cá nhân,03/30/2026 12:00 PM (GMT+7) → 5:30 PM,0.5,Approved",
            "Leave Request,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,Cá nhân,03/31/2026 8:30 AM (GMT+7) → 12:00 PM,0.5,Approved",
            "Leave Request,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,Cá nhân,04/01/2026 12:00 PM (GMT+7) → 6:00 PM,0.5,Approved",
        ]
    ).encode("utf-8")

    reconciled = reconcile_attendance_with_notion(attendance_json, notion_csv)
    details = reconciled[0]["attendance_details"]

    assert details["2026-03-27"]["attendance_symbol"] == "P/X"
    assert details["2026-03-27"]["status"] == "Notion_Submitted"
    assert details["2026-03-30"]["attendance_symbol"] == "X/P"
    assert details["2026-03-30"]["status"] == "Notion_Submitted"
    assert details["2026-03-31"]["attendance_symbol"] == "P/Ro"
    assert details["2026-03-31"]["status"] == "Notion_Submitted"
    assert details["2026-04-01"]["attendance_symbol"] == "Ro/P"
    assert details["2026-04-01"]["status"] == "Notion_Submitted"


def test_reconcile_attendance_with_notion_skips_dates_outside_selected_period():
    attendance_json = [
        {
            "employee_id": "2",
            "employee_name": "NGUYEN THANH TR",
            "department": "Not Set1",
            "attendance_details": {
                "2026-03-27": {"status": "Absent", "check_in": None, "check_out": None},
            },
        }
    ]

    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "Leave Request,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,Cá nhân,01/02/2026 8:00 AM (GMT+7) → 5:30 PM,1,Approved",
            "Leave Request,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,Cá nhân,03/27/2026 8:00 AM (GMT+7) → 5:30 PM,1,Approved",
        ]
    ).encode("utf-8")

    reconciled = reconcile_attendance_with_notion(
        attendance_json,
        notion_csv,
        period_start=date(2026, 3, 23),
        period_end=date(2026, 4, 22),
    )
    details = reconciled[0]["attendance_details"]

    assert "2026-01-02" not in details
    assert details["2026-03-27"]["attendance_symbol"] == "P"


def test_reconcile_attendance_with_notion_keeps_full_day_symbol_when_leave_units_are_1_day():
    attendance_json = [
        {
            "employee_id": "61",
            "employee_name": "kimkt",
            "department": "Accounting",
            "attendance_details": {
                "2026-04-13": {"status": "Missing_Punch", "check_in": "07:46", "check_out": None},
                "2026-04-22": {"status": "Missing_Punch", "check_in": "18:12", "check_out": None},
            },
        }
    ]

    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "Leave Request,ACCT - RIN KIM,ACCT - RIN KIM,Đau ốm,04/13/2026 12:00 PM (GMT+7) → 5:30 PM,1.0,Approved",
            "Leave Request,ACCT - RIN KIM,ACCT - RIN KIM,Cá nhân,04/22/2026 8:00 AM (GMT+7) → 1:00 PM,1.0,Approved",
        ]
    ).encode("utf-8")

    reconciled = reconcile_attendance_with_notion(
        attendance_json,
        notion_csv,
        {"RIN KIM": "61"},
        period_start=date(2026, 3, 23),
        period_end=date(2026, 4, 22),
    )
    details = reconciled[0]["attendance_details"]

    assert details["2026-04-13"]["attendance_symbol"] == "X/P"
    assert details["2026-04-13"]["status"] == "Notion_Submitted"
    assert details["2026-04-22"]["attendance_symbol"] == "P/X"
    assert details["2026-04-22"]["status"] == "Notion_Submitted"


def test_reconcile_attendance_with_notion_ignores_zero_day_rows():
    attendance_json = [
        {
            "employee_id": "43",
            "employee_name": "DIEU",
            "department": "Accounting",
            "attendance_details": {
                "2026-03-27": {"status": "Absent", "check_in": None, "check_out": None},
            },
        }
    ]

    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "Leave Request,DIEU,DIEU,Cá nhân,03/27/2026 8:00 AM (GMT+7) → 5:00 PM,0.0,Need Review",
        ]
    ).encode("utf-8")

    reconciled = reconcile_attendance_with_notion(
        attendance_json,
        notion_csv,
        period_start=date(2026, 3, 23),
        period_end=date(2026, 4, 22),
    )
    details = reconciled[0]["attendance_details"]

    assert details["2026-03-27"].get("attendance_symbol") is None
    assert details["2026-03-27"].get("notion_submitted") is None


def test_reconcile_attendance_with_notion_marks_attendance_as_work_when_full_day_leave_overlaps_machine_logs():
    attendance_json = [
        {
            "employee_id": "2",
            "employee_name": "NGUYEN THANH TR",
            "department": "Not Set1",
            "attendance_details": {
                "2026-04-08": {"status": "Missing_Punch", "check_in": "08:53", "check_out": None},
                "2026-04-09": {"status": "Normal", "check_in": "08:37", "check_out": "18:08"},
                "2026-04-10": {"status": "Normal", "check_in": "08:35", "check_out": "16:13"},
            },
        }
    ]

    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "Leave Request,DOCS - NGUYEN THANH TR,DOCS - NGUYEN THANH TR,Cá nhân,04/08/2026 12:00 AM (GMT+7) → 04/10/2026 5:00 PM (GMT+7),3.0,Approved",
        ]
    ).encode("utf-8")

    reconciled = reconcile_attendance_with_notion(
        attendance_json,
        notion_csv,
        period_start=date(2026, 3, 23),
        period_end=date(2026, 4, 22),
    )
    details = reconciled[0]["attendance_details"]

    assert details["2026-04-08"]["attendance_symbol"] == "X/P"
    assert details["2026-04-08"]["status"] == "Notion_Submitted"
    assert details["2026-04-08"]["notion_submitted"] is True
    assert details["2026-04-08"]["notion_status"] == "Approved"
    assert details["2026-04-09"]["attendance_symbol"] == "X"
    assert details["2026-04-09"]["status"] == "Normal"
    assert details["2026-04-10"]["attendance_symbol"] == "X"
    assert details["2026-04-10"]["status"] == "Normal"


def test_reconcile_attendance_with_pending_notion_leave_prevents_absence_mark():
    attendance_json = [
        {
            "employee_id": "26",
            "employee_name": "NGUYEN THANH DAT",
            "department": "SALE",
            "attendance_details": {
                "2026-07-06": {"status": "Absent", "attendance_symbol": "V"},
            },
        }
    ]
    notion_csv = "\n".join(
        [
            "Name,TÃªn nhÃ¢n viÃªn,Leave Balance,LÃ½ do Nghá»‰,Thá»i Gian,Sá»‘ NgÃ y Nghá»‰,Tráº¡ng ThÃ¡i",
            "Leave Request,IT - TOMMY DAT,IT - TOMMY DAT,Viá»‡c gia Ä‘Ã¬nh,07/06/2026 8:30 AM (GMT+7) â†’ 5:30 PM,1,Under Review",
        ]
    ).encode("utf-8")

    # ASCII aliases keep this regression fixture independent of the source
    # encoding of Vietnamese column captions.
    notion_csv = (
        b"Name,Ten nhan vien,Leave Balance,Ly do Nghi,Thoi Gian,So Ngay Nghi,Trang Thai\n"
        b"Leave Request,IT - TOMMY DAT,IT - TOMMY DAT,Viec gia dinh,07/06/2026 8:30 AM (GMT+7) -> 5:30 PM,1,Under Review\n"
    )
    reconciled = reconcile_attendance_with_notion(
        attendance_json,
        notion_csv,
        {"TOMMY DAT": "26"},
        period_start=date(2026, 6, 23),
        period_end=date(2026, 7, 22),
    )

    detail = reconciled[0]["attendance_details"]["2026-07-06"]
    assert detail["attendance_symbol"] == "P"
    assert detail["status"] == "Notion_Submitted"
    assert detail["notion_submitted"] is True
    assert detail["notion_status"] == "Under Review"


def test_reconcile_uses_time_range_to_select_the_active_attendance_cycle():
    attendance_json = [
        {
            "employee_id": "26",
            "employee_name": "NGUYEN THANH DAT",
            "department": "SALE",
            "attendance_details": {
                "2025-07-06": {"status": "Absent", "attendance_symbol": "V"},
                "2026-07-06": {"status": "Absent", "attendance_symbol": "V"},
            },
        }
    ]
    # The historical row has the same month/day as the current row.  The
    # active period must choose only 2026-07-06; ``07/06`` is MM/DD here.
    notion_csv = (
        b"Name,Ten nhan vien,Leave Balance,Ly do Nghi,Thoi Gian,So Ngay Nghi,Trang Thai\n"
        b"Leave Request,IT - TOMMY DAT,IT - TOMMY DAT,Viec gia dinh,07/06/2025 8:30 AM (GMT+7) -> 5:30 PM,1,Approved\n"
        b"Leave Request,IT - TOMMY DAT,IT - TOMMY DAT,Viec gia dinh,07/06/2026 8:30 AM (GMT+7) -> 5:30 PM,1,Under Review\n"
    )

    reconciled = reconcile_attendance_with_notion(
        attendance_json,
        notion_csv,
        {"TOMMY DAT": "26"},
        period_start=date(2026, 6, 23),
        period_end=date(2026, 7, 22),
    )

    details = reconciled[0]["attendance_details"]
    assert details["2025-07-06"]["attendance_symbol"] == "V"
    assert details["2026-07-06"]["attendance_symbol"] == "P"
    assert details["2026-07-06"]["notion_status"] == "Under Review"


def test_reconcile_keeps_machine_absence_when_notion_request_is_rejected():
    attendance_json = [
        {
            "employee_id": "26",
            "employee_name": "NGUYEN THANH DAT",
            "attendance_details": {
                "2026-07-06": {"status": "Absent", "attendance_symbol": "V"},
            },
        }
    ]
    notion_csv = (
        b"Name,Ten nhan vien,Leave Balance,Ly do Nghi,Thoi Gian,So Ngay Nghi,Trang Thai\n"
        b"Leave Request,IT - TOMMY DAT,IT - TOMMY DAT,Viec gia dinh,07/06/2026 8:30 AM (GMT+7) -> 5:30 PM,1,Rejected\n"
    )

    reconciled = reconcile_attendance_with_notion(
        attendance_json,
        notion_csv,
        {"TOMMY DAT": "26"},
        period_start=date(2026, 6, 23),
        period_end=date(2026, 7, 22),
    )

    detail = reconciled[0]["attendance_details"]["2026-07-06"]
    assert detail["attendance_symbol"] == "V"
    assert detail["notion_submitted"] is False
    assert detail["notion_status"] == "Rejected"


def test_reconcile_attendance_with_vietnamese_date_format_and_single_digits():
    attendance_json = [
        {
            "employee_id": "4",
            "employee_name": "BOO BAO",
            "department": "Not Set1",
            "attendance_details": {
                "2026-06-05": {"status": "Normal", "check_in": "08:57", "check_out": "13:02"},
                "2026-06-19": {"status": "Normal", "check_in": "08:51", "check_out": "13:16"},
            },
        }
    ]

    notion_csv = "\n".join(
        [
            "Name,Tên nhân viên,Leave Balance,Lý do Nghỉ,Thời Gian,Số Ngày Nghỉ,Trạng Thái",
            "Leave Request,BOO BAO,BOO BAO,Cá nhân,5/6/2026 8:00 AM (GMT+7) → 12:00 PM,0.5,Approved",
            "Leave Request,BOO BAO,BOO BAO,Cá nhân,19/06/2026 12:00 PM (GMT+7) → 5:30 PM,0.5,Approved",
        ]
    ).encode("utf-8")

    reconciled = reconcile_attendance_with_notion(
        attendance_json,
        notion_csv,
        period_start=date(2026, 5, 23),
        period_end=date(2026, 6, 22),
    )
    details = reconciled[0]["attendance_details"]

    assert details["2026-06-05"]["attendance_symbol"] == "P/X"
    assert details["2026-06-19"]["attendance_symbol"] == "X/P"

