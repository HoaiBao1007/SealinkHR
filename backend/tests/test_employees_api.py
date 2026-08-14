def test_create_list_update_employee(client):
    create_payload = {
        "machine_employee_id": "E100",
        "full_name": "Tran Thi B",
        "notion_name": "DOCS - TRAN THI B",
        "department_code": "ACC",
        "department_name": "Accounting",
        "annual_leave_quota": 14,
        "is_active": True,
        "phone_number": "0901000001",
        "company_phone_number": "02873075768",
    }
    create_response = client.post("/api/employees", json=create_payload)
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["machine_employee_id"] == "E100"
    assert created["notion_name"] == "DOCS - TRAN THI B"
    assert created["phone_number"] == "0901000001"
    assert created["company_phone_number"] == "02873075768"
    employee_id = created["id"]

    list_response = client.get("/api/employees", params={"q": "DOCS - TRAN"})
    assert list_response.status_code == 200
    listed = list_response.json()
    assert len(listed) == 1
    assert listed[0]["id"] == employee_id

    detail_response = client.get(f"/api/employees/{employee_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == employee_id

    update_payload = {
        "notion_name": "DOCS - TRAN THI B UPDATED",
        "department_name": "Finance",
        "annual_leave_used": 2,
        "paid_leave_balance": 10,
        "is_active": False,
        "company_phone_number": "02873075769",
    }
    update_response = client.put(f"/api/employees/{employee_id}", json=update_payload)
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["notion_name"] == "DOCS - TRAN THI B UPDATED"
    assert updated["department_name"] == "Finance"
    assert updated["annual_leave_used"] == 2.0
    assert updated["is_active"] is False
    assert updated["company_phone_number"] == "02873075769"


def test_create_employee_duplicate_machine_id(client):
    payload = {
        "machine_employee_id": "E200",
        "full_name": "Le Van C",
    }
    first = client.post("/api/employees", json=payload)
    second = client.post("/api/employees", json=payload)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"] == (
        "Mã máy chấm công (ID) đã được dùng làm mã chính hoặc mã phụ của nhân viên khác."
    )


def test_employee_identifiers_cannot_cross_duplicate_primary_and_alternate_ids(client):
    first = client.post(
        "/api/employees",
        json={
            "machine_employee_id": "PRIMARY-E203",
            "biometric_id": "ALIAS-E203",
            "full_name": "Nhan Vien Co Ma Phu",
        },
    )
    assert first.status_code == 200

    duplicate_primary = client.post(
        "/api/employees",
        json={
            "machine_employee_id": "ALIAS-E203",
            "full_name": "Nhan Vien Trung Ma Phu",
        },
    )
    assert duplicate_primary.status_code == 409

    second = client.post(
        "/api/employees",
        json={
            "machine_employee_id": "PRIMARY-E204",
            "full_name": "Nhan Vien Thu Hai",
        },
    )
    assert second.status_code == 200

    duplicate_alternate = client.put(
        f"/api/employees/{second.json()['id']}",
        json={"biometric_id": "PRIMARY-E203"},
    )
    assert duplicate_alternate.status_code == 409


def test_create_employee_allows_blank_login_credentials(client):
    response = client.post("/api/employees", json={
        "machine_employee_id": "E201",
        "full_name": "Nhan Vien Mapping",
        "username": "",
        "password": "",
    })

    assert response.status_code == 200
    assert response.json()["username"] is None


def test_employee_detail_can_fill_deferred_profile_fields(client):
    created = client.post("/api/employees", json={
        "machine_employee_id": "E202",
        "full_name": "ten tren bao cao",
        "username": "",
        "password": "",
    })
    assert created.status_code == 200
    employee_id = created.json()["id"]

    updated = client.put(f"/api/employees/{employee_id}", json={
        "full_name": "NGUYEN VAN BO SUNG",
        "notion_name": "NOTION NAME",
        "biometric_id": "BIO-E202",
        "position": "Nhân viên",
        "start_date": "2026-07-22",
        "contract_salary": 15000000,
        "meal_allowance": 1300000,
        "phone_allowance": 800000,
        "trans_allowance": 600000,
        "other_allowance": 200000,
        "account_number": "123456789",
        "bank_name": "VCB",
        "company_email": "mapping@sea-link.com",
        "phone_number": "0902000202",
        "company_phone_number": "02873075768",
        "username": "mapping_e202",
        "password": "mapping-pass-2026",
    })

    assert updated.status_code == 200
    data = updated.json()
    assert data["full_name"] == "NGUYEN VAN BO SUNG"
    assert data["notion_name"] == "NOTION NAME"
    assert data["biometric_id"] == "BIO-E202"
    assert data["contract_salary"] == 15000000
    assert data["meal_allowance"] == 1300000
    assert data["account_number"] == "123456789"
    assert data["phone_number"] == "0902000202"
    assert data["company_phone_number"] == "02873075768"
    assert data["username"] == "mapping_e202"


def test_create_employee_saves_contract_allowance_configuration(client):
    payload = {
        "machine_employee_id": "E205",
        "full_name": "Le Van Phu Cap",
        "contract_salary": 15000000,
        "meal_allowance": 1200000,
        "phone_allowance": 750000,
        "trans_allowance": 500000,
        "other_allowance": 300000,
    }

    response = client.post("/api/employees", json=payload)

    assert response.status_code == 200
    created = response.json()
    assert created["contract_salary"] == 15000000
    assert created["meal_allowance"] == 1200000
    assert created["phone_allowance"] == 750000
    assert created["trans_allowance"] == 500000
    assert created["other_allowance"] == 300000

    input_response = client.get("/api/salary/inputs", params={"period": "2026-07"})
    assert input_response.status_code == 200
    input_row = next(item for item in input_response.json() if item["employee_id"] == created["id"])
    assert input_row["meal_allowance_free"] == 1200000
    assert input_row["phone_allowance_free"] == 750000
    assert input_row["trans_allowance_tax"] == 500000
    assert input_row["perf_allowance_tax"] == 300000


def test_employee_type_controls_default_allowances(client):
    created = client.post("/api/employees", json={
        "machine_employee_id": "E206",
        "full_name": "Nhan Vien Hoc Viec",
        "employee_type": "INTERN",
        "meal_allowance": 1_200_000,
        "phone_allowance": 2_000_000,
        "trans_allowance": 2_000_000,
        "other_allowance": 500_000,
    })
    assert created.status_code == 200
    intern = created.json()
    assert intern["employee_type"] == "INTERN"
    assert intern["meal_allowance"] == 0
    assert intern["phone_allowance"] == 0
    assert intern["trans_allowance"] == 0
    assert intern["other_allowance"] == 0

    promoted = client.put(f"/api/employees/{intern['id']}", json={
        "employee_type": "FULLTIME",
    })
    assert promoted.status_code == 200
    employee = promoted.json()
    assert employee["employee_type"] == "FULLTIME"
    assert employee["meal_allowance"] == 1_200_000
    assert employee["phone_allowance"] == 2_000_000
    assert employee["trans_allowance"] == 2_000_000
    assert employee["other_allowance"] == 0

    period_type_update = client.put(
        f"/api/salary/employees/{intern['id']}",
        params={"period": "2026-08"},
        json={"employee_type": "INTERN"},
    )
    assert period_type_update.status_code == 200
    inputs = client.get("/api/salary/inputs", params={"period": "2026-08"}).json()
    intern_input = next(item for item in inputs if item["employee_id"] == intern["id"])
    assert intern_input["meal_allowance_free"] == 0
    assert intern_input["phone_allowance_free"] == 0
    assert intern_input["trans_allowance_tax"] == 0
    assert intern_input["perf_allowance_tax"] == 0

    period_promotion = client.put(
        f"/api/salary/employees/{intern['id']}",
        params={"period": "2026-08"},
        json={"employee_type": "FULLTIME"},
    )
    assert period_promotion.status_code == 200
    inputs = client.get("/api/salary/inputs", params={"period": "2026-08"}).json()
    promoted_input = next(item for item in inputs if item["employee_id"] == intern["id"])
    assert promoted_input["meal_allowance_free"] == 1_200_000
    assert promoted_input["phone_allowance_free"] == 2_000_000
    assert promoted_input["trans_allowance_tax"] == 2_000_000
    assert promoted_input["perf_allowance_tax"] == 0


def test_promotion_date_preserves_old_period_allowances(client, db_session):
    created = client.post("/api/employees", json={
        "machine_employee_id": "E207",
        "full_name": "Nhan Vien Thang Tien",
        "employee_type": "PROBATION",
    })
    assert created.status_code == 200
    employee_id = created.json()["id"]

    promoted = client.put(f"/api/employees/{employee_id}", json={
        "employee_type": "FULLTIME",
        "employee_type_effective_date": "2026-07-10",
        "meal_allowance": 1_350_000,
        "phone_allowance": 2_100_000,
        "trans_allowance": 2_300_000,
        "other_allowance": 250_000,
    })
    assert promoted.status_code == 200
    assert promoted.json()["meal_allowance"] == 1_350_000
    assert promoted.json()["phone_allowance"] == 2_100_000
    from app.models.salary_decision import SalaryDecision
    decision = db_session.query(SalaryDecision).filter(
        SalaryDecision.employee_id == employee_id,
        SalaryDecision.new_employee_type.is_not(None),
    ).one()
    assert decision.new_employee_type == "FULLTIME"
    assert decision.meal_allowance == 1_350_000
    assert decision.phone_allowance == 2_100_000

    old_period = client.get("/api/salary/inputs", params={"period": "2026-06"}).json()
    old_input = next(item for item in old_period if item["employee_id"] == employee_id)
    assert old_input["meal_allowance_free"] == 0
    assert old_input["phone_allowance_free"] == 0
    assert old_input["trans_allowance_tax"] == 0

    promotion_period = client.get("/api/salary/inputs", params={"period": "2026-07"}).json()
    promotion_input = next(item for item in promotion_period if item["employee_id"] == employee_id)
    assert promotion_input["meal_allowance_free"] == 1_350_000
    assert promotion_input["phone_allowance_free"] == 2_100_000
    assert promotion_input["trans_allowance_tax"] == 2_300_000
    assert promotion_input["perf_allowance_tax"] == 250_000


def test_delete_employee(client):
    payload = {
        "machine_employee_id": "E300",
        "full_name": "Pham Van D",
        "notion_name": "DOCS - PHAM VAN D",
    }

    create_response = client.post("/api/employees", json=payload)
    assert create_response.status_code == 200
    employee_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/employees/{employee_id}")
    assert delete_response.status_code == 204

    list_response = client.get("/api/employees", params={"q": "PHAM VAN D"})
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_delete_employee_cleans_timesheet_children_before_parent(client, db_session):
    from datetime import date
    from app.models import AttendanceDaily, Timesheet, TimesheetEntry

    created = client.post("/api/employees", json={
        "machine_employee_id": "E301",
        "full_name": "Nhan Vien Can Xoa",
    })
    assert created.status_code == 200
    employee_id = created.json()["id"]

    timesheet = Timesheet(
        employee_id=employee_id,
        period_start=date(2026, 5, 23),
        period_end=date(2026, 6, 22),
    )
    db_session.add(timesheet)
    db_session.flush()
    db_session.add(TimesheetEntry(
        timesheet_id=timesheet.id,
        employee_id=employee_id,
        work_date=date(2026, 5, 23),
        original_symbol="X",
        final_symbol="X",
    ))
    db_session.add(AttendanceDaily(
        employee_id=employee_id,
        work_date=date(2026, 5, 23),
        period_start=date(2026, 5, 23),
        period_end=date(2026, 6, 22),
        attendance_symbol="X",
    ))
    db_session.commit()

    deleted = client.delete(f"/api/employees/{employee_id}")
    assert deleted.status_code == 204
    assert db_session.query(TimesheetEntry).filter(TimesheetEntry.employee_id == employee_id).count() == 0
    assert db_session.query(Timesheet).filter(Timesheet.employee_id == employee_id).count() == 0
    assert db_session.query(AttendanceDaily).filter(AttendanceDaily.employee_id == employee_id).count() == 0


def test_create_employee_with_credentials(client):
    # Test creation with manual username & password
    payload = {
        "machine_employee_id": "E400",
        "full_name": "Nguyen Van E",
        "username": "user_e_manual",
        "password": "mypassword123",
    }
    response = client.post("/api/employees", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["username"] == "user_e_manual"
    emp_id = res["id"]

    # Test duplicate username creation
    duplicate_payload = {
        "machine_employee_id": "E401",
        "full_name": "Nguyen Van F",
        "username": "user_e_manual",
        "password": "mypassword456",
    }
    dup_res = client.post("/api/employees", json=duplicate_payload)
    assert dup_res.status_code == 409
    assert dup_res.json()["detail"] == "Tên đăng nhập đã tồn tại"

    # Test update username & password
    update_payload = {
        "username": "user_e_updated",
        "password": "newpassword123",
    }
    up_res = client.put(f"/api/employees/{emp_id}", json=update_payload)
    assert up_res.status_code == 200
    assert up_res.json()["username"] == "user_e_updated"

    # Test login with new credentials
    login_payload = {
        "username": "user_e_updated",
        "password": "newpassword123",
    }
    login_res = client.post("/api/auth/login", json=login_payload)
    assert login_res.status_code == 200
    assert login_res.json()["role"] == "USER"
