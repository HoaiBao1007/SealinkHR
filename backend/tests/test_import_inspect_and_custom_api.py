import json
from io import BytesIO

import pandas as pd


def test_workbook_inspect_returns_sheet_metadata(client):
    profile_df = pd.DataFrame(
        [
            ["ID", "Ten", "Ngay", "Moc gio"],
            ["E001", "Nguyen Van A", "24/04/2026", "08:30;17:45"],
        ]
    )
    custom_df = pd.DataFrame(
        [
            ["Code", "Name", "Work Day", "Scan Data"],
            ["E002", "Nguyen Van B", "24/04/2026", "08:40;17:30"],
        ]
    )

    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Ho so check-in")
        custom_df.to_excel(writer, index=False, header=False, sheet_name="Custom Raw")
    stream.seek(0)

    files = {
        "file": (
            "inspect.xlsx",
            stream,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    response = client.post("/api/import/workbook-inspect", files=files, data={"import_type": "checkin"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["import_type"] == "checkin"
    assert payload["recommended_sheet_name"] == "Ho so check-in"
    assert len(payload["sheets"]) == 2
    assert payload["sheets"][0]["sheet_name"] == "Ho so check-in"
    assert payload["sheets"][0]["suggested_mapping"]["ID"] == 0



def test_custom_preview_accepts_user_mapping(client):
    custom_df = pd.DataFrame(
        [
            ["Code", "Name", "Work Day", "Scan Data"],
            ["E010", "Tran Thi C", "24/04/2026", "08:15;17:20"],
        ]
    )

    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        custom_df.to_excel(writer, index=False, header=False, sheet_name="Custom Raw")
    stream.seek(0)

    files = {
        "file": (
            "custom.xlsx",
            stream,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    data = {
        "import_type": "checkin",
        "sheet_name": "Custom Raw",
        "header_row_index": "0",
        "column_mapping_json": json.dumps({"ID": 0, "Ten": 1, "Ngay": 2, "Moc gio": 3}),
    }
    response = client.post("/api/import/custom-preview", files=files, data=data)

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == 1
    row = payload["preview"][0]
    assert row["machine_employee_id"] == "E010"
    assert row["full_name"] == "Tran Thi C"
    assert row["check_in_time"] == "08:15"
    assert row["check_out_time"] == "17:20"


def test_workbook_inspect_detects_header_row_after_title_line(client):
    profile_df = pd.DataFrame(
        [
            ["Bao cao check-in thang 04", "", "", ""],
            ["Ma nhan vien / Machine ID", "Ho va ten nhan vien", "Ngay lam viec", "Du lieu quet / Scan Data"],
            ["E001", "Nguyen Van A", "24/04/2026", "08:30\n17:45"],
        ]
    )
    abnormal_df = pd.DataFrame(
        [
            ["ID", "Ten", "Ngay"],
            ["E999", "Nguoi dung test", "24/04/2026"],
        ]
    )

    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Ho so check-in")
        abnormal_df.to_excel(writer, index=False, header=False, sheet_name="Bao cao bat thuong")
    stream.seek(0)

    files = {
        "file": (
            "inspect_title_row.xlsx",
            stream,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    response = client.post("/api/import/workbook-inspect", files=files, data={"import_type": "checkin"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_sheet_name"] == "Ho so check-in"
    assert payload["recommended_header_row_index"] == 1
    assert payload["recommended_mapping"]["ID"] == 0
    assert payload["recommended_mapping"]["Ten"] == 1
    assert payload["recommended_mapping"]["Ngay"] == 2
    assert payload["recommended_mapping"]["Moc gio"] == 3


def test_workbook_inspect_detects_and_returns_report_period(client):
    profile_df = pd.DataFrame(
        [
            ["Ngày: 2026-05-23 ~ 2026-06-22", "", "", ""],
            ["ID", "Ten", "Ngay", "Moc gio"],
            ["E001", "Nguyen Van A", "24/05/2026", "08:30;17:45"],
        ]
    )

    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Ho so check-in")
    stream.seek(0)

    response = client.post(
        "/api/import/workbook-inspect",
        files={"file": ("period.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"import_type": "checkin"},
    )

    assert response.status_code == 200
    selected_sheet = response.json()["sheets"][0]
    assert selected_sheet["period_start"] == "2026-05-23"
    assert selected_sheet["period_end"] == "2026-06-22"


def test_sheet_inspect_returns_real_labels_for_selected_header_row(client):
    profile_df = pd.DataFrame(
        [
            ["Bao cao check-in thang 04", "", "", ""],
            ["Ma nhan vien / Machine ID", "Ho va ten nhan vien", "Ngay lam viec", "Du lieu quet / Scan Data"],
            ["E001", "Nguyen Van A", "24/04/2026", "08:30\n17:45"],
        ]
    )

    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Ho so check-in")
    stream.seek(0)

    files = {
        "file": (
            "sheet_inspect.xlsx",
            stream,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    data = {
        "import_type": "checkin",
        "sheet_name": "Ho so check-in",
        "header_row_index": "1",
    }
    response = client.post("/api/import/sheet-inspect", files=files, data=data)

    assert response.status_code == 200
    payload = response.json()
    assert payload["header_row_index"] == 1
    assert payload["columns"][0]["label"] == "Ma nhan vien / Machine ID"
    assert payload["columns"][2]["label"] == "Ngay lam viec"
    assert payload["sample_rows"][0]["Ngay lam viec"] == "24/04/2026"
    assert payload["raw_rows"][0]["Ma nhan vien / Machine ID"] == "E001"
    assert payload["data_row_count"] == 1


def test_sheet_inspect_builds_employee_blocks_for_raw_checkin_layout(client):
    raw_profile_df = pd.DataFrame(
        [
            ["Hồ sơ check-in", "", "", "", "", "", "", "", ""],
            ["Ngày ：", "", "2026-03-23 ~ 2026-04-22", "", "", "", "", "", ""],
            [23, 24, 25, 26, 27, 28, 29, 30, 31],
            ["ID:", "", "1", "", "Tên ：", "", "NGUYEN A", "P.Ban:", "Kho A"],
            ["08:10\n17:20", "", "08:12\n17:18", "", "", "", "08:15\n17:30", "", ""],
            [23, 24, 25, 26, 27, 28, 29, 30, 31],
            ["ID:", "", "2", "", "Tên ：", "", "NGUYEN B", "P.Ban:", "Kho B"],
            ["08:20\n17:10", "", "08:18\n17:25", "", "", "", "08:40\n17:45", "", ""],
        ]
    )

    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        raw_profile_df.to_excel(writer, index=False, header=False, sheet_name="Hồ sơ check-in")
    stream.seek(0)

    files = {
        "file": (
            "raw_checkin_blocks.xlsx",
            stream,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    response = client.post(
        "/api/import/sheet-inspect",
        files=files,
        data={"import_type": "checkin", "sheet_name": "Hồ sơ check-in", "header_row_index": "3"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["employee_blocks"]) == 2
    assert payload["employee_blocks"][0]["employee_id"] == "1"
    assert payload["employee_blocks"][0]["employee_name"] == "NGUYEN A"
    assert payload["employee_blocks"][1]["employee_id"] == "2"
    assert payload["employee_blocks"][1]["department_name"] == "Kho B"
    assert payload["employee_blocks"][0]["day_entries"][0]["day_label"] == "23"


def test_sheet_inspect_merges_repeated_employee_blocks_and_all_punches(client):
    raw_profile_df = pd.DataFrame(
        [
            [23, 24, 25, 26, 27, 28, 29, 30, 31],
            ["ID:", "", "#29", "", "Tên ：", "", "ruby", "P.Ban:", "IT"],
            ["08:10", "", "08:20", "", "", "", "", "", ""],
            [23, 24, 25, 26, 27, 28, 29, 30, 31],
            ["ID:", "", "#29", "", "Tên ：", "", "ruby", "P.Ban:", "IT"],
            ["17:40", "", "17:30", "", "", "", "", "", ""],
        ]
    )
    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        raw_profile_df.to_excel(writer, index=False, header=False, sheet_name="Hồ sơ check-in")
    stream.seek(0)

    response = client.post(
        "/api/import/sheet-inspect",
        files={"file": ("ruby_two_blocks.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"import_type": "checkin", "sheet_name": "Hồ sơ check-in", "header_row_index": "1"},
    )

    assert response.status_code == 200
    blocks = response.json()["employee_blocks"]
    assert len(blocks) == 1
    assert blocks[0]["employee_id"] == "29"
    assert blocks[0]["day_entries"][0]["time_values"] == ["08:10", "17:40"]


def test_workbook_inspect_does_not_recommend_partial_match_from_optional_columns_only(client):
    raw_profile_df = pd.DataFrame(
        [
            ["Hồ sơ check-in", "", "", ""],
            ["Ngày ：", "", "2026-03-23 ~ 2026-04-22", ""],
            [23, 24, 25, 26],
            ["ID:", "", "2", "Tên ："],
            ["08:15\n17:30", "08:45*\n17:30", "", "08:15"],
        ]
    )
    abnormal_df = pd.DataFrame(
        [
            ["ID", "Tên", "P.Ban", "Ngày", "Thời gian trễ", "Thời gian sớm"],
            ["2", "NGUYEN THANH TR", "Not Set1", "2026-03-23", 23, 0],
        ]
    )

    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        raw_profile_df.to_excel(writer, index=False, header=False, sheet_name="Hồ sơ check-in")
        abnormal_df.to_excel(writer, index=False, header=False, sheet_name="Báo cáo bất thường")
    stream.seek(0)

    files = {
        "file": (
            "partial_optional_match.xlsx",
            stream,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    response = client.post("/api/import/workbook-inspect", files=files, data={"import_type": "checkin"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_sheet_name"] is None
    assert payload["recommended_mapping"] == {}


def test_sheet_inspect_falls_back_to_dense_header_row_for_template_like_sheet(client):
    template_df = pd.DataFrame(
        [
            ["", "", "", "", "", "", "EMPLOYEE TIMESHEET FROM 23/03/2026 TO 22/04/2026"],
            ["STT", "Họ Và Tên", 23, 24, "28 T7", "29 CN", "Nghỉ không lương"],
            [1, "Nguyễn A", "X", "X", "", "", 0],
        ]
    )

    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        template_df.to_excel(writer, index=False, header=False, sheet_name="Sheet1")
    stream.seek(0)

    files = {
        "file": (
            "template_like.xlsx",
            stream,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    response = client.post("/api/import/workbook-inspect", files=files, data={"import_type": "checkin"})

    assert response.status_code == 200
    payload = response.json()
    sheet = payload["sheets"][0]
    assert sheet["header_row_index"] == 1
    assert sheet["columns"][0]["label"] == "STT"
    assert sheet["columns"][1]["label"] == "Họ Và Tên"
