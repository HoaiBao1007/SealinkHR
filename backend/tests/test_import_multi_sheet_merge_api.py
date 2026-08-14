from io import BytesIO

import pandas as pd


def test_import_checkin_profile_merges_multiple_sheets_prefers_with_time(client):
    # Sheet tong hop co ID/Ten/Ngay nhung khong co gio -> khong nen duoc uu tien khi da co sheet co gio.
    summary_df = pd.DataFrame(
        [
            ["ID", "Ten", "Ngay"],
            ["1", "NGO THI ANH HON", "23/03/2026"],
            ["1", "NGO THI ANH HON", "24/03/2026"],
        ]
    )

    profile_df = pd.DataFrame(
        [
            ["ID", "Ten", "Ngay", "Moc gio"],
            ["E001", "NGO THI ANH HON", "23/03/2026", "08:30;17:45"],
            ["E002", "NGUYEN THANH TR", "23/03/2026", "08:40;17:30"],
        ]
    )

    report_df = pd.DataFrame(
        [
            ["ID", "Ten", "Ngay", "In", "Out"],
            ["E003", "PHAM DO HANH Q", "23/03/2026", "08:20", "17:20"],
        ]
    )

    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, header=False, sheet_name="Bang tom tat check-in")
        profile_df.to_excel(writer, index=False, header=False, sheet_name="Ho so check-in")
        report_df.to_excel(writer, index=False, header=False, sheet_name="Bao cao check-in")
    stream.seek(0)

    files = {
        "file": (
            "checkin_multi_sheet_merge.xlsx",
            stream,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    response = client.post("/api/import/checkin-profile", files=files)

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == 3

    machine_ids = {row["machine_employee_id"] for row in payload["preview"]}
    assert machine_ids == {"E001", "E002", "E003"}
