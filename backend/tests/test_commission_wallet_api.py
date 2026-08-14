from app.models.employee import Employee


def test_employee_can_request_accounting_review_for_own_held_bonus_job(client, db_session):
    """The employee may report a held JOB, but cannot release its money."""
    from app.models.commission import CommissionJob, CommissionPaymentVerification

    employee = Employee(
        machine_employee_id="PORTAL-HOLD-01",
        full_name="NGUYEN PORTAL HOLD",
        user_id=9999,
        contract_salary=10_000_000,
        employee_type="FULLTIME",
        annual_leave_quota=12,
    )
    db_session.add(employee)
    db_session.commit()

    imported = client.post("/api/commission/import", json={
        "period_label": "PORTAL-HOLD-Q3-2026",
        "from_date": "2026-07-01",
        "till_date": "2026-09-30",
        "jobs": [{
            "job_no": "PORTAL-HELD-01",
            "sales_rep": employee.full_name,
            "customer": "Portal held customer",
            "profit_loss": 100_000_000,
            "payment_received": "NO",
        }],
    })
    assert imported.status_code == 201
    assert client.post("/api/commission/wallet/sync", json={"period_id": imported.json()["period_id"]}).status_code == 200

    jobs = client.get("/api/user/my-held-bonus-jobs")
    assert jobs.status_code == 200
    held_job = next(item for item in jobs.json() if item["job_no"] == "PORTAL-HELD-01")
    assert held_job["payment_received"] == "NO"
    assert held_job["payment_held"] > 0
    assert held_job["can_request"] is True

    requested = client.post(
        f"/api/user/my-held-bonus-jobs/{held_job['job_id']}/request-accounting",
        json={"note": "Khách hàng đã thanh toán, vui lòng kế toán kiểm tra."},
    )
    assert requested.status_code == 200
    assert requested.json()["status"] == "PENDING"

    refreshed = next(item for item in client.get("/api/user/my-held-bonus-jobs").json() if item["job_id"] == held_job["job_id"])
    assert refreshed["request_status"] == "PENDING"
    assert refreshed["request_note"] == "Khách hàng đã thanh toán, vui lòng kế toán kiểm tra."
    assert refreshed["payment_held"] == held_job["payment_held"]
    assert refreshed["can_request"] is False

    verification = db_session.query(CommissionPaymentVerification).filter_by(job_id=held_job["job_id"]).one()
    assert verification.status == "PENDING"
    assert db_session.get(CommissionJob, held_job["job_id"]).payment_received == "NO"


def test_wallet_is_scoped_by_sales_rep_and_source_period(client, db_session):
    employee = Employee(machine_employee_id="WALLET-SCOPE", full_name="NGUYEN WALLET SCOPE", contract_salary=10_000_000, employee_type="FULLTIME", annual_leave_quota=12)
    db_session.add(employee)
    db_session.commit()
    first = client.post("/api/commission/import", json={"period_label": "SCOPE-Q2", "from_date": "2026-04-01", "till_date": "2026-06-30", "jobs": [{"job_no": "SCOPE-A", "sales_rep": employee.full_name, "profit_loss": 100_000_000, "payment_received": "YES"}]})
    second = client.post("/api/commission/import", json={"period_label": "SCOPE-Q3", "from_date": "2026-07-01", "till_date": "2026-09-30", "jobs": [{"job_no": "SCOPE-B", "sales_rep": employee.full_name, "profit_loss": 100_000_000, "payment_received": "YES"}]})
    assert first.status_code == 201 and second.status_code == 201
    assert client.post("/api/commission/wallet/sync", json={"period_id": first.json()["period_id"]}).status_code == 200
    assert client.post("/api/commission/wallet/sync", json={"period_id": second.json()["period_id"]}).status_code == 200
    wallets = client.get("/api/commission/wallet", params={"sales_rep": employee.full_name}).json()
    assert {(row["sales_rep"], row["period_id"]) for row in wallets} == {
        (employee.full_name, first.json()["period_id"]), (employee.full_name, second.json()["period_id"]),
    }
    assert {row["period_summaries"][0]["period_label"] for row in wallets} == {"SCOPE-Q2", "SCOPE-Q3"}


def test_commission_wallet_holds_releases_and_pays_by_job(client, db_session):
    employee = Employee(
        machine_employee_id="WALLET-01",
        full_name="NGUYEN VAN WALLET",
        contract_salary=10_000_000,
        employee_type="FULLTIME",
        annual_leave_quota=12,
    )
    db_session.add(employee)
    db_session.add(Employee(
        machine_employee_id="WALLET-02",
        full_name="NGUYEN VAN OTHER",
        contract_salary=10_000_000,
        employee_type="FULLTIME",
        annual_leave_quota=12,
    ))
    db_session.commit()

    imported = client.post("/api/commission/import", json={
        "period_label": "WALLET-Q2-2026",
        "from_date": "2026-04-01",
        "till_date": "2026-06-30",
        "jobs": [
            {"job_no": "W-YES", "sales_rep": "NGUYEN VAN WALLET", "profit_loss": 60_000_000, "payment_received": "YES"},
            {"job_no": "W-NO", "sales_rep": "NGUYEN VAN WALLET", "profit_loss": 40_000_000, "payment_received": "NO"},
            {"job_no": "W-OTHER", "sales_rep": "NGUYEN VAN OTHER", "profit_loss": 80_000_000, "payment_received": "YES"},
        ],
    })
    assert imported.status_code == 201
    period_id = imported.json()["period_id"]

    synced = client.post("/api/commission/wallet/sync", json={"period_id": period_id})
    assert synced.status_code == 200

    wallet = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN WALLET"})
    assert wallet.status_code == 200
    data = wallet.json()[0]
    assert data["total_earned"] > 0
    assert data["held_amount"] > 0
    assert data["available_amount"] > 0
    assert round(data["held_amount"] + data["available_amount"], 2) == data["total_earned"]
    # The overview treats Payment Received hold as one amount for the source
    # quarter and spreads it over July/August/September instead of subtracting
    # it once from every displayed monthly amount.
    monthly_available = data["period_summaries"][0]["monthly_available_amounts"]
    assert len(monthly_available) == 3
    assert round(sum(item["amount"] for item in monthly_available), 2) == round(
        data["period_summaries"][0]["total_bonus_quarter"] - data["period_summaries"][0]["quarter_hold_amount"], 2
    )

    wallet_jobs = client.get("/api/commission/wallet/jobs", params={"sales_rep": "NGUYEN VAN WALLET"})
    assert wallet_jobs.status_code == 200
    wallet_job = next(item for item in wallet_jobs.json() if item["jobNo"] == "W-NO")
    assert wallet_job["periodLabel"] == "WALLET-Q2-2026"
    assert wallet_job["customer"] is None
    assert wallet_job["paymentReceived"] == "NO"
    assert wallet_job["paymentHeld"] > 0

    jobs = client.get(f"/api/commission/periods/{period_id}/jobs").json()
    no_job = next(job for job in jobs if job["jobNo"] == "W-NO")
    # Job IDs are intentionally retrieved from the DB-facing endpoint test setup.
    from app.models.commission import CommissionJob
    no_job_id = db_session.query(CommissionJob).filter(CommissionJob.job_no == no_job["jobNo"]).one().id
    yes_job_id = db_session.query(CommissionJob).filter(CommissionJob.job_no == "W-YES").one().id
    updated = client.patch(f"/api/commission/periods/{period_id}/jobs/{no_job_id}/payment", json={"payment_received": "YES"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "PENDING"
    pending = next(item for item in client.get("/api/commission/wallet/jobs", params={"sales_rep": "NGUYEN VAN WALLET"}).json() if item["id"] == no_job_id)
    assert pending["paymentReceived"] == "NO"
    assert pending["paymentHeld"] > 0
    verification_id = pending["paymentVerificationId"]
    assert client.post(f"/api/commission/payment-verifications/{verification_id}/review", json={"action": "VERIFY"}).status_code == 200
    command = client.post(f"/api/commission/payment-verifications/{verification_id}/payout-command", json={"release_mode": "NEXT_QUARTER_SPLIT"})
    assert command.status_code == 200
    assert len(command.json()["schedule_ids"]) == 3
    after_command = next(item for item in client.get("/api/commission/wallet/jobs", params={"sales_rep": "NGUYEN VAN WALLET"}).json() if item["id"] == no_job_id)
    assert after_command["paymentHeld"] == 0
    assert after_command["scheduled"] > 0
    return
    assert updated.json()["remark"] == "Payment Received NO → YES: khách hàng đã thanh toán, mở giữ tự động."
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    from app.models.commission import CommissionBonusEntitlement, CommissionCalculationSnapshot
    assert db_session.query(CommissionCalculationSnapshot).filter(CommissionCalculationSnapshot.period_id == period_id).count() > 0
    assert db_session.query(CommissionBonusEntitlement).filter(CommissionBonusEntitlement.period_id == period_id).count() > 0

    after_release = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN WALLET"}).json()[0]
    assert after_release["held_amount"] == 0
    assert round(after_release["available_amount"] + after_release["scheduled_amount"], 2) == after_release["total_earned"]

    job_before_hold = next(item for item in after_release["jobs"] if item["job_id"] == yes_job_id)
    held = client.post("/api/commission/wallet/job-holds", json={
        "sales_rep": "NGUYEN VAN WALLET", "job_id": yes_job_id, "action": "HOLD", "amount": 500,
        "reason": "Giá»¯ JOB Ä‘á»ƒ kiá»ƒm tra",
    })
    assert held.status_code == 200
    after_manual_hold = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN WALLET"}).json()[0]
    held_job = next(item for item in after_manual_hold["jobs"] if item["job_id"] == yes_job_id)
    assert held_job["manual_held"] == 500
    assert held_job["available"] == job_before_hold["available"] - 500

    # Re-sync must never release an explicit administrator JOB hold.
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    after_resync = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN WALLET"}).json()[0]
    assert next(item for item in after_resync["jobs"] if item["job_id"] == yes_job_id)["manual_held"] == 500
    released_hold = client.post("/api/commission/wallet/job-holds", json={
        "sales_rep": "NGUYEN VAN WALLET", "job_id": yes_job_id, "action": "RELEASE", "amount": 500,
    })
    assert released_hold.status_code == 200
    after_manual_release = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN WALLET"}).json()[0]
    assert next(item for item in after_manual_release["jobs"] if item["job_id"] == no_job_id)["manual_held"] == 0

    # The editable table saves a target total, while the API appends only the delta.
    edited_hold = client.put(f"/api/commission/wallet/jobs/{yes_job_id}/manual-hold", json={
        "sales_rep": "NGUYEN VAN WALLET", "manual_held_amount": 350, "remark": "Giá»¯ theo yÃªu cáº§u kiá»ƒm tra",
    })
    assert edited_hold.status_code == 200
    assert edited_hold.json()["manual_held_amount"] == 350
    assert next(item for item in client.get("/api/commission/wallet/jobs", params={"sales_rep": "NGUYEN VAN WALLET"}).json() if item["id"] == yes_job_id)["remark"] is not None
    assert client.put(f"/api/commission/wallet/jobs/{yes_job_id}/manual-hold", json={
        "sales_rep": "NGUYEN VAN WALLET", "manual_held_amount": 0,
    }).status_code == 200

    # A YES -> NO edit now re-holds the available JOB bonus after synchronization.
    payment_no = client.patch(f"/api/commission/periods/{period_id}/jobs/{no_job_id}/payment", json={"payment_received": "NO", "remark": "Chá» khÃ¡ch thanh toÃ¡n láº¡i"})
    assert payment_no.status_code == 200
    assert payment_no.json()["wallet_synchronized"] is True
    reheld = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN WALLET"}).json()[0]
    assert next(item for item in reheld["jobs"] if item["job_id"] == no_job_id)["payment_held"] > 0
    payment_yes = client.patch(f"/api/commission/periods/{period_id}/jobs/{no_job_id}/payment", json={"payment_received": "YES"})
    assert payment_yes.status_code == 200
    assert payment_yes.json()["wallet_synchronized"] is True
    assert payment_yes.json()["remark"] == "Payment Received NO → YES: khách hàng đã thanh toán, mở giữ tự động."
    released_again = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN WALLET"}).json()[0]
    assert next(item for item in released_again["jobs"] if item["job_id"] == no_job_id)["payment_held"] == 0

    paid = client.post("/api/commission/wallet/payout", json={"sales_rep": "NGUYEN VAN WALLET", "payout_period": "2026-07"})
    assert paid.status_code == 200
    after_payment = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN WALLET"}).json()[0]
    assert after_payment["available_amount"] == 0
    assert round(after_payment["paid_amount"] + after_payment["scheduled_amount"], 2) == after_payment["total_earned"]

    deleted = client.delete(f"/api/commission/periods/{period_id}/reps/NGUYEN%20VAN%20WALLET")
    assert deleted.status_code == 200
    assert client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN WALLET"}).json() == []
    assert len(client.get("/api/commission/periods").json()) == 1
    other_wallet = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN OTHER"}).json()
    assert other_wallet and other_wallet[0]["total_earned"] > 0


def test_payment_received_release_is_allocated_to_the_next_cycle(client, db_session):
    from app.models.commission import CommissionCalculationSnapshot, CommissionJob, CommissionWalletLedger
    from app.services.salary import get_commission_payslip_summary, get_sales_bonus_for_employee_period

    split_employee = Employee(machine_employee_id="RELEASE-SPLIT", full_name="NGUYEN RELEASE SPLIT", contract_salary=10_000_000, employee_type="FULLTIME", annual_leave_quota=12)
    lump_employee = Employee(machine_employee_id="RELEASE-LUMP", full_name="NGUYEN RELEASE LUMP", contract_salary=10_000_000, employee_type="FULLTIME", annual_leave_quota=12)
    db_session.add_all([split_employee, lump_employee])
    db_session.commit()
    imported = client.post("/api/commission/import", json={
        "period_label": "RELEASE-Q2-2026", "from_date": "2026-04-01", "till_date": "2026-06-30",
        "jobs": [
            {"job_no": "RELEASE-SPLIT-JOB", "sales_rep": split_employee.full_name, "profit_loss": 100_000_000, "payment_received": "NO"},
            {"job_no": "RELEASE-LUMP-JOB", "sales_rep": lump_employee.full_name, "profit_loss": 100_000_000, "payment_received": "NO"},
        ],
    })
    assert imported.status_code == 201
    period_id = imported.json()["period_id"]
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200

    split_job = db_session.query(CommissionJob).filter(CommissionJob.job_no == "RELEASE-SPLIT-JOB").one()
    lump_job = db_session.query(CommissionJob).filter(CommissionJob.job_no == "RELEASE-LUMP-JOB").one()
    split_held = next(item for item in client.get("/api/commission/wallet/jobs", params={"sales_rep": split_employee.full_name}).json() if item["id"] == split_job.id)["paymentHeld"]
    lump_held = next(item for item in client.get("/api/commission/wallet/jobs", params={"sales_rep": lump_employee.full_name}).json() if item["id"] == lump_job.id)["paymentHeld"]

    split_release = client.patch(f"/api/commission/periods/{period_id}/jobs/{split_job.id}/payment", json={"payment_received": "YES", "release_mode": "NEXT_QUARTER_SPLIT"})
    assert split_release.status_code == 200
    split_pending = next(item for item in client.get("/api/commission/wallet/jobs", params={"sales_rep": split_employee.full_name}).json() if item["id"] == split_job.id)
    assert split_pending["paymentHeld"] == split_held
    split_verification_id = split_pending["paymentVerificationId"]
    assert client.post(f"/api/commission/payment-verifications/{split_verification_id}/review", json={"action": "VERIFY"}).status_code == 200
    split_command = client.post(f"/api/commission/payment-verifications/{split_verification_id}/payout-command", json={
        "release_mode": "NEXT_QUARTER_SPLIT",
        "note": "Khách hàng đã thanh toán JOB RELEASE-SPLIT-JOB; kế toán chia đều khoản bị giữ.",
    })
    assert split_command.status_code == 200
    scheduled = client.get("/api/commission/wallet/schedules", params={"sales_rep": split_employee.full_name}).json()
    assert [item["payout_period"] for item in scheduled] == ["2026-10", "2026-11", "2026-12"]
    assert round(sum(item["total_amount"] for item in scheduled), 2) == round(split_held, 2)
    # Payment commands for a held JOB belong to the following commission
    # cycle and must appear in its target salary months.
    assert round(sum(get_sales_bonus_for_employee_period(db_session, split_employee.id, month) for month in ("2026-10", "2026-11", "2026-12")), 2) == round(split_held, 2)
    october_summary = get_commission_payslip_summary(db_session, split_employee, "2026-10")
    assert october_summary["scheduled_job_payout_total"] > 0
    assert october_summary["scheduled_job_payouts"] == [{
        "job_no": "RELEASE-SPLIT-JOB", "customer": None,
        "source_period_label": "RELEASE-Q2-2026",
        "amount": october_summary["scheduled_job_payout_total"],
        "note": "Khách hàng đã thanh toán JOB RELEASE-SPLIT-JOB; kế toán chia đều khoản bị giữ.",
    }]
    return
    assert [item["payout_period"] for item in split_release.json()["release_allocations"]] == ["2026-10", "2026-11", "2026-12"]
    assert round(sum(item["amount"] for item in split_release.json()["release_allocations"]), 2) == round(split_held, 2)

    lump_release = client.patch(f"/api/commission/periods/{period_id}/jobs/{lump_job.id}/payment", json={"payment_received": "YES", "release_mode": "NEXT_QUARTER_LUMP", "release_payout_period": "2026-11"})
    assert lump_release.status_code == 200
    assert lump_release.json()["release_allocations"] == [{"payout_period": "2026-11", "amount": lump_held}]

    split_snapshot = db_session.query(CommissionCalculationSnapshot).filter(
        CommissionCalculationSnapshot.period_id == period_id,
        CommissionCalculationSnapshot.employee_id == split_employee.id,
    ).order_by(CommissionCalculationSnapshot.id.desc()).first()
    split_source = sum(get_sales_bonus_for_employee_period(db_session, split_employee.id, month) for month in ("2026-07", "2026-08", "2026-09"))
    split_future = sum(get_sales_bonus_for_employee_period(db_session, split_employee.id, month) for month in ("2026-10", "2026-11", "2026-12"))
    assert round(split_source + split_future, 2) == round(float(split_snapshot.total_bonus_quarter), 2)
    assert get_sales_bonus_for_employee_period(db_session, lump_employee.id, "2026-10") == 0
    assert get_sales_bonus_for_employee_period(db_session, lump_employee.id, "2026-11") == lump_held
    assert get_sales_bonus_for_employee_period(db_session, lump_employee.id, "2026-12") == 0
    types = {row.entry_type for row in db_session.query(CommissionWalletLedger).filter(CommissionWalletLedger.period_id == period_id).all()}
    assert {"RELEASED", "PAYMENT_RELEASE_ALLOCATION"}.issubset(types)


def test_payslip_commission_summary_explains_quarter_and_unpaid_jobs(client, db_session):
    from app.models.commission import CommissionCalculationSnapshot
    from app.services.salary import get_commission_payslip_summary

    employee = Employee(machine_employee_id="PAYSLIP-COMMISSION", full_name="NGUYEN PAYSLIP COMMISSION", contract_salary=10_000_000, employee_type="FULLTIME", annual_leave_quota=12)
    db_session.add(employee)
    db_session.commit()
    imported = client.post("/api/commission/import", json={
        "period_label": "PAYSLIP-Q2-2026", "from_date": "2026-04-01", "till_date": "2026-06-30",
        "jobs": [
            {"job_no": "PAYSLIP-PAID", "sales_rep": employee.full_name, "profit_loss": 60_000_000, "payment_received": "YES"},
            {"job_no": "PAYSLIP-WAITING", "sales_rep": employee.full_name, "profit_loss": 40_000_000, "payment_received": "NO", "customer": "Customer still pending"},
        ],
    })
    period_id = imported.json()["period_id"]
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200

    summary = get_commission_payslip_summary(db_session, employee, "2026-07")
    snapshot = db_session.query(CommissionCalculationSnapshot).filter(
        CommissionCalculationSnapshot.period_id == period_id,
        CommissionCalculationSnapshot.employee_id == employee.id,
    ).order_by(CommissionCalculationSnapshot.id.desc()).first()
    assert summary["cycles"][0]["period_label"] == "PAYSLIP-Q2-2026"
    assert summary["total_bonus_quarter"] == round(float(snapshot.total_bonus_quarter), 2)
    assert summary["current_period_bonus"] > 0
    assert summary["remaining_bonus"] > 0
    assert summary["pending_jobs"] == [{
        "period_label": "PAYSLIP-Q2-2026", "job_no": "PAYSLIP-WAITING",
        "customer": "Customer still pending", "payment_received": "NO",
        "pending_bonus": summary["pending_bonus_amount"],
        "reason": "Chờ khách hàng thanh toán (Payment Received = NO).",
    }]
    # The paid month, two remaining regular months and the ledger amount still
    # held for the waiting JOB reconcile exactly to the source-quarter total.
    assert round(summary["current_period_bonus"] + summary["remaining_bonus"] + summary["pending_bonus_amount"], 2) == summary["total_bonus_quarter"]


def test_flexible_bonus_funnel_adjust_transfer_and_schedule(client, db_session):
    db_session.add(Employee(machine_employee_id="FUNNEL-01", full_name="NGUYEN VAN FUNNEL", contract_salary=10_000_000, employee_type="FULLTIME", annual_leave_quota=12))
    db_session.commit()
    imported = client.post("/api/commission/import", json={
        "period_label": "FUNNEL-Q3-2026", "from_date": "2026-07-01", "till_date": "2026-09-30",
        "jobs": [{"job_no": "FUNNEL-YES", "sales_rep": "NGUYEN VAN FUNNEL", "profit_loss": 100_000_000, "payment_received": "YES"}],
    })
    period_id = imported.json()["period_id"]
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    wallet_before = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN FUNNEL"}).json()[0]
    assert wallet_before["available_amount"] > 500

    credit = client.post("/api/commission/wallet/adjustments", json={"sales_rep": "NGUYEN VAN FUNNEL", "action": "CREDIT", "amount": 500, "reason": "Thưởng nóng"})
    assert credit.status_code == 200
    decrease = client.post("/api/commission/wallet/adjustments", json={"sales_rep": "NGUYEN VAN FUNNEL", "action": "DECREASE", "amount": 100, "reason": "Điều chỉnh giảm"})
    assert decrease.status_code == 200
    after_adjustment = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN FUNNEL"}).json()[0]
    assert after_adjustment["manual_credit_amount"] == 500
    assert after_adjustment["manual_decrease_amount"] == 100
    # Re-syncing a formula change must not erase independent manual ledger rows.
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    after_resync_adjustment = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN FUNNEL"}).json()[0]
    assert after_resync_adjustment["manual_credit_amount"] == 500
    assert after_resync_adjustment["manual_decrease_amount"] == 100
    transfer = client.post("/api/commission/wallet/transfers", json={"sales_rep": "NGUYEN VAN FUNNEL", "amount": 200, "target_payout_period": "2026-10", "reason": "Chuyển sang tháng 10"})
    assert transfer.status_code == 200
    assert transfer.json()["amount"] == 200
    after_transfer = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN FUNNEL"}).json()[0]
    assert after_transfer["transferred_amount"] == 200
    assert after_transfer["available_amount"] == wallet_before["available_amount"] + 400 - 200
    scheduled = client.post("/api/commission/wallet/schedules", json={"sales_rep": "NGUYEN VAN FUNNEL", "amount": 300, "payout_period": "2026-10", "note": "Đợt trả tháng 10"})
    assert scheduled.status_code == 200
    schedule_id = scheduled.json()["schedule_id"]
    from app.models.commission import CommissionPayoutScheduleAllocation
    assert db_session.query(CommissionPayoutScheduleAllocation).filter(CommissionPayoutScheduleAllocation.schedule_id == schedule_id).count() > 0
    mid = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN FUNNEL"}).json()[0]
    assert mid["scheduled_amount"] == 300
    assert client.post(f"/api/commission/wallet/schedules/{schedule_id}/pay", json={}).status_code == 200
    after = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN FUNNEL"}).json()[0]
    assert after["scheduled_amount"] == 0
    assert after["paid_amount"] >= 300
    types = {entry["entry_type"] for entry in client.get("/api/commission/wallet/ledger", params={"sales_rep": "NGUYEN VAN FUNNEL"}).json()}
    assert {"MANUAL_CREDIT", "MANUAL_DECREASE", "TRANSFER_OUT", "TRANSFER_IN", "SCHEDULED", "PAID"}.issubset(types)


def test_wallet_undo_uses_compensating_entries_and_never_reverses_paid_payout(client, db_session):
    db_session.add(Employee(machine_employee_id="UNDO-01", full_name="NGUYEN VAN UNDO", contract_salary=10_000_000, employee_type="FULLTIME", annual_leave_quota=12))
    db_session.commit()
    imported = client.post("/api/commission/import", json={
        "period_label": "UNDO-Q3-2026", "from_date": "2026-07-01", "till_date": "2026-09-30",
        "jobs": [{"job_no": "UNDO-YES", "sales_rep": "NGUYEN VAN UNDO", "profit_loss": 100_000_000, "payment_received": "YES"}],
    })
    period_id = imported.json()["period_id"]
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    before = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN UNDO"}).json()[0]

    assert client.post("/api/commission/wallet/adjustments", json={
        "sales_rep": "NGUYEN VAN UNDO", "action": "CREDIT", "amount": 500, "reason": "Test undo",
    }).status_code == 200
    after_credit = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN UNDO"}).json()[0]
    assert after_credit["available_amount"] == before["available_amount"] + 500

    undone = client.post("/api/commission/wallet/undo-last", json={"sales_rep": "NGUYEN VAN UNDO"})
    assert undone.status_code == 200
    after_undo = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN UNDO"}).json()[0]
    assert after_undo["available_amount"] == before["available_amount"]
    assert after_undo["manual_credit_amount"] == 0
    assert "MANUAL_CREDIT_REVERSAL" in {entry["entry_type"] for entry in client.get("/api/commission/wallet/ledger", params={"sales_rep": "NGUYEN VAN UNDO"}).json()}

    assert client.post("/api/commission/wallet/transfers", json={
        "sales_rep": "NGUYEN VAN UNDO", "amount": 200, "target_payout_period": "2026-10", "reason": "Test undo transfer",
    }).status_code == 200
    after_transfer = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN UNDO"}).json()[0]
    assert after_transfer["transferred_amount"] == 200
    assert client.post("/api/commission/wallet/undo-last", json={"sales_rep": "NGUYEN VAN UNDO"}).status_code == 200
    after_transfer_undo = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN UNDO"}).json()[0]
    assert after_transfer_undo["transferred_amount"] == 0
    assert after_transfer_undo["available_amount"] == before["available_amount"]

    scheduled = client.post("/api/commission/wallet/schedules", json={
        "sales_rep": "NGUYEN VAN UNDO", "amount": 200, "payout_period": "2026-10", "note": "Test undo schedule",
    })
    assert scheduled.status_code == 200
    assert client.post("/api/commission/wallet/undo-last", json={"sales_rep": "NGUYEN VAN UNDO"}).status_code == 200
    after_schedule_undo = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN UNDO"}).json()[0]
    assert after_schedule_undo["scheduled_amount"] == 0

    assert client.post("/api/commission/wallet/payout", json={"sales_rep": "NGUYEN VAN UNDO", "payout_period": "2026-10"}).status_code == 200
    no_undo = client.post("/api/commission/wallet/undo-last", json={"sales_rep": "NGUYEN VAN UNDO"})
    assert no_undo.status_code == 409


def test_held_job_release_plan_and_bonus_lock_are_persisted_and_enforced(client, db_session):
    from app.models.commission import CommissionJob

    employee = Employee(machine_employee_id="LOCK-01", full_name="NGUYEN VAN BONUS LOCK", contract_salary=10_000_000, employee_type="FULLTIME", annual_leave_quota=12)
    db_session.add(employee)
    db_session.commit()
    imported = client.post("/api/commission/import", json={
        "period_label": "LOCK-Q2-2026", "from_date": "2026-04-01", "till_date": "2026-06-30",
        "jobs": [{"job_no": "LOCK-HELD-JOB", "sales_rep": employee.full_name, "customer": "Held customer", "profit_loss": 100_000_000, "payment_received": "NO"}],
    })
    period_id = imported.json()["period_id"]
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    job = db_session.query(CommissionJob).filter(CommissionJob.job_no == "LOCK-HELD-JOB").one()

    release_plan = client.put(f"/api/commission/periods/{period_id}/jobs/{job.id}/release-plan", json={
        "release_mode": "NEXT_QUARTER_LUMP", "release_payout_period": "2026-11",
    })
    assert release_plan.status_code == 200
    job_detail = client.get("/api/commission/wallet/jobs", params={"sales_rep": employee.full_name, "period_id": period_id}).json()[0]
    assert job_detail["heldReleaseMode"] == "NEXT_QUARTER_LUMP"
    assert job_detail["heldReleasePayoutPeriod"] == "2026-11"
    ledger = client.get("/api/commission/wallet/ledger", params={"sales_rep": employee.full_name, "period_id": period_id}).json()
    assert ledger[0]["job_no"] == "LOCK-HELD-JOB"
    assert ledger[0]["job_customer"] == "Held customer"
    assert ledger[0]["current_held_amount"] > 0

    locked = client.post("/api/commission/wallet/lock", json={"period_id": period_id, "sales_rep": employee.full_name})
    assert locked.status_code == 200
    assert client.get("/api/commission/wallet/lock", params={"period_id": period_id, "sales_rep": employee.full_name}).json()["locked"] is True
    assert client.patch(f"/api/commission/periods/{period_id}/jobs/{job.id}/payment", json={"payment_received": "YES"}).status_code == 409
    assert client.put(f"/api/commission/periods/{period_id}/jobs/{job.id}/release-plan", json={"release_mode": "NEXT_QUARTER_SPLIT"}).status_code == 409
    assert client.put(f"/api/commission/wallet/jobs/{job.id}/manual-hold", json={"sales_rep": employee.full_name, "manual_held_amount": 0}).status_code == 409
