from io import BytesIO


def test_import_checkin_profile_without_time_columns(client):
    csv_content = "ID,Ten,Ngay\nE001,Nguyen Van A,24/04/2026\n"
    files = {"file": ("checkin_no_time.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    response = client.post("/api/import/checkin-profile", files=files)

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == 1
    row = payload["preview"][0]
    assert row["machine_employee_id"] == "E001"
    assert row["check_in_time"] is None
    assert row["check_out_time"] is None
    assert row["missing_flag"] is True
    assert row["missing_reason"] == "missing_all"
