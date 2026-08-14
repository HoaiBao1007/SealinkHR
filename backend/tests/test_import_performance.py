from io import BytesIO


def test_import_checkin_large_file(client):
    row_count = 10000
    lines = ["ID,Ten,Ngay,Moc gio"]
    for i in range(row_count):
        lines.append(f"E{i:05d},Nhan Vien {i},24/04/2026,08:30;17:45")
    csv_content = "\n".join(lines)

    files = {"file": ("large_checkin.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
    response = client.post("/api/import/checkin-profile", files=files)

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == row_count
    assert len(payload["preview"]) == 50
