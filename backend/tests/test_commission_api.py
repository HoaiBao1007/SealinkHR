import pytest
from app.models.commission import CommissionPeriod, CommissionJob

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
    assert len(period_item["sales_rep_summary"]) == 2
    
    # 3. Get single period detail
    detail_res = client.get(f"/api/commission/periods/{period_id}")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["period_label"] == "Q2-2026"
    assert detail_data["source_filename"] == "climax_q2_2026.xlsx"
    
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
    assert rep_summary_ov["bonus_rate"] == 0.45
    assert rep_summary_ov["total_bonus_quarter"] == 45000000.0
    assert rep_summary_ov["sales_bonus"] == 15000000.0
    
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
    assert non_sales["target"] == 0
    assert non_sales["bonus_rate"] == 0.20
    assert non_sales["total_bonus_quarter"] == 190_000_000
    assert non_sales["sales_bonus"] == pytest.approx(63_333_333.33, abs=0.01)

    sales = summaries[sales_employee.full_name]
    expected_sales = calculateDynamicSalesBonus(1_000_000_000, 20_000_000)
    assert sales["uses_progressive_bonus"] is True
    assert sales["total_bonus_quarter"] == expected_sales["total_bonus_quarter"]
    assert sales["sales_bonus"] == pytest.approx(expected_sales["bonus_per_month"], abs=0.01)

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
