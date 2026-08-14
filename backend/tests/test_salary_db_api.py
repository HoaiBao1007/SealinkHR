from app.models.monthly_salary_input import MonthlySalaryInput


def test_employee_salary_crud(client):
    # 1. Create an employee first
    emp_payload = {
        "machine_employee_id": "E800",
        "full_name": "Test Salary Employee",
        "notion_name": "TEST SALARY EMP",
    }
    create_emp_res = client.post("/api/employees", json=emp_payload)
    assert create_emp_res.status_code == 200
    emp_id = create_emp_res.json()["id"]

    # 2. Get employee via salary endpoint
    get_res = client.get("/api/salary/employees", params={"q": "TEST SALARY"})
    assert get_res.status_code == 200
    employees = get_res.json()
    assert len(employees) >= 1
    target_emp = next(e for e in employees if e["id"] == emp_id)
    assert target_emp["contract_salary"] == 0
    assert target_emp["employee_type"] == "FULLTIME"

    # 3. Update employee salary fields
    update_payload = {
        "employee_code": "CODE800",
        "fullname": "Test Salary Employee Updated",
        "position": "Senior Developer",
        "contract_salary": 65000000,
        "employee_type": "FULLTIME",
        "dependents_count": 2,
        "account_number": "123456789",
        "bank_name": "Vietcombank",
    }
    put_res = client.put(f"/api/salary/employees/{emp_id}", json=update_payload)
    assert put_res.status_code == 200
    updated = put_res.json()
    assert updated["employee_code"] == "CODE800"
    assert updated["fullname"] == "Test Salary Employee Updated"
    assert updated["position"] == "Senior Developer"
    assert updated["contract_salary"] == 65000000
    assert updated["dependents_count"] == 2
    assert updated["account_number"] == "123456789"
    assert updated["bank_name"] == "Vietcombank"

    # 4. Create monthly salary input
    input_payload = {
        "employee_id": emp_id,
        "salary_period": "2026-05",
        "actual_working_days": 21.5,
        "meal_allowance_free": 1200000,
        "phone_allowance_free": 500000,
        "perf_allowance_tax": 3000000,
        "bonus": 10000000,
        "advance_payment": 2000000,
    }
    post_res = client.post("/api/salary/inputs", json=input_payload)
    assert post_res.status_code == 200
    created_inputs = post_res.json()
    assert len(created_inputs) == 1
    input_item = created_inputs[0]
    input_id = input_item["id"]
    assert input_item["actual_working_days"] == 21.5
    assert input_item["perf_allowance_tax"] == 3000000
    assert input_item["salary_period"] == "2026-05"

    # 5. Get list of inputs filtered by period
    get_inputs_res = client.get("/api/salary/inputs", params={"period": "2026-05"})
    assert get_inputs_res.status_code == 200
    inputs = get_inputs_res.json()
    assert len(inputs) >= 1
    assert any(x["id"] == input_id for x in inputs)

    # 6. Update single input record
    update_input_payload = {
        "actual_working_days": 22.0,
        "bonus": 12000000,
    }
    put_input_res = client.put(f"/api/salary/inputs/{input_id}", json=update_input_payload)
    assert put_input_res.status_code == 200
    updated_input = put_input_res.json()
    assert updated_input["actual_working_days"] == 22.0
    assert updated_input["bonus"] == 12000000

    # 7. Upsert (update existing via POST)
    upsert_payload = {
        "employee_id": emp_id,
        "salary_period": "2026-05",
        "actual_working_days": 20.0,
        "bonus": 5000000,
    }
    post_upsert_res = client.post("/api/salary/inputs", json=upsert_payload)
    assert post_upsert_res.status_code == 200
    upserted_inputs = post_upsert_res.json()
    assert len(upserted_inputs) == 1
    upserted_item = upserted_inputs[0]
    assert upserted_item["id"] == input_id
    assert upserted_item["actual_working_days"] == 20.0
    assert upserted_item["bonus"] == 5000000

    # 7.5 Test export endpoint
    export_res = client.get("/api/salary/export", params={"period": "2026-05"})
    assert export_res.status_code == 200
    assert "content-disposition" in export_res.headers
    assert "salary_table_2026-05.xlsx" in export_res.headers["content-disposition"]

    # 8. Delete input
    delete_res = client.delete(f"/api/salary/inputs/{input_id}")
    assert delete_res.status_code == 204

    # Verify deleted
    get_deleted_res = client.get("/api/salary/inputs", params={"period": "2026-05"})
    assert get_deleted_res.status_code == 200
    assert not any(x["id"] == input_id for x in get_deleted_res.json())


def test_other_income_evidence_round_trip(client):
    created = client.post(
        "/api/employees",
        json={
            "machine_employee_id": "E899",
            "full_name": "Other Income Employee",
            "notion_name": "OTHER INCOME EMPLOYEE",
        },
    )
    assert created.status_code == 200
    employee_id = created.json()["id"]

    missing_reason = client.post(
        f"/api/salary/other-income-evidence/{employee_id}",
        data={"period": "2026-08", "other_income": "750000", "note": ""},
    )
    assert missing_reason.status_code == 422

    saved = client.post(
        f"/api/salary/other-income-evidence/{employee_id}",
        data={
            "period": "2026-08",
            "other_income": "750000",
            "note": "Hỗ trợ dự án theo quyết định nội bộ",
        },
        files={"document": ("quyet-dinh.pdf", b"%PDF-1.4 test evidence", "application/pdf")},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["other_income"] == 750000
    assert body["other_income_note"] == "Hỗ trợ dự án theo quyết định nội bộ"
    assert body["other_income_document_name"] == "quyet-dinh.pdf"
    assert "other_income_document_path" not in body

    salary_inputs = client.get("/api/salary/inputs", params={"period": "2026-08"})
    assert salary_inputs.status_code == 200
    saved_input = next(row for row in salary_inputs.json() if row["employee_id"] == employee_id)
    assert saved_input["other_income"] == 750000
    assert saved_input["other_income_note"] == "Hỗ trợ dự án theo quyết định nội bộ"
    assert saved_input["other_income_document_name"] == "quyet-dinh.pdf"
    assert "other_income_document_path" not in saved_input

    downloaded = client.get(
        f"/api/salary/other-income-evidence/{employee_id}/file",
        params={"period": "2026-08"},
    )
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF-1.4 test evidence"
    assert "quyet-dinh.pdf" in downloaded.headers["content-disposition"]

    deleted = client.delete(
        f"/api/salary/other-income-evidence/{employee_id}/file",
        params={"period": "2026-08"},
    )
    assert deleted.status_code == 204
    assert client.get(
        f"/api/salary/other-income-evidence/{employee_id}/file",
        params={"period": "2026-08"},
    ).status_code == 404


def test_employee_type_change_from_salary_period_preserves_history_and_propagates(client, db_session):
    """A type selected for one payroll period applies from that period forward only."""
    created = client.post(
        "/api/employees",
        json={
            "machine_employee_id": "E801",
            "full_name": "Type Timeline Employee",
            "notion_name": "TYPE TIMELINE EMPLOYEE",
        },
    )
    assert created.status_code == 200
    employee_id = created.json()["id"]

    # Simulate legacy snapshots that still say FULLTIME in both an old and a
    # future row. The timeline must supersede the future legacy snapshot.
    db_session.add_all(
        [
            MonthlySalaryInput(
                employee_id=employee_id,
                salary_period="2026-06",
                employee_type="FULLTIME",
                meal_allowance_free=1_200_000,
                phone_allowance_free=2_000_000,
                trans_allowance_tax=2_000_000,
            ),
            MonthlySalaryInput(
                employee_id=employee_id,
                salary_period="2026-08",
                employee_type="FULLTIME",
                meal_allowance_free=1_200_000,
                phone_allowance_free=2_000_000,
                trans_allowance_tax=2_000_000,
            ),
        ]
    )
    db_session.commit()

    changed = client.put(
        f"/api/salary/employees/{employee_id}",
        params={"period": "2026-07"},
        json={"employee_type": "PROBATION"},
    )
    assert changed.status_code == 200

    june = client.get("/api/salary/employees", params={"period": "2026-06"}).json()
    july = client.get("/api/salary/employees", params={"period": "2026-07"}).json()
    august = client.get("/api/salary/employees", params={"period": "2026-08"}).json()
    assert next(row for row in june if row["id"] == employee_id)["employee_type"] == "FULLTIME"
    assert next(row for row in july if row["id"] == employee_id)["employee_type"] == "PROBATION"
    assert next(row for row in august if row["id"] == employee_id)["employee_type"] == "PROBATION"

    august_inputs = client.get("/api/salary/inputs", params={"period": "2026-08"}).json()
    august_input = next(row for row in august_inputs if row["employee_id"] == employee_id)
    assert august_input["meal_allowance_free"] == 0
    assert august_input["phone_allowance_free"] == 0
    assert august_input["trans_allowance_tax"] == 0
