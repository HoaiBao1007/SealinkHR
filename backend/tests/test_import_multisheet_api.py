from io import BytesIO

import pandas as pd


def test_import_checkin_profile_detects_correct_sheet(client):
    summary_df = pd.DataFrame(
        [
            ["Bảng tóm tắt check-in", None, None, None],
            ["ID", "Tên", "P.Ban", "Giờ làm"],
            ["1", "Nguyen Van A", "Not Set 1", "294:30"],
        ]
    )

    profile_df = pd.DataFrame(
        [
            ["ID", "Ten", "Ngay", "Moc gio"],
            ["E001", "Nguyen Van A", "24/04/2026", "08:45*;10:54;13:39;18:03"],
        ]
    )

    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, header=False, sheet_name="Bang tom tat check-in")
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Ho so check-in")
    stream.seek(0)

    files = {
        "file": (
            "checkin_multi_sheet.xlsx",
            stream,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    response = client.post("/api/import/checkin-profile", files=files)

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == 1
    row = payload["preview"][0]
    assert row["machine_employee_id"] == "E001"
    assert row["check_in_time"] == "08:45"
    assert row["check_out_time"] == "18:03"
