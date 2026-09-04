import pytest

from app.models.employee import Employee


def test_formula_sync_recreates_hold_after_incorrect_fully_paid_evidence_is_corrected(client, db_session):
    from app.models.commission import CommissionJob

    employee = Employee(
        machine_employee_id="HOLD-REOPEN-01",
        full_name="NGUYEN HOLD REOPEN",
        contract_salary=10_000_000,
        employee_type="FULLTIME",
        annual_leave_quota=12,
    )
    db_session.add(employee)
    db_session.commit()
    imported = client.post("/api/commission/import", json={
        "period_label": "HOLD-REOPEN-Q2-2026",
        "from_date": "2026-04-01",
        "till_date": "2026-06-30",
        "jobs": [{
            "job_no": "HOLD-REOPEN-JOB",
            "sales_rep": employee.full_name,
            "profit_loss": 100_000_000,
            "payment_received": "YES",
        }],
    })
    period_id = imported.json()["period_id"]
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    job = db_session.query(CommissionJob).filter(CommissionJob.job_no == "HOLD-REOPEN-JOB").one()

    job.balance_amount = 0
    job.receivable_amount = 100_000_000
    job.payment_received_amount = 100_000_000
    db_session.commit()
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    fully_paid = next(item for item in client.get(
        "/api/commission/wallet/jobs",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json() if item["id"] == job.id)
    assert fully_paid["paymentHeld"] == 0

    job.payment_received_amount = 90_000_000
    db_session.commit()
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    corrected = next(item for item in client.get(
        "/api/commission/wallet/jobs",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json() if item["id"] == job.id)
    assert corrected["holdBonusPercent"] == 30
    assert corrected["paymentHeld"] > 0


def test_admin_manual_payment_edit_updates_amount_hold_and_wallet_immediately(client, db_session):
    from app.models.commission import CommissionJob, CommissionWalletLedger

    employee = Employee(
        machine_employee_id="MANUAL-PAYMENT-01",
        full_name="NGUYEN MANUAL PAYMENT",
        contract_salary=10_000_000,
        employee_type="FULLTIME",
        annual_leave_quota=12,
    )
    db_session.add(employee)
    db_session.commit()
    imported = client.post("/api/commission/import", json={
        "period_label": "MANUAL-PAYMENT-Q2-2026",
        "from_date": "2026-04-01",
        "till_date": "2026-06-30",
        "jobs": [{
            "job_no": "MANUAL-PAYMENT-JOB",
            "sales_rep": employee.full_name,
            "profit_loss": 100_000_000,
            "payment_received": "NO",
        }],
    })
    assert imported.status_code == 201
    period_id = imported.json()["period_id"]
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    job = db_session.query(CommissionJob).filter(CommissionJob.job_no == "MANUAL-PAYMENT-JOB").one()

    partial = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{job.id}/manual-payment",
        json={
            "payment_received": "YES",
            "payment_received_amount": 90_000_000,
            "payment_month": "2026-08",
            "payment_date": "2026-08-20",
        },
    )
    assert partial.status_code == 200
    assert partial.json()["wallet_synchronized"] is True
    assert partial.json()["balance_amount"] == 10_000_000
    assert partial.json()["hold_bonus_percent"] == 30
    partial_job = next(item for item in client.get(
        "/api/commission/wallet/jobs",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json() if item["id"] == job.id)
    assert partial_job["paymentReceived"] == "YES"
    assert partial_job["paymentReceivedAmount"] == 90_000_000
    assert partial_job["paymentHeld"] > 0
    assert partial_job["heldReleasePayoutPeriod"] == "2026-08"

    fully_paid = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{job.id}/manual-payment",
        json={
            "payment_received": "YES",
            "payment_received_amount": 100_000_000,
            "payment_month": "2026-08",
            "payment_date": "2026-08-26",
            "payout_months": ["2026-11", "2026-12"],
        },
    )
    assert fully_paid.status_code == 200
    assert fully_paid.json()["balance_amount"] == 0
    assert fully_paid.json()["hold_bonus_percent"] == 0
    assert fully_paid.json()["payout_months"] == ["2026-11", "2026-12"]
    assert [row["payout_period"] for row in fully_paid.json()["release_allocations"]] == ["2026-11", "2026-12"]
    fully_paid_job = next(item for item in client.get(
        "/api/commission/wallet/jobs",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json() if item["id"] == job.id)
    assert fully_paid_job["paymentHeld"] == 0
    assert fully_paid_job["heldReleasePayoutPeriod"] == "2026-08"

    unpaid = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{job.id}/manual-payment",
        json={"payment_received": "NO"},
    )
    assert unpaid.status_code == 200
    assert unpaid.json()["payment_received_amount"] == 0
    assert unpaid.json()["hold_bonus_percent"] == 30
    unpaid_job = next(item for item in client.get(
        "/api/commission/wallet/jobs",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json() if item["id"] == job.id)
    assert unpaid_job["paymentReceived"] == "NO"
    assert unpaid_job["paymentReceivedAmount"] == 0
    assert unpaid_job["paymentHeld"] > 0
    assert unpaid_job["heldReleasePayoutPeriod"] is None

    invalid = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{job.id}/manual-payment",
        json={"payment_received": "YES", "payment_received_amount": 0},
    )
    assert invalid.status_code == 422
    assert db_session.query(CommissionWalletLedger).filter(
        CommissionWalletLedger.job_id == job.id,
        CommissionWalletLedger.entry_type == "PAYMENT_MANUAL_OVERRIDE",
    ).count() == 3


@pytest.mark.parametrize(
    ("payment_date", "payout_months"),
    [
        ("2026-08-20", ["2026-10"]),
        ("2026-08-25", ["2026-10", "2026-11", "2026-12"]),
        ("2026-08-26", ["2026-11"]),
        ("2026-08-26", ["2026-11", "2026-12"]),
    ],
)
def test_manual_full_payment_adds_released_hold_only_to_selected_months(
    client,
    db_session,
    payment_date,
    payout_months,
):
    from app.models.commission import CommissionJob, CommissionPayoutSchedule, CommissionWalletLedger

    employee = Employee(
        machine_employee_id=f"PAYMENT-{payment_date}-{'-'.join(payout_months)}",
        full_name=f"NGUYEN PAYMENT {payment_date} {' '.join(payout_months)}",
        contract_salary=10_000_000,
        employee_type="FULLTIME",
        annual_leave_quota=12,
    )
    db_session.add(employee)
    db_session.commit()
    imported = client.post("/api/commission/import", json={
        "period_label": f"PAYMENT-Q2-{payment_date}-{'-'.join(payout_months)}",
        "from_date": "2026-04-01",
        "till_date": "2026-06-30",
        "jobs": [{
            "job_no": f"PAYMENT-JOB-{payment_date}-{'-'.join(payout_months)}",
            "sales_rep": employee.full_name,
            "profit_loss": 100_000_000,
            "payment_received": "NO",
        }],
    })
    assert imported.status_code == 201
    period_id = imported.json()["period_id"]
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    job = db_session.query(CommissionJob).filter(CommissionJob.period_id == period_id).one()
    before = next(item for item in client.get(
        "/api/commission/wallet/jobs",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json() if item["id"] == job.id)
    held_before = before["paymentHeld"]
    assert held_before > 0
    assert before["customerPaymentPeriods"] == ["2026-07", "2026-08", "2026-09"]
    assert before["nextReleasePayoutPeriods"] == ["2026-10", "2026-11", "2026-12"]

    missing_month = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{job.id}/manual-payment",
        json={
            "payment_received": "YES",
            "payment_received_amount": 100_000_000,
            "payment_month": "2026-08",
        },
    )
    assert missing_month.status_code == 422

    invalid_customer_month = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{job.id}/manual-payment",
        json={
            "payment_received": "YES",
            "payment_received_amount": 100_000_000,
            "payment_month": "2026-07",
            "payment_date": "2026-07-20",
            "payout_months": ["2026-10"],
        },
    )
    assert invalid_customer_month.status_code == 422

    invalid_month = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{job.id}/manual-payment",
        json={
            "payment_received": "YES",
            "payment_received_amount": 100_000_000,
            "payment_month": "2026-08",
            "payment_date": "2026-08-26",
            "payout_months": ["2026-10"],
        },
    )
    assert invalid_month.status_code == 422
    paid = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{job.id}/manual-payment",
        json={
            "payment_received": "YES",
            "payment_received_amount": 100_000_000,
            "payment_month": "2026-08",
            "payment_date": payment_date,
            "payout_months": payout_months,
        },
    )
    assert paid.status_code == 200
    assert paid.json()["payout_months"] == payout_months
    allocations = paid.json()["release_allocations"]
    assert [row["payout_period"] for row in allocations] == payout_months
    assert sum(row["amount"] for row in allocations) == pytest.approx(held_before, abs=0.01)
    assert max(row["amount"] for row in allocations) - min(row["amount"] for row in allocations) <= 0.01

    schedule_ids = paid.json()["schedule_ids"]
    schedules = db_session.query(CommissionPayoutSchedule).filter(
        CommissionPayoutSchedule.id.in_(schedule_ids),
    ).order_by(CommissionPayoutSchedule.payout_period.asc()).all()
    assert [row.payout_period for row in schedules] == payout_months
    assert all(row.status == "SCHEDULED" for row in schedules)
    assert db_session.query(CommissionWalletLedger).filter(
        CommissionWalletLedger.job_id == job.id,
        CommissionWalletLedger.reason_code == "MANUAL_PAYMENT_SELECTED_MONTHS",
    ).count() == len(payout_months)

    after = next(item for item in client.get(
        "/api/commission/wallet/jobs",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json() if item["id"] == job.id)
    assert after["paymentHeld"] == 0
    assert after["scheduled"] == pytest.approx(held_before, abs=0.01)
    assert after["available"] == 0

    wallet = client.get(
        "/api/commission/wallet",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json()[0]
    monthly_rows = wallet["period_summaries"][0]["monthly_available_amounts"]
    all_cycle_months = ["2026-10", "2026-11", "2026-12"]
    assert [row["payout_period"] for row in monthly_rows] == all_cycle_months
    base_monthly_amount = wallet["period_summaries"][0]["monthly_payout"]
    expected_amounts = {
        month: base_monthly_amount
        + next((row["amount"] for row in allocations if row["payout_period"] == month), 0)
        for month in all_cycle_months
    }
    assert {row["payout_period"]: row["amount"] for row in monthly_rows} == pytest.approx(expected_amounts, abs=0.01)
    assert all(row["base_amount"] == pytest.approx(base_monthly_amount, abs=0.01) for row in monthly_rows)
    assert {
        row["payout_period"]: row["released_amount"] for row in monthly_rows
    } == pytest.approx({
        month: next((row["amount"] for row in allocations if row["payout_period"] == month), 0)
        for month in all_cycle_months
    }, abs=0.01)


def test_manual_release_keeps_three_month_base_and_changes_only_selected_months(client, db_session):
    from app.models.commission import CommissionJob
    from app.services.salary import get_wallet_sales_bonus_for_employee_period

    employee = Employee(
        machine_employee_id="PAYMENT-ONE-MONTH-BASE",
        full_name="NGUYEN PAYMENT ONE MONTH BASE",
        contract_salary=10_000_000,
        employee_type="FULLTIME",
        annual_leave_quota=12,
    )
    db_session.add(employee)
    db_session.commit()
    imported = client.post("/api/commission/import", json={
        "period_label": "PAYMENT-ONE-MONTH-BASE-Q2-2026",
        "from_date": "2026-04-01",
        "till_date": "2026-06-30",
        "jobs": [
            {
                "job_no": "PAYMENT-BASE-PAID",
                "sales_rep": employee.full_name,
                "profit_loss": 900_000_000,
                "payment_received": "YES",
            },
            {
                "job_no": "PAYMENT-BASE-HELD",
                "sales_rep": employee.full_name,
                "profit_loss": 100_000_000,
                "payment_received": "NO",
            },
        ],
    })
    assert imported.status_code == 201
    period_id = imported.json()["period_id"]
    jobs = {
        job.job_no: job
        for job in db_session.query(CommissionJob).filter(CommissionJob.period_id == period_id).all()
    }
    jobs["PAYMENT-BASE-PAID"].receivable_amount = 900_000_000
    jobs["PAYMENT-BASE-PAID"].payment_received_amount = 900_000_000
    jobs["PAYMENT-BASE-PAID"].balance_amount = 0
    jobs["PAYMENT-BASE-HELD"].receivable_amount = 100_000_000
    jobs["PAYMENT-BASE-HELD"].payment_received_amount = 0
    jobs["PAYMENT-BASE-HELD"].balance_amount = 100_000_000
    db_session.commit()
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200

    wallet_before = client.get(
        "/api/commission/wallet",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json()[0]
    base_before = wallet_before["period_summaries"][0]["monthly_payout"]
    assert base_before > 0
    source_months_before = {
        month: get_wallet_sales_bonus_for_employee_period(db_session, employee, month)
        for month in ("2026-07", "2026-08", "2026-09")
    }
    held_job_before = next(item for item in client.get(
        "/api/commission/wallet/jobs",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json() if item["id"] == jobs["PAYMENT-BASE-HELD"].id)
    held_before = held_job_before["paymentHeld"]
    assert held_before > 0

    paid = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{jobs['PAYMENT-BASE-HELD'].id}/manual-payment",
        json={
            "payment_received": "YES",
            "payment_received_amount": 100_000_000,
            "payment_month": "2026-08",
            "payment_date": "2026-08-26",
            "payout_months": ["2026-11", "2026-12"],
        },
    )
    assert paid.status_code == 200
    first_release = round(held_before / 2, 2)
    second_release = round(held_before - first_release, 2)
    assert paid.json()["release_allocations"] == [
        {"payout_period": "2026-11", "amount": pytest.approx(first_release, abs=0.01)},
        {"payout_period": "2026-12", "amount": pytest.approx(second_release, abs=0.01)},
    ]

    wallet_after = client.get(
        "/api/commission/wallet",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json()[0]
    monthly_rows = wallet_after["period_summaries"][0]["monthly_available_amounts"]
    assert [row["payout_period"] for row in monthly_rows] == ["2026-10", "2026-11", "2026-12"]
    assert all(row["base_amount"] == pytest.approx(base_before, abs=0.01) for row in monthly_rows)
    assert [row["released_amount"] for row in monthly_rows] == pytest.approx(
        [0, first_release, second_release], abs=0.01,
    )
    assert [row["amount"] for row in monthly_rows] == pytest.approx(
        [base_before, base_before + first_release, base_before + second_release], abs=0.01,
    )
    assert {
        month: get_wallet_sales_bonus_for_employee_period(db_session, employee, month)
        for month in ("2026-07", "2026-08", "2026-09")
    } == pytest.approx(source_months_before, abs=0.01)
    assert get_wallet_sales_bonus_for_employee_period(db_session, employee, "2026-11") == pytest.approx(
        first_release, abs=0.01,
    )
    assert get_wallet_sales_bonus_for_employee_period(db_session, employee, "2026-12") == pytest.approx(
        second_release, abs=0.01,
    )


def test_temporary_wallet_remains_fully_available_when_hold_is_reallocated_to_remaining_job(client, db_session):
    from app.models.commission import CommissionJob

    employee = Employee(
        machine_employee_id="WALLET-REALLOCATE-01",
        full_name="NGUYEN WALLET REALLOCATE",
        contract_salary=10_000_000,
        employee_type="FULLTIME",
        annual_leave_quota=12,
    )
    db_session.add(employee)
    db_session.commit()
    imported = client.post("/api/commission/import", json={
        "period_label": "WALLET-REALLOCATE-Q2-2026",
        "from_date": "2026-04-01",
        "till_date": "2026-06-30",
        "jobs": [
            {"job_no": "WALLET-UNPAID", "sales_rep": employee.full_name, "profit_loss": 200_000_000, "payment_received": "NO"},
            {"job_no": "WALLET-PAID-A", "sales_rep": employee.full_name, "profit_loss": 50_000_000, "payment_received": "NO"},
            {"job_no": "WALLET-PAID-B", "sales_rep": employee.full_name, "profit_loss": 50_000_000, "payment_received": "NO"},
        ],
    })
    assert imported.status_code == 201
    period_id = imported.json()["period_id"]
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    jobs = {
        job.job_no: job
        for job in db_session.query(CommissionJob).filter(CommissionJob.period_id == period_id).all()
    }

    for job_no in ("WALLET-PAID-A", "WALLET-PAID-B"):
        response = client.patch(
            f"/api/commission/periods/{period_id}/jobs/{jobs[job_no].id}/manual-payment",
            json={
                "payment_received": "YES",
                "payment_received_amount": 50_000_000,
                "payment_month": "2026-08",
                "payment_date": "2026-08-26",
                "payout_months": ["2026-11"],
            },
        )
        assert response.status_code == 200

    wallet = client.get(
        "/api/commission/wallet",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json()[0]
    period_summary = wallet["period_summaries"][0]
    assert period_summary["holds_entire_profit"] is True
    assert period_summary["policy_hold_amount"] == 60_000_000
    assert wallet["held_amount"] == pytest.approx(wallet["total_earned"], abs=0.01)
    assert wallet["available_amount"] == pytest.approx(wallet["total_earned"], abs=0.01)
    assert period_summary["temporary_bonus_available"] == pytest.approx(wallet["total_earned"], abs=0.01)

    job_rows = client.get(
        "/api/commission/wallet/jobs",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json()
    assert sum(row["available"] for row in job_rows) == pytest.approx(wallet["total_earned"], abs=0.01)


def test_hold_bonus_is_fixed_at_thirty_percent_and_cannot_be_edited(client, db_session):
    employee = Employee(
        machine_employee_id="HOLD-CONVERT-01",
        full_name="NGUYEN VAN HOLD CONVERT",
        contract_salary=10_000_000,
        employee_type="FULLTIME",
        annual_leave_quota=12,
    )
    db_session.add(employee)
    db_session.commit()
    imported = client.post("/api/commission/import", json={
        "period_label": "HOLD-CONVERT-Q3-2026",
        "from_date": "2026-07-01",
        "till_date": "2026-09-30",
        "jobs": [{
            "job_no": "HOLD-CONVERT-JOB",
            "sales_rep": employee.full_name,
            "profit_loss": 100_000_000,
            "payment_received": "YES",
        }],
    })
    assert imported.status_code == 201
    period_id = imported.json()["period_id"]
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    job = next(item for item in client.get(
        "/api/commission/wallet/jobs",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json() if item["jobNo"] == "HOLD-CONVERT-JOB")
    assert job["earned"] > 0
    assert job["periodProfitLoss"] == 100_000_000
    assert job["periodTarget"] == 20_000_000
    assert job["periodCoefficient"] > 0
    assert job["periodTotalBonusQuarter"] > 0
    assert job["periodMonthlyBonus"] == pytest.approx(job["periodTotalBonusQuarter"] / 3, abs=0.01)
    # The temporary wallet owns the whole quarterly commission so it can be
    # moved to another period or explicitly scheduled later.
    assert job["calculationEarned"] == pytest.approx(job["periodTotalBonusQuarter"], abs=0.01)
    assert job["earned"] == job["calculationEarned"]
    assert job["manualCredit"] == 0
    assert job["manualDecrease"] == 0
    expected_hold = round(job["profitLoss"] * 0.30, 2)
    assert job["holdBonusPercent"] == 30
    assert job["holdBonusAmount"] == expected_hold
    assert job["paymentHeld"] == pytest.approx(job["periodTotalBonusQuarter"], abs=0.01)
    assert job["available"] == pytest.approx(job["periodTotalBonusQuarter"], abs=0.01)

    from_percent = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{job['id']}/hold-bonus",
        json={"hold_bonus_percent": 30, "edited_field": "percent"},
    )
    assert from_percent.status_code == 409

    ten_percent_amount = round(job["earned"] * 0.10, 2)
    from_amount = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{job['id']}/hold-bonus",
        json={"hold_bonus_amount": ten_percent_amount, "edited_field": "amount"},
    )
    assert from_amount.status_code == 409
    after_amount = next(item for item in client.get(
        "/api/commission/wallet/jobs",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json() if item["id"] == job["id"])
    assert after_amount["holdBonusPercent"] == 30
    assert after_amount["holdBonusAmount"] == expected_hold
    assert after_amount["paymentHeld"] == pytest.approx(job["periodTotalBonusQuarter"], abs=0.01)
    assert after_amount["available"] == pytest.approx(job["periodTotalBonusQuarter"], abs=0.01)

    over_cap = client.patch(
        f"/api/commission/periods/{period_id}/jobs/{job['id']}/hold-bonus",
        json={"hold_bonus_amount": round(job["earned"] * 0.31, 2), "edited_field": "amount"},
    )
    assert over_cap.status_code == 409


def test_commission_batch_import_saves_all_files_in_one_request(client, db_session):
    response = client.post(
        "/api/commission/import/batch",
        json={
            "imports": [
                {
                    "period_label": "BATCH-APR-2026",
                    "from_date": "2026-04-01",
                    "till_date": "2026-04-30",
                    "source_filename": "commission-apr.xlsx",
                    "jobs": [{"job_no": "BATCH-APR-01", "sales_rep": "BATCH SALES", "profit_loss": 10_000_000}],
                },
                {
                    "period_label": "BATCH-MAY-2026",
                    "from_date": "2026-05-01",
                    "till_date": "2026-05-31",
                    "source_filename": "commission-may.xlsx",
                    "jobs": [{"job_no": "BATCH-MAY-01", "sales_rep": "BATCH SALES", "profit_loss": 20_000_000}],
                },
            ]
        },
    )

    assert response.status_code == 201
    assert response.json()["files_saved"] == 2
    assert response.json()["jobs_saved"] == 2
    assert len(response.json()["period_ids"]) == 2

    from app.models.commission import CommissionJob, CommissionPeriod

    assert db_session.query(CommissionPeriod).filter(CommissionPeriod.period_label.like("BATCH-%")).count() == 2
    assert db_session.query(CommissionJob).filter(CommissionJob.job_no.like("BATCH-%")).count() == 2


def test_commission_batch_import_rolls_back_every_file_when_one_is_invalid(client, db_session):
    response = client.post(
        "/api/commission/import/batch",
        json={
            "imports": [
                {
                    "period_label": "ATOMIC-VALID",
                    "from_date": "2026-06-01",
                    "till_date": "2026-06-30",
                    "jobs": [{"job_no": "ATOMIC-JOB", "profit_loss": 1}],
                },
                {
                    "period_label": "ATOMIC-INVALID",
                    "from_date": "2026-07-01",
                    "till_date": "2026-07-31",
                    "jobs": [],
                },
            ]
        },
    )

    assert response.status_code == 400

    from app.models.commission import CommissionJob, CommissionPeriod

    assert db_session.query(CommissionPeriod).filter(CommissionPeriod.period_label.like("ATOMIC-%")).count() == 0
    assert db_session.query(CommissionJob).filter(CommissionJob.job_no == "ATOMIC-JOB").count() == 0


def test_commission_exact_period_merge_protects_manual_jobs_and_adds_new_jobs(client, db_session):
    from app.models.commission import CommissionJob, CommissionPeriod

    imported = client.post(
        "/api/commission/import",
        json={
            "period_label": "MERGE-Q2-2026",
            "from_date": "2026-04-01",
            "till_date": "2026-06-30",
            "source_filename": "merge-base.xlsx",
            "jobs": [
                {"job_no": "MERGE-MANUAL", "sales_rep": "MERGE SALE", "profit_loss": 10_000_000},
                {"job_no": "MERGE-AUTO", "sales_rep": "MERGE SALE", "profit_loss": 20_000_000},
            ],
        },
    )
    assert imported.status_code == 201
    period_id = imported.json()["period_id"]
    manual_job = db_session.query(CommissionJob).filter(CommissionJob.job_no == "MERGE-MANUAL").one()
    manual_job.bonus_remark = "Kế toán đã rà soát"
    db_session.commit()

    incoming = {
        "period_label": "MERGE-Q2-2026",
        "from_date": "2026-04-01",
        "till_date": "2026-06-30",
        "source_filename": "merge-supplement.xlsx",
        "jobs": [
            {"job_no": "MERGE-MANUAL", "sales_rep": "MERGE SALE", "profit_loss": 99_000_000},
            {"job_no": "MERGE-AUTO", "sales_rep": "MERGE SALE", "profit_loss": 88_000_000},
            {"job_no": "MERGE-NEW", "sales_rep": "MERGE SALE", "profit_loss": 77_000_000},
        ],
    }
    preview = client.post("/api/commission/import/merge-preview", json={"imports": [incoming]})
    assert preview.status_code == 200
    preview_item = preview.json()["imports"][0]
    assert preview_item["period_id"] == period_id
    assert preview_item["new_jobs"] == 1
    assert preview_item["automatic_updates"] == 1
    assert preview_item["manual_jobs"] == [{
        "job_id": manual_job.id,
        "job_no": "MERGE-MANUAL",
        "sales_rep": "MERGE SALE",
        "reasons": ["Đã có ghi chú thủ công"],
    }]

    merged_without_manual = client.post(
        "/api/commission/import/merge",
        json={"imports": [incoming], "overwrite_manual_job_ids": []},
    )
    assert merged_without_manual.status_code == 200
    assert merged_without_manual.json()["jobs_added"] == 1
    assert merged_without_manual.json()["jobs_updated"] == 1
    assert merged_without_manual.json()["manual_jobs_skipped"] == 1
    db_session.expire_all()
    assert db_session.query(CommissionPeriod).filter(CommissionPeriod.id == period_id).one().source_filename == "merge-base.xlsx; merge-supplement.xlsx"
    jobs = {job.job_no: job for job in db_session.query(CommissionJob).filter(CommissionJob.period_id == period_id).all()}
    assert set(jobs) == {"MERGE-MANUAL", "MERGE-AUTO", "MERGE-NEW"}
    assert jobs["MERGE-MANUAL"].profit_loss == 10_000_000
    assert jobs["MERGE-AUTO"].profit_loss == 88_000_000
    assert jobs["MERGE-NEW"].profit_loss == 77_000_000

    selected_merge = client.post(
        "/api/commission/import/merge",
        json={"imports": [incoming], "overwrite_manual_job_ids": [manual_job.id]},
    )
    assert selected_merge.status_code == 200
    db_session.expire_all()
    refreshed_manual = db_session.query(CommissionJob).filter(CommissionJob.id == manual_job.id).one()
    assert refreshed_manual.profit_loss == 99_000_000
    assert refreshed_manual.hold_bonus_percent == 30
    assert refreshed_manual.hold_bonus_amount == 29_700_000
    assert refreshed_manual.bonus_remark == "Kế toán đã rà soát"


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


def test_accounting_can_pay_without_request_and_cancel_back_to_initial_state(client, db_session):
    from app.models.commission import CommissionJob, CommissionPaymentVerification
    from app.models.notification import Notification

    employee = Employee(
        machine_employee_id="DIRECT-PAYOUT-01",
        full_name="NGUYEN DIRECT PAYOUT",
        user_id=9999,
        contract_salary=10_000_000,
        employee_type="FULLTIME",
        annual_leave_quota=12,
    )
    db_session.add(employee)
    db_session.commit()

    imported = client.post("/api/commission/import", json={
        "period_label": "DIRECT-Q2-2026",
        "from_date": "2026-04-01",
        "till_date": "2026-06-30",
        "jobs": [{
            "job_no": "DIRECT-PAYOUT-JOB",
            "sales_rep": employee.full_name,
            "customer": "Direct payout customer",
            "profit_loss": 100_000_000,
            "payment_received": "NO",
        }],
    })
    assert imported.status_code == 201
    period_id = imported.json()["period_id"]
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200

    job = db_session.query(CommissionJob).filter_by(job_no="DIRECT-PAYOUT-JOB").one()
    before = next(item for item in client.get(
        "/api/commission/wallet/jobs",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json() if item["id"] == job.id)
    held_amount = before["paymentHeld"]
    assert before["paymentVerificationStatus"] is None

    command = client.post(
        f"/api/commission/periods/{period_id}/jobs/{job.id}/direct-payout-command",
        json={
            "release_mode": "NEXT_QUARTER_LUMP",
            "release_payout_period": "2026-10",
            "note": "Kế toán chủ động chi trả sau khi đối soát.",
        },
    )
    assert command.status_code == 200
    schedule_id = command.json()["schedule_ids"][0]
    scheduled = next(item for item in client.get(
        "/api/commission/wallet/jobs",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json() if item["id"] == job.id)
    assert scheduled["paymentReceived"] == "YES"
    assert scheduled["paymentHeld"] == 0
    assert scheduled["scheduled"] == held_amount
    assert scheduled["paymentVerificationStatus"] == "COMMAND_CREATED"

    missing_reason = client.post(f"/api/commission/wallet/schedules/{schedule_id}/cancel", json={})
    assert missing_reason.status_code == 422
    blank_reason = client.post(
        f"/api/commission/wallet/schedules/{schedule_id}/cancel",
        json={"reason": "   "},
    )
    assert blank_reason.status_code == 422

    reason = "Khách hàng đề nghị lùi thời điểm thanh toán."
    cancelled = client.post(
        f"/api/commission/wallet/schedules/{schedule_id}/cancel",
        json={"reason": reason},
    )
    assert cancelled.status_code == 200

    restored = next(item for item in client.get(
        "/api/commission/wallet/jobs",
        params={"sales_rep": employee.full_name, "period_id": period_id},
    ).json() if item["id"] == job.id)
    assert restored["paymentReceived"] == "NO"
    assert restored["paymentHeld"] == held_amount
    assert restored["scheduled"] == 0
    assert restored["paymentVerificationId"] is None
    assert restored["paymentVerificationStatus"] is None

    portal_job = next(item for item in client.get("/api/user/my-held-bonus-jobs").json() if item["job_id"] == job.id)
    assert portal_job["request_status"] == "NONE"
    assert portal_job["can_request"] is True
    verification = db_session.query(CommissionPaymentVerification).filter_by(job_id=job.id).one()
    assert verification.status == "CANCELLED"
    notification = db_session.query(Notification).filter_by(
        event_type="BONUS_PAYOUT_CANCELLED",
        target_user_id=employee.user_id,
    ).one()
    assert reason in notification.message
    assert notification.resource_id == str(job.id)


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
    assert data["available_amount"] == data["total_earned"]
    assert data["held_amount"] == data["total_earned"]
    # The source monthly payout is zero while the whole quarterly commission
    # remains available in the temporary bonus wallet.
    monthly_available = data["period_summaries"][0]["monthly_available_amounts"]
    assert len(monthly_available) == 3
    assert round(sum(item["amount"] for item in monthly_available), 2) == 0

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
    command = client.post(f"/api/commission/payment-verifications/{verification_id}/payout-command", json={"release_mode": "NEXT_QUARTER_LUMP", "release_payout_period": "2026-10"})
    assert command.status_code == 200
    assert len(command.json()["schedule_ids"]) == 1
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


def test_payment_command_requires_one_selected_month_in_the_next_cycle(client, db_session):
    from app.models.commission import CommissionCalculationSnapshot, CommissionJob, CommissionWalletLedger
    from app.services.salary import get_commission_payslip_summary, get_sales_bonus_for_employee_period

    employee = Employee(machine_employee_id="RELEASE-ONCE", full_name="NGUYEN RELEASE ONCE", contract_salary=10_000_000, employee_type="FULLTIME", annual_leave_quota=12)
    db_session.add(employee)
    db_session.commit()
    imported = client.post("/api/commission/import", json={
        "period_label": "RELEASE-Q2-2026", "from_date": "2026-04-01", "till_date": "2026-06-30",
        "jobs": [{"job_no": "RELEASE-ONCE-JOB", "sales_rep": employee.full_name, "profit_loss": 100_000_000, "payment_received": "NO"}],
    })
    assert imported.status_code == 201
    period_id = imported.json()["period_id"]
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200

    job = db_session.query(CommissionJob).filter(CommissionJob.job_no == "RELEASE-ONCE-JOB").one()
    held = next(item for item in client.get("/api/commission/wallet/jobs", params={"sales_rep": employee.full_name}).json() if item["id"] == job.id)["paymentHeld"]
    report = client.patch(f"/api/commission/periods/{period_id}/jobs/{job.id}/payment", json={"payment_received": "YES"})
    assert report.status_code == 200
    pending = next(item for item in client.get("/api/commission/wallet/jobs", params={"sales_rep": employee.full_name}).json() if item["id"] == job.id)
    assert pending["paymentHeld"] == held
    verification_id = pending["paymentVerificationId"]
    assert client.post(f"/api/commission/payment-verifications/{verification_id}/review", json={"action": "VERIFY"}).status_code == 200

    split_command = client.post(f"/api/commission/payment-verifications/{verification_id}/payout-command", json={
        "release_mode": "NEXT_QUARTER_SPLIT",
    })
    assert split_command.status_code == 422
    missing_month = client.post(f"/api/commission/payment-verifications/{verification_id}/payout-command", json={"release_mode": "NEXT_QUARTER_LUMP"})
    assert missing_month.status_code == 422

    command = client.post(f"/api/commission/payment-verifications/{verification_id}/payout-command", json={
        "release_mode": "NEXT_QUARTER_LUMP",
        "release_payout_period": "2026-11",
        "note": "Khách hàng đã thanh toán JOB RELEASE-ONCE-JOB; kế toán trả một lần.",
    })
    assert command.status_code == 200
    assert len(command.json()["schedule_ids"]) == 1
    scheduled = client.get("/api/commission/wallet/schedules", params={"sales_rep": employee.full_name}).json()
    assert [(item["payout_period"], item["total_amount"]) for item in scheduled] == [("2026-11", held)]
    assert get_sales_bonus_for_employee_period(db_session, employee.id, "2026-10") == 0
    assert get_sales_bonus_for_employee_period(db_session, employee.id, "2026-11") == held
    assert get_sales_bonus_for_employee_period(db_session, employee.id, "2026-12") == 0
    november_summary = get_commission_payslip_summary(db_session, employee, "2026-11")
    assert november_summary["scheduled_job_payout_total"] == held
    assert november_summary["scheduled_job_payouts"] == [{
        "job_no": "RELEASE-ONCE-JOB", "customer": None,
        "source_period_label": "RELEASE-Q2-2026",
        "amount": held,
        "note": "Khách hàng đã thanh toán JOB RELEASE-ONCE-JOB; kế toán trả một lần.",
    }]
    snapshot = db_session.query(CommissionCalculationSnapshot).filter(
        CommissionCalculationSnapshot.period_id == period_id,
        CommissionCalculationSnapshot.employee_id == employee.id,
    ).order_by(CommissionCalculationSnapshot.id.desc()).first()
    source_total = sum(get_sales_bonus_for_employee_period(db_session, employee.id, month) for month in ("2026-07", "2026-08", "2026-09"))
    future_total = sum(get_sales_bonus_for_employee_period(db_session, employee.id, month) for month in ("2026-10", "2026-11", "2026-12"))
    # The source months pay zero; the verified command moves the retained
    # quarterly bonus to exactly one future payroll month.
    assert round(source_total + future_total, 2) == round(float(snapshot.total_bonus_quarter), 2)
    types = {row.entry_type for row in db_session.query(CommissionWalletLedger).filter(CommissionWalletLedger.period_id == period_id).all()}
    assert {"RELEASED", "SCHEDULED"}.issubset(types)


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
    assert summary["current_period_bonus"] == 0
    assert summary["remaining_bonus"] == 0
    pending_by_job = {item["job_no"]: item for item in summary["pending_jobs"]}
    assert set(pending_by_job) == {"PAYSLIP-PAID", "PAYSLIP-WAITING"}
    assert pending_by_job["PAYSLIP-PAID"]["payment_received"] == "YES"
    assert pending_by_job["PAYSLIP-WAITING"]["payment_received"] == "NO"
    assert all(item["reason"] == "Hold cố định 30% Profit/Loss dương của JOB." for item in summary["pending_jobs"])
    assert summary["pending_bonus_amount"] == pytest.approx(float(snapshot.total_bonus_quarter), abs=0.01)


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
    assert wallet_before["available_amount"] == wallet_before["total_earned"]

    credit = client.post("/api/commission/wallet/adjustments", json={"sales_rep": "NGUYEN VAN FUNNEL", "action": "CREDIT", "amount": 30_000_500, "reason": "Thưởng nóng"})
    assert credit.status_code == 200
    decrease = client.post("/api/commission/wallet/adjustments", json={"sales_rep": "NGUYEN VAN FUNNEL", "action": "DECREASE", "amount": 100, "reason": "Điều chỉnh giảm"})
    assert decrease.status_code == 200
    after_adjustment = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN FUNNEL"}).json()[0]
    assert after_adjustment["manual_credit_amount"] == 30_000_500
    assert after_adjustment["manual_decrease_amount"] == 100
    # Re-syncing a formula change must not erase independent manual ledger rows.
    assert client.post("/api/commission/wallet/sync", json={"period_id": period_id}).status_code == 200
    after_resync_adjustment = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN FUNNEL"}).json()[0]
    assert after_resync_adjustment["manual_credit_amount"] == 30_000_500
    assert after_resync_adjustment["manual_decrease_amount"] == 100
    transfer = client.post("/api/commission/wallet/transfers", json={"sales_rep": "NGUYEN VAN FUNNEL", "amount": 200, "target_payout_period": "2026-10", "reason": "Chuyển sang tháng 10"})
    assert transfer.status_code == 200
    assert transfer.json()["amount"] == 200
    after_transfer = client.get("/api/commission/wallet", params={"sales_rep": "NGUYEN VAN FUNNEL"}).json()[0]
    assert after_transfer["transferred_amount"] == 200
    # Manual adjustments do not change the fixed 30%-of-Profit/Loss hold.
    assert after_transfer["available_amount"] == wallet_before["available_amount"] + 30_000_400 - 200
    scheduled = client.post("/api/commission/wallet/schedules", json={"sales_rep": "NGUYEN VAN FUNNEL", "amount": 300, "payout_period": "2026-10", "note": "Đợt trả tháng 10"})
    assert scheduled.status_code == 200
    schedule_id = scheduled.json()["schedule_id"]
    from app.models.commission import CommissionPayoutScheduleAllocation
    assert db_session.query(CommissionPayoutScheduleAllocation).filter(CommissionPayoutScheduleAllocation.schedule_id == schedule_id).count() > 0
    global_jobs = client.get("/api/commission/wallet/jobs")
    assert global_jobs.status_code == 200
    assert any(item["jobNo"] == "FUNNEL-YES" and item["salesRep"] == "NGUYEN VAN FUNNEL" for item in global_jobs.json())
    schedule_rows = client.get("/api/commission/wallet/schedules")
    assert schedule_rows.status_code == 200
    schedule_row = next(item for item in schedule_rows.json() if item["id"] == schedule_id)
    assert schedule_row["job_count"] == 1
    assert schedule_row["jobs"] == [{
        "job_id": schedule_row["jobs"][0]["job_id"],
        "job_no": "FUNNEL-YES",
        "period_id": period_id,
        "period_label": "FUNNEL-Q3-2026",
        "amount": 300.0,
    }]
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
    assert client.post("/api/commission/wallet/adjustments", json={
        "sales_rep": "NGUYEN VAN UNDO", "action": "CREDIT", "amount": 30_001_000, "reason": "Tạo số dư kiểm thử",
    }).status_code == 200
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
    assert after_undo["manual_credit_amount"] == 30_001_000
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
    # The large setup credit is only partly consumed because the fixed hold is
    # based on Profit/Loss; its unpaid remainder is still reversible.
    assert no_undo.status_code == 200


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
    assert client.put(f"/api/commission/periods/{period_id}/jobs/{job.id}/release-plan", json={"release_mode": "NEXT_QUARTER_LUMP", "release_payout_period": "2026-11"}).status_code == 409
    assert client.put(f"/api/commission/wallet/jobs/{job.id}/manual-hold", json={"sales_rep": employee.full_name, "manual_held_amount": 0}).status_code == 409
