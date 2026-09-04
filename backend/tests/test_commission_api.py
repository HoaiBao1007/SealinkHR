import pytest
from io import BytesIO
from openpyxl import Workbook
from app.models.commission import CommissionPeriod, CommissionJob
from app.models.employee import Employee


def _receivable_report_bytes(rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "AGEING"
    sheet.append(["Job No", "Receivable / Payable", "Received / Paid", "Balance", "Cur"])
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_commission_job_receivable_upload_detail_download_and_cleanup(client, monkeypatch, tmp_path):
    from app.api import commission_api

    monkeypatch.setattr(commission_api, "COMMISSION_RECEIVABLE_UPLOAD_DIR", tmp_path)
    imported = client.post("/api/commission/import", json={
        "period_label": "Q3-2026",
        "from_date": "2026-07-01",
        "till_date": "2026-09-30",
        "source_filename": "job-pnl-q3.xlsx",
        "jobs": [{
            "job_no": "REC-001",
            "sales_rep": "NGUYEN BAO",
            "customer": "Customer Receivable",
            "profit_loss": 100_000_000,
        }],
    })
    assert imported.status_code == 201
    period_id = imported.json()["period_id"]
    job = client.get(f"/api/commission/periods/{period_id}/jobs").json()[0]
    assert job["receivableCount"] == 0

    uploaded = client.post(
        f"/api/commission/periods/{period_id}/jobs/{job['id']}/receivables",
        data={"note": "Công nợ khách hàng tháng 8"},
        files=[
            ("files", ("bang-cong-no.xlsx", b"excel receivable content", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ("files", ("bien-ban-doi-chieu.pdf", b"%PDF-1.4 receivable", "application/pdf")),
        ],
    )
    assert uploaded.status_code == 201
    attachments = uploaded.json()
    assert [item["original_filename"] for item in attachments] == ["bang-cong-no.xlsx", "bien-ban-doi-chieu.pdf"]
    assert all(item["job_no"] == "REC-001" for item in attachments)
    assert all(item["sales_rep"] == "NGUYEN BAO" for item in attachments)
    assert all(item["note"] == "Công nợ khách hàng tháng 8" for item in attachments)

    listed = client.get(f"/api/commission/periods/{period_id}/jobs/{job['id']}/receivables")
    assert listed.status_code == 200
    assert len(listed.json()) == 2
    refreshed_job = client.get(f"/api/commission/periods/{period_id}/jobs").json()[0]
    assert refreshed_job["receivableCount"] == 2

    pdf = next(item for item in attachments if item["original_filename"].endswith(".pdf"))
    downloaded = client.get(
        f"/api/commission/periods/{period_id}/jobs/{job['id']}/receivables/{pdf['id']}/file"
    )
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF-1.4 receivable"

    deleted = client.delete(
        f"/api/commission/periods/{period_id}/jobs/{job['id']}/receivables/{pdf['id']}"
    )
    assert deleted.status_code == 204
    assert len(client.get(f"/api/commission/periods/{period_id}/jobs/{job['id']}/receivables").json()) == 1

    assert client.delete(f"/api/commission/periods/{period_id}").status_code == 200
    assert list(tmp_path.iterdir()) == []


def test_commission_job_receivable_rejects_unsupported_file(client, monkeypatch, tmp_path):
    from app.api import commission_api

    monkeypatch.setattr(commission_api, "COMMISSION_RECEIVABLE_UPLOAD_DIR", tmp_path)
    imported = client.post("/api/commission/import", json={
        "period_label": "Q3-2026",
        "from_date": "2026-07-01",
        "till_date": "2026-09-30",
        "jobs": [{"job_no": "REC-INVALID", "sales_rep": "NGUYEN BAO"}],
    })
    period_id = imported.json()["period_id"]
    job_id = client.get(f"/api/commission/periods/{period_id}/jobs").json()[0]["id"]
    response = client.post(
        f"/api/commission/periods/{period_id}/jobs/{job_id}/receivables",
        files=[("files", ("malware.exe", b"not allowed", "application/octet-stream"))],
    )
    assert response.status_code == 422
    assert list(tmp_path.iterdir()) == []


def test_commission_receivable_bulk_upload_stores_once_and_links_many_jobs(client, monkeypatch, tmp_path):
    from app.api import commission_api

    monkeypatch.setattr(commission_api, "COMMISSION_RECEIVABLE_UPLOAD_DIR", tmp_path)
    imported = client.post("/api/commission/import", json={
        "period_label": "Q3-BULK-2026",
        "from_date": "2026-07-01",
        "till_date": "2026-09-30",
        "jobs": [
            {"job_no": "REC-BULK-001", "sales_rep": "NGUYEN BAO"},
            {"job_no": "REC-BULK-002", "sales_rep": "NGUYEN BAO"},
        ],
    })
    assert imported.status_code == 201
    period_id = imported.json()["period_id"]
    jobs = client.get(f"/api/commission/periods/{period_id}/jobs").json()
    job_ids = [job["id"] for job in jobs]

    uploaded = client.post(
        f"/api/commission/periods/{period_id}/receivables/bulk",
        data={"job_ids": f"[{job_ids[0]},{job_ids[1]}]", "note": "Đối chiếu nhiều JOB"},
        files=[("files", ("cong-no-nhieu-job.xlsx", b"one physical workbook", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))],
    )
    assert uploaded.status_code == 201
    attachment_id = uploaded.json()[0]["id"]
    assert len(list(tmp_path.iterdir())) == 1

    first_list = client.get(f"/api/commission/periods/{period_id}/jobs/{job_ids[0]}/receivables").json()
    second_list = client.get(f"/api/commission/periods/{period_id}/jobs/{job_ids[1]}/receivables").json()
    assert [item["id"] for item in first_list] == [attachment_id]
    assert [item["id"] for item in second_list] == [attachment_id]
    refreshed = client.get(f"/api/commission/periods/{period_id}/jobs").json()
    assert [job["receivableCount"] for job in refreshed] == [1, 1]

    first_delete = client.delete(
        f"/api/commission/periods/{period_id}/jobs/{job_ids[0]}/receivables/{attachment_id}"
    )
    assert first_delete.status_code == 204
    assert len(list(tmp_path.iterdir())) == 1
    assert client.get(f"/api/commission/periods/{period_id}/jobs/{job_ids[0]}/receivables").json() == []
    assert len(client.get(f"/api/commission/periods/{period_id}/jobs/{job_ids[1]}/receivables").json()) == 1

    second_delete = client.delete(
        f"/api/commission/periods/{period_id}/jobs/{job_ids[1]}/receivables/{attachment_id}"
    )
    assert second_delete.status_code == 204
    assert list(tmp_path.iterdir()) == []


def test_commission_receivable_reconciliation_matches_job_and_updates_hold_bonus(client, db_session, monkeypatch, tmp_path):
    from app.api import commission_api

    monkeypatch.setattr(commission_api, "COMMISSION_RECEIVABLE_UPLOAD_DIR", tmp_path)
    employee = Employee(
        machine_employee_id="REC-RECONCILE-01",
        full_name="NGUYEN THANH DAT RECONCILE",
        contract_salary=10_000_000,
        employee_type="FULLTIME",
        annual_leave_quota=12,
    )
    db_session.add(employee)
    db_session.commit()
    imported = client.post("/api/commission/import", json={
        "period_label": "Q3-RECEIVABLE-2026",
        "from_date": "2026-07-01",
        "till_date": "2026-09-30",
        "jobs": [
            {"job_no": "SEJ-100/26", "sales_rep": employee.full_name, "profit_loss": 100_000_000, "payment_received": "YES"},
            {"job_no": "SEJ-NEG/26", "sales_rep": employee.full_name, "profit_loss": 80_000_000, "payment_received": "YES"},
            {"job_no": "SEJ-ZERO/26", "sales_rep": employee.full_name, "profit_loss": 60_000_000, "payment_received": "NO"},
        ],
    })
    assert imported.status_code == 201
    period_id = imported.json()["period_id"]
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    jobs = client.get(f"/api/commission/periods/{period_id}/jobs").json()
    by_no = {job["jobNo"]: job for job in jobs}
    preserved = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{by_no['SEJ-NEG/26']['id']}/hold-bonus",
        json={"hold_bonus_percent": 12, "edited_field": "percent"},
    )
    assert preserved.status_code == 409

    report = _receivable_report_bytes([
        ["SEJ-100/26", 60_000_000, 30_000_000, 30_000_000, "VND"],
        [" SEJ-100 / 26 ", 40_000_000, 30_000_000, 10_000_000, "VND"],
        ["SEJ-NEG/26", 20_000_000, 21_000_000, -1_000_000, "VND"],
        ["SEJ-OTHER/26", 100_000_000, 75_000_000, 25_000_000, "VND"],
        ["SEJ-ZERO/26", 20_000_000, 20_000_000, 0, "VND"],
    ])
    response = client.post(
        f"/api/commission/periods/{period_id}/receivables/reconcile",
        data={"job_ids": str([job["id"] for job in jobs]).replace("'", '"'), "note": "Đối chiếu AGEING"},
        files={"file": ("payment-report.xlsx", report, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["matched_jobs"] == 2
    assert result["ignored_non_positive_rows"] == 1
    assert result["unmatched_positive_jobs"] == 1
    updates_by_no = {update["job_no"]: update for update in result["updates"]}
    assert updates_by_no["SEJ-100/26"]["source_rows"] == 2
    assert updates_by_no["SEJ-100/26"]["payment_received_amount"] == 60_000_000
    assert updates_by_no["SEJ-100/26"]["hold_bonus_percent"] == 30
    assert updates_by_no["SEJ-100/26"]["hold_bonus_amount"] == 30_000_000
    assert updates_by_no["SEJ-ZERO/26"]["payment_received_amount"] == 20_000_000
    assert updates_by_no["SEJ-ZERO/26"]["paid_percent"] == 100
    # AGEING says Balance = 0, but paid 20m is below the JOB Profit/Loss 60m;
    # the effective outstanding amount therefore keeps the 30% hold.
    assert updates_by_no["SEJ-ZERO/26"]["hold_bonus_percent"] == 30
    assert updates_by_no["SEJ-ZERO/26"]["hold_bonus_amount"] == 18_000_000

    refreshed = {job["jobNo"]: job for job in client.get(f"/api/commission/periods/{period_id}/jobs").json()}
    assert refreshed["SEJ-100/26"]["holdBonusPercent"] == 30
    assert refreshed["SEJ-100/26"]["paymentReceived"] == "YES"
    assert refreshed["SEJ-100/26"]["receivableAmount"] == 100_000_000
    assert refreshed["SEJ-100/26"]["balanceAmount"] == 40_000_000
    assert refreshed["SEJ-100/26"]["paymentReceivedAmount"] == 60_000_000
    assert refreshed["SEJ-100/26"]["netBonus"] == result["updates"][0]["net_bonus"]
    assert refreshed["SEJ-NEG/26"]["holdBonusPercent"] == 30
    assert refreshed["SEJ-ZERO/26"]["paymentReceived"] == "YES"
    assert refreshed["SEJ-ZERO/26"]["paymentReceivedAmount"] == 20_000_000
    assert refreshed["SEJ-ZERO/26"]["balanceAmount"] == 0
    assert refreshed["SEJ-ZERO/26"]["holdBonusPercent"] == 30
    assert refreshed["SEJ-ZERO/26"]["holdBonusAmount"] == updates_by_no["SEJ-ZERO/26"]["hold_bonus_amount"]
    assert refreshed["SEJ-100/26"]["receivableCount"] == 1
    assert refreshed["SEJ-NEG/26"]["receivableCount"] == 0
    wallet_jobs = client.get(
        f"/api/commission/wallet/jobs?sales_rep={employee.full_name}&period_id={period_id}"
    ).json()
    wallet_job = next(item for item in wallet_jobs if item["jobNo"] == "SEJ-100/26")
    fully_paid_wallet_job = next(item for item in wallet_jobs if item["jobNo"] == "SEJ-ZERO/26")
    assert wallet_job["paymentReceived"] == "YES"
    assert wallet_job["paymentReceivedAmount"] == 60_000_000
    assert wallet_job["paymentHeld"] > 0
    assert fully_paid_wallet_job["paymentHeld"] > 0
    wallet_summary = client.get(
        "/api/commission/wallet",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json()[0]["period_summaries"][0]
    assert wallet_summary["payment_received_total"] == 80_000_000
    assert wallet_summary["gross_total_bonus_quarter"] == wallet_summary["total_bonus_quarter"]
    assert wallet_summary["hold_adjusted_total_bonus"] == wallet_summary["total_bonus_quarter"]
    assert wallet_summary["cash_basis_coefficient"] == pytest.approx(
        wallet_summary["formula_effective_coefficient"],
        abs=0.0001,
    )
    assert wallet_summary["cash_basis_monthly_bonus"] == pytest.approx(
        wallet_summary["formula_monthly_bonus"],
        abs=0.01,
    )
    assert len(list(tmp_path.iterdir())) == 1


def test_commission_job_hold_bonus_is_fixed_and_manual_updates_are_rejected(client):
    imported = client.post("/api/commission/import", json={
        "period_label": "Q3-HOLD-2026",
        "from_date": "2026-07-01",
        "till_date": "2026-09-30",
        "jobs": [{"job_no": "HOLD-001", "sales_rep": "NGUYEN BAO", "profit_loss": 100_000_000}],
    })
    assert imported.status_code == 201
    period_id = imported.json()["period_id"]
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    job = client.get(f"/api/commission/periods/{period_id}/jobs").json()[0]
    assert job["holdBonusPercent"] == 30
    # Hold is independent of the employee bonus formula and AGEING data.
    assert job["holdBonusAmount"] == 30_000_000

    updated = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{job['id']}/hold-bonus",
        json={"hold_bonus_percent": 25, "hold_bonus_amount": 500_000},
    )
    assert updated.status_code == 409
    refreshed = client.get(f"/api/commission/periods/{period_id}/jobs").json()[0]
    assert refreshed["holdBonusPercent"] == 30
    assert refreshed["holdBonusAmount"] == job["holdBonusAmount"]
    assert refreshed["profitLoss"] == 100_000_000

    rejected = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{job['id']}/hold-bonus",
        json={"hold_bonus_percent": 31, "hold_bonus_amount": 500_000},
    )
    assert rejected.status_code == 409


def test_commission_import_preserves_large_integer_amounts(client):
    from app.models.commission import CommissionJob

    # MySQL FLOAT (single precision) changes these values to multiples of 32/64.
    # The model and migration must keep DOUBLE precision for imported money.
    for column_name in (
        "realized_revenue",
        "unrealized_revenue",
        "realized_cost",
        "unrealized_cost",
        "profit_loss",
    ):
        assert CommissionJob.__table__.c[column_name].type.precision == 53

    imported = client.post("/api/commission/import", json={
        "period_label": "Q2-PRECISION-2026",
        "from_date": "2026-04-01",
        "till_date": "2026-06-30",
        "jobs": [{
            "job_no": "PRECISION-001",
            "sales_rep": "PRECISION USER",
            "realized_revenue": 623_628_614,
            "unrealized_revenue": 623_628_614,
            "realized_cost": 0,
            "unrealized_cost": 0,
            "profit_loss": 623_682_614,
        }],
    })
    assert imported.status_code == 201
    jobs = client.get(f"/api/commission/periods/{imported.json()['period_id']}/jobs").json()
    assert jobs[0]["realizedRevenue"] == 623_628_614
    assert jobs[0]["unrealizedRevenue"] == 623_628_614
    assert jobs[0]["profitLoss"] == 623_682_614

def test_commission_api_flow(client, db_session):
    # 1. Import commission jobs
    import_payload = {
        "period_label": "Q2-2026",
        "from_date": "2026-04-01",
        "till_date": "2026-06-30",
        "source_filename": "climax_q2_2026.xlsx",
        "note": "Test commission import",
        "jobs": [
            {
                "job_no": "JOB001",
                "job_date": "15/04/2026",
                "hbl": "HBL001",
                "mbl": "MBL001",
                "customer": "Customer A",
                "vendor": "Vendor A",
                "sales_rep": "NGUYEN THANH DAT",
                "shipper": "Shipper A",
                "consignee": "Consignee A",
                "sub_type": "FCL",
                "container_string": "1x20DC",
                "wt": 15.5,
                "vol": 20.0,
                "carrier_booking_no": "BK001",
                "por": "HCM",
                "final_destination": "LAX",
                "realized_revenue": 1000.0,
                "unrealized_revenue": 0.0,
                "realized_cost": 800.0,
                "unrealized_cost": 0.0,
                "profit_loss": 200.0,
                "container_picked": "YES",
                "payment_received": "YES"
            },
            {
                "job_no": "JOB002",
                "job_date": "20/04/2026",
                "hbl": "HBL002",
                "mbl": "MBL002",
                "customer": "Customer B",
                "vendor": "Vendor B",
                "sales_rep": "ĐẶNG HOÀI BẢO",
                "shipper": "Shipper B",
                "consignee": "Consignee B",
                "sub_type": "LCL",
                "container_string": "1x40HC",
                "wt": 25.0,
                "vol": 45.0,
                "carrier_booking_no": "BK002",
                "por": "HCM",
                "final_destination": "HAM",
                "realized_revenue": 2000.0,
                "unrealized_revenue": 0.0,
                "realized_cost": 1500.0,
                "unrealized_cost": 0.0,
                "profit_loss": 500.0,
                "container_picked": "YES",
                "payment_received": "NO"
            }
        ]
    }
    
    import_res = client.post("/api/commission/import", json=import_payload)
    assert import_res.status_code == 201
    import_data = import_res.json()
    assert import_data["jobs_saved"] == 2
    period_id = import_data["period_id"]
    
    # 2. List periods
    list_res = client.get("/api/commission/periods")
    assert list_res.status_code == 200
    periods = list_res.json()
    assert len(periods) >= 1
    
    period_item = next(p for p in periods if p["id"] == period_id)
    assert period_item["period_label"] == "Q2-2026"
    assert period_item["source_filename"] == "climax_q2_2026.xlsx"
    assert period_item["job_count"] == 2
    assert period_item["payout_periods"] == ["2026-07", "2026-08", "2026-09"]
    assert len(period_item["sales_rep_summary"]) == 2
    assert all(
        [item["payout_period"] for item in summary["monthly_payouts"]]
        == period_item["payout_periods"]
        for summary in period_item["sales_rep_summary"]
    )
    
    # 3. Get single period detail
    detail_res = client.get(f"/api/commission/periods/{period_id}")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["period_label"] == "Q2-2026"
    assert detail_data["source_filename"] == "climax_q2_2026.xlsx"
    assert detail_data["payout_periods"] == ["2026-07", "2026-08", "2026-09"]
    
    # 4. Get jobs for a period (without filter)
    jobs_all_res = client.get(f"/api/commission/periods/{period_id}/jobs")
    assert jobs_all_res.status_code == 200
    jobs_all = jobs_all_res.json()
    assert len(jobs_all) == 2
    assert jobs_all[0]["jobNo"] == "JOB001"
    assert jobs_all[1]["jobNo"] == "JOB002"
    
    # 5. Get jobs filtered by sales_rep
    jobs_filtered_res = client.get(f"/api/commission/periods/{period_id}/jobs", params={"sales_rep": "NGUYEN THANH DAT"})
    assert jobs_filtered_res.status_code == 200
    jobs_filtered = jobs_filtered_res.json()
    assert len(jobs_filtered) == 1
    assert jobs_filtered[0]["jobNo"] == "JOB001"
    assert jobs_filtered[0]["salesRep"] == "NGUYEN THANH DAT"
    
    # 5.5 Test override values for a sales_rep
    override_payload = {
        "override_job_count": 99,
        "override_profit_loss": 999999.0,
        "override_target": 150000000.0,
        "override_bonus_rate": 0.45,
        "override_total_bonus": 45000000.0,
        "override_monthly_bonus": 15000000.0
    }
    override_res = client.post(
        f"/api/commission/periods/{period_id}/reps/NGUYEN%20THANH%20DAT/override",
        json=override_payload
    )
    assert override_res.status_code == 200
    
    # Verify values are overridden in period summary
    list_res_ov = client.get("/api/commission/periods")
    assert list_res_ov.status_code == 200
    periods_ov = list_res_ov.json()
    period_item_ov = next(p for p in periods_ov if p["id"] == period_id)
    rep_summary_ov = next(s for s in period_item_ov["sales_rep_summary"] if s["sales_rep"] == "NGUYEN THANH DAT")
    
    assert rep_summary_ov["job_count"] == 99
    assert rep_summary_ov["total_profit_loss"] == 999999.0
    assert rep_summary_ov["target"] == 150000000.0
    # The target gate wins over stale/manual bonus overrides.
    assert rep_summary_ov["bonus_rate"] == 0.0
    assert rep_summary_ov["coefficient"] == 0.0
    assert rep_summary_ov["total_bonus_quarter"] == 0.0
    assert rep_summary_ov["sales_bonus"] == 0.0
    
    # Verify details (jobs list) are NOT affected by overrides
    jobs_detail_res = client.get(
        f"/api/commission/periods/{period_id}/jobs",
        params={"sales_rep": "NGUYEN THANH DAT"}
    )
    assert jobs_detail_res.status_code == 200
    jobs_detail = jobs_detail_res.json()
    assert len(jobs_detail) == 1
    assert jobs_detail[0]["jobNo"] == "JOB001"

    # 6. Delete period
    delete_res = client.delete(f"/api/commission/periods/{period_id}")
    assert delete_res.status_code == 200
    
    # Verify period deleted
    list_after_res = client.get("/api/commission/periods")
    assert list_after_res.status_code == 200
    assert not any(p["id"] == period_id for p in list_after_res.json())

def test_parse_date_helper():
    from app.api.commission_api import _parse_date
    from datetime import date
    
    assert _parse_date("11-Feb-2026") == date(2026, 2, 11)
    assert _parse_date("09-Feb-26") == date(2026, 2, 9)
    assert _parse_date("03-Mar-2026") == date(2026, 3, 3)
    assert _parse_date("01-Jan-2026") == date(2026, 1, 1)
    assert _parse_date(" 15/Apr/2026 ") == date(2026, 4, 15)
    assert _parse_date("2026-05-20") == date(2026, 5, 20)
    assert _parse_date("") is None
    assert _parse_date(None) is None


def test_non_sales_commission_uses_fixed_twenty_percent_rule(client, db_session):
    from datetime import date
    from app.models.department import Department
    from app.models.employee import Employee
    from app.services.salary import calculateDynamicSalesBonus

    non_sales_department = Department(name="DOC")
    sales_department = Department(name="SALE LOCAL")
    db_session.add_all([non_sales_department, sales_department])
    db_session.flush()

    non_sales_employee = Employee(
        machine_employee_id="BONUS-DOC-001",
        full_name="DOC EMPLOYEE",
        department_id=non_sales_department.id,
        department_name="DOC",
        contract_salary=20_000_000,
        bonus_coefficient=0,
    )
    sales_employee = Employee(
        machine_employee_id="BONUS-SALE-001",
        full_name="SALE EMPLOYEE",
        department_id=sales_department.id,
        department_name="SALE LOCAL",
        contract_salary=20_000_000,
        bonus_coefficient=sales_department.id,
    )
    period = CommissionPeriod(
        period_label="Q3-2026",
        from_date=date(2026, 7, 1),
        till_date=date(2026, 9, 30),
    )
    db_session.add_all([non_sales_employee, sales_employee, period])
    db_session.flush()
    db_session.add_all([
        CommissionJob(
            period_id=period.id,
            job_no="BONUS-DOC-JOB",
            sales_rep=non_sales_employee.full_name,
            profit_loss=1_000_000_000,
        ),
        CommissionJob(
            period_id=period.id,
            job_no="BONUS-SALE-JOB",
            sales_rep=sales_employee.full_name,
            profit_loss=1_000_000_000,
        ),
    ])
    db_session.commit()

    response = client.get(f"/api/commission/periods/{period.id}")
    assert response.status_code == 200
    summaries = {row["sales_rep"]: row for row in response.json()["sales_rep_summary"]}

    non_sales = summaries[non_sales_employee.full_name]
    assert non_sales["uses_progressive_bonus"] is False
    assert non_sales["target"] == 40_000_000
    assert non_sales["bonus_rate"] == 0.20
    assert non_sales["total_bonus_quarter"] == 182_000_000
    assert non_sales["sales_bonus"] == pytest.approx(60_666_666.67, abs=0.01)
    assert [row["payout_period"] for row in non_sales["monthly_payouts"]] == [
        "2026-10", "2026-11", "2026-12",
    ]
    assert all(
        row["amount"] == pytest.approx(non_sales["sales_bonus"], abs=0.01)
        for row in non_sales["monthly_payouts"]
    )

    sales = summaries[sales_employee.full_name]
    expected_sales = calculateDynamicSalesBonus(1_000_000_000, 20_000_000)
    assert sales["uses_progressive_bonus"] is True
    assert sales["total_bonus_quarter"] == expected_sales["total_bonus_quarter"]
    assert sales["sales_bonus"] == pytest.approx(expected_sales["bonus_per_month"], abs=0.01)
    assert [row["payout_period"] for row in sales["monthly_payouts"]] == [
        "2026-10", "2026-11", "2026-12",
    ]

    config_response = client.get(
        f"/api/departments/{non_sales_department.id}/bonus-config",
        params={"period": "2026-08"},
    )
    assert config_response.status_code == 200
    assert config_response.json()["rules"] == [{"min": 0.0, "max": 999.0, "rate": 0.20}]

    save_response = client.post(
        f"/api/departments/{non_sales_department.id}/bonus-config",
        json={
            "period": "2026-08",
            "rules": [
                {"min": 0, "max": 2, "rate": 0},
                {"min": 2.01, "max": 999, "rate": 0.35},
            ],
        },
    )
    assert save_response.status_code == 200
    assert save_response.json()["rules"] == [{"min": 0.0, "max": 999.0, "rate": 0.20}]


def test_commission_import_rejects_missing_or_reversed_source_period(client):
    payload = {
        "period_label": "tháng 07, 2026",
        "jobs": [{"job_no": "PERIOD-GUARD-001", "profit_loss": 100}],
    }
    missing_range = client.post("/api/commission/import", json=payload)
    assert missing_range.status_code == 422
    assert "khoảng ngày nguồn" in missing_range.json()["detail"].lower()

    reversed_range = client.post(
        "/api/commission/import",
        json={
            **payload,
            "from_date": "01-Apr-2036",
            "till_date": "30-Jun-2026",
        },
    )
    assert reversed_range.status_code == 422
    assert "bắt đầu lớn hơn" in reversed_range.json()["detail"].lower()
