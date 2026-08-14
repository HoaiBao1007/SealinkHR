from io import BytesIO


def test_import_checkin_profile_with_in_out_columns(client):
    csv_content = "ID,Ten,Ngay,In,Out\nE001,Nguyen Van A,24/04/2026,08:45,18:03\n"
    files = {"file": ("checkin_in_out.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    response = client.post("/api/import/checkin-profile", files=files)

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == 1
    row = payload["preview"][0]
    assert row["machine_employee_id"] == "E001"
    assert row["check_in_time"] == "08:45"
    assert row["check_out_time"] == "18:03"
    assert row["missing_flag"] is False
