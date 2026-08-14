from io import BytesIO


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_import_checkin_profile_preview(client):
    csv_content = "ID,Ten,Ngay,Moc gio\nE001,Nguyen Van A,24/04/2026,08:45*;10:54;13:39;18:03\n"
    files = {"file": ("checkin.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    response = client.post("/api/import/checkin-profile", files=files)

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == 1
    row = payload["preview"][0]
    assert row["machine_employee_id"] == "E001"
    assert row["check_in_time"] == "08:45"
    assert row["check_out_time"] == "18:03"
    assert row["period_start"] == "2026-04-23"
    assert row["period_end"] == "2026-05-22"


def test_import_abnormal_report_preview(client):
    csv_content = (
        "ID,Ten,P.Ban,Ngay,Thoi gian tre,Thoi gian som,Ghi chu\n"
        "E001,Nguyen Van A,Operations,24/04/2026,15 phut,0,Bo lo dau vao\n"
    )
    files = {"file": ("abnormal.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}

    response = client.post("/api/import/abnormal-report", files=files)

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == 1
    row = payload["preview"][0]
    assert row["machine_employee_id"] == "E001"
    assert row["late_minutes"] == 15
    assert row["missing_flag"] is True
    assert row["period_start"] == "2026-04-23"
    assert row["period_end"] == "2026-05-22"
