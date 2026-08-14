import pytest
from app.services.salary import cake_salary

def test_salary_calculation_nguyen_ly_tuong():
    # Row 10: Nguyễn Lý Tưởng (FULLTIME)
    employee = {
        "type": "FULLTIME",
        "contract_salary": 50000000,
        "actual_working_days": 26,
        "meal_allowance_free": 1200000,
        "phone_allowance_free": 2000000,
        "taxable_meal": 0,
        "taxable_transport": 2000000,
        "performance_allowance": 2450000,
        "other_allowance": 0,
        "bonus": 0,
        "dependents_count": 3,
        "union_fee": 234000,
        "other_deductions": 0,
        "pit_refund": 0,
        "advance_payment": 0
    }
    
    result = cake_salary(employee)
    
    assert result["actual_salary"] == 50000000
    assert result["taxable_income"] == 54450000
    assert result["social_emp"] == 4000000
    assert result["health_emp"] == 750000
    assert result["unemp_emp"] == 500000
    assert result["total_ins_emp"] == 5250000
    assert result["assessable_income"] == 15100000
    assert result["pit_tax"] == 1010000
    assert result["net_salary"] == 51390000
    assert result["total_transfer"] == 51156000
    assert result["final_transfer"] == 51156000

def test_salary_calculation_dang_que_quyen():
    # Row 11: Đặng Quế Quyên (FULLTIME)
    employee = {
        "type": "FULLTIME",
        "contract_salary": 50000000,
        "actual_working_days": 26,
        "meal_allowance_free": 1200000,
        "phone_allowance_free": 1000000,
        "taxable_meal": 0,
        "taxable_transport": 1000000,
        "performance_allowance": 0,
        "other_allowance": 0,
        "bonus": 0,
        "dependents_count": 1,
        "union_fee": 234000,
        "other_deductions": 0,
        "pit_refund": 0,
        "advance_payment": 0
    }
    
    result = cake_salary(employee)
    
    assert result["actual_salary"] == 50000000
    assert result["taxable_income"] == 51000000
    assert result["social_emp"] == 4000000
    assert result["health_emp"] == 750000
    assert result["unemp_emp"] == 500000
    assert result["total_ins_emp"] == 5250000
    assert result["assessable_income"] == 24050000
    assert result["pit_tax"] == 1905000
    assert result["net_salary"] == 46045000
    assert result["total_transfer"] == 45811000
    assert result["final_transfer"] == 45811000

def test_salary_calculation_ho_dang_nhat():
    # Row 14: Hồ Đăng Nhật (PROBATION)
    employee = {
        "type": "PROBATION",
        "contract_salary": 50000000,
        "actual_working_days": 26,
        "taxable_meal": 0,
        "taxable_transport": 0,
        "performance_allowance": 0,
        "other_allowance": 0,
        "bonus": 0,
        "dependents_count": 0,
        "union_fee": 0,
        "other_deductions": 0,
        "pit_refund": 0,
        "advance_payment": 0
    }
    
    result = cake_salary(employee)
    
    assert result["actual_salary"] == 50000000
    assert result["taxable_income"] == 50000000
    assert result["social_emp"] == 0
    assert result["health_emp"] == 0
    assert result["unemp_emp"] == 0
    assert result["total_ins_emp"] == 0
    assert result["assessable_income"] == 50000000
    assert result["pit_tax"] == 5000000
    assert result["net_salary"] == 45000000
    assert result["total_transfer"] == 45000000
    assert result["final_transfer"] == 45000000

def test_salary_calculation_from_excel():
    import os
    import pandas as pd
    excel_path = r"C:\Users\hoaib\Downloads\Copy of 05 2026 Sealink salary table.xlsx"
    if not os.path.exists(excel_path):
        pytest.skip("Excel file not available in this environment")
        
    df = pd.read_excel(excel_path, sheet_name="Employee salary", header=None)
    
    def val_to_int(val):
        if pd.isna(val) or val == "":
            return 0
        try:
            return int(float(val))
        except ValueError:
            return 0

    # Row 10: Nguyễn Lý Tưởng (FULLTIME)
    row_10 = df.iloc[10]
    emp_10 = {
        "type": "FULLTIME",
        "contract_salary": val_to_int(row_10[5]),
        "actual_working_days": val_to_int(row_10[1]),
        "meal_allowance_free": val_to_int(row_10[7]),
        "taxable_meal": val_to_int(row_10[8]),
        "phone_allowance_free": val_to_int(row_10[9]),
        "taxable_transport": val_to_int(row_10[10]),
        "performance_allowance": val_to_int(row_10[11]),
        "other_allowance": val_to_int(row_10[12]),
        "bonus": val_to_int(row_10[13]),
        "dependents_count": val_to_int(row_10[3]),
        "union_fee": val_to_int(row_10[29]),
        "other_deductions": val_to_int(row_10[30]),
        "pit_refund": val_to_int(row_10[31]),
        "advance_payment": val_to_int(row_10[33])
    }
    res_10 = cake_salary(emp_10)
    assert res_10["actual_salary"] == val_to_int(row_10[6])
    assert res_10["social_emp"] == val_to_int(row_10[16])
    assert res_10["health_emp"] == val_to_int(row_10[17])
    assert res_10["unemp_emp"] == val_to_int(row_10[18])
    assert res_10["total_ins_emp"] == val_to_int(row_10[19])
    assert res_10["taxable_income"] == val_to_int(row_10[25])
    assert res_10["assessable_income"] == val_to_int(row_10[26])
    assert res_10["pit_tax"] == val_to_int(row_10[27])
    # In old excel, net_salary Col 32 (index 32) was: net_salary - union_fee?
    # Actually, in the old sheet, Col 32 is "Lương nhân viên thực nhận (NET Salary)" which subtracted union_fee.
    # So we assert total_transfer or net_salary + union_fee
    assert res_10["total_transfer"] == val_to_int(row_10[32])
    assert res_10["final_transfer"] == val_to_int(row_10[34])

    # Row 11: Đặng Quế Quyên (FULLTIME)
    row_11 = df.iloc[11]
    emp_11 = {
        "type": "FULLTIME",
        "contract_salary": val_to_int(row_11[5]),
        "actual_working_days": val_to_int(row_11[1]),
        "meal_allowance_free": val_to_int(row_11[7]),
        "taxable_meal": val_to_int(row_11[8]),
        "phone_allowance_free": val_to_int(row_11[9]),
        "taxable_transport": val_to_int(row_11[10]),
        "performance_allowance": val_to_int(row_11[11]),
        "other_allowance": val_to_int(row_11[12]),
        "bonus": val_to_int(row_11[13]),
        "dependents_count": val_to_int(row_11[3]),
        "union_fee": val_to_int(row_11[29]),
        "other_deductions": val_to_int(row_11[30]),
        "pit_refund": val_to_int(row_11[31]),
        "advance_payment": val_to_int(row_11[33])
    }
    res_11 = cake_salary(emp_11)
    assert res_11["actual_salary"] == val_to_int(row_11[6])
    assert res_11["social_emp"] == val_to_int(row_11[16])
    assert res_11["health_emp"] == val_to_int(row_11[17])
    assert res_11["unemp_emp"] == val_to_int(row_11[18])
    assert res_11["total_ins_emp"] == val_to_int(row_11[19])
    assert res_11["taxable_income"] == val_to_int(row_11[25])
    assert res_11["assessable_income"] == val_to_int(row_11[26])
    assert res_11["pit_tax"] == val_to_int(row_11[27])
    assert res_11["total_transfer"] == val_to_int(row_11[32])
    assert res_11["final_transfer"] == val_to_int(row_11[34])

    # Row 14: Hồ Đăng Nhật (PROBATION)
    row_14 = df.iloc[14]
    emp_14 = {
        "type": "PROBATION",
        "contract_salary": val_to_int(row_14[5]),
        "actual_working_days": val_to_int(row_14[1]),
        "meal_allowance_free": val_to_int(row_14[7]),
        "taxable_meal": val_to_int(row_14[8]),
        "phone_allowance_free": val_to_int(row_14[9]),
        "taxable_transport": val_to_int(row_14[10]),
        "performance_allowance": val_to_int(row_14[11]),
        "other_allowance": val_to_int(row_14[12]),
        "bonus": val_to_int(row_14[13]),
        "dependents_count": val_to_int(row_14[3]),
        "union_fee": val_to_int(row_14[29]),
        "other_deductions": val_to_int(row_14[30]),
        "pit_refund": val_to_int(row_14[31]),
        "advance_payment": val_to_int(row_14[33])
    }
    res_14 = cake_salary(emp_14)
    assert res_14["actual_salary"] == val_to_int(row_14[6])
    assert res_14["social_emp"] == val_to_int(row_14[16])
    assert res_14["health_emp"] == val_to_int(row_14[17])
    assert res_14["unemp_emp"] == val_to_int(row_14[18])
    assert res_14["total_ins_emp"] == val_to_int(row_14[19])
    assert res_14["taxable_income"] == val_to_int(row_14[25])
    assert res_14["assessable_income"] == val_to_int(row_14[26])
    assert res_14["pit_tax"] == val_to_int(row_14[27])
    assert res_14["total_transfer"] == val_to_int(row_14[32])
    assert res_14["final_transfer"] == val_to_int(row_14[34])


def test_calculate_sales_bonus():
    from app.services.salary import calculate_sales_bonus
    # Inputs: Gross_Profit = 209,416,407.13 | Target = 120,000,000
    res = calculate_sales_bonus(209416407.13, 120000000.0)
    
    # Intermediaries
    assert res["net_profit"] == 198945586.77
    assert res["target"] == 120000000.0
    assert res["pf_count_bn"] == 78945586.77
    
    # Level & Rates
    assert res["bonus_rate"] == 0.20
    
    # Final Output
    assert res["total_bonus_quarter"] == 15789117.35
    assert res["bonus_per_month"] == 5263039.12


def test_calculate_dynamic_sales_bonus():
    from app.services.salary import calculateDynamicSalesBonus
    # Case 1: Gross_Profit = 209,416,407.13, Employee_Salary = 60,000,000.0 (Target = 120,000,000)
    res = calculateDynamicSalesBonus(209416407.13, 60000000.0)
    assert res["net_profit"] == 198945586.77
    assert res["target"] == 120000000.0
    assert res["pf_count_bn"] == 78945586.77
    assert res["bonus_rate"] == 0.20
    assert res["total_bonus_quarter"] == 15789117.35
    assert res["bonus_per_month"] == 5263039.12

    # Case 2: PF_COUNT_BN <= 0
    res_zero = calculateDynamicSalesBonus(100000000.0, 60000000.0) # Net_Profit = 95M, Target = 120M -> PF_COUNT_BN = -25M <= 0
    assert res_zero["bonus_per_month"] == 0.0

    # Case 3: employee_salary <= 0 (unmatched or no salary profile)
    res_no_profile = calculateDynamicSalesBonus(209416407.13, 0.0)
    assert res_no_profile["bonus_per_month"] == 0.0


def test_non_sales_bonus_is_always_twenty_percent_of_ninety_five_percent_profit():
    from app.services.salary import calculate_employee_bonus

    result = calculate_employee_bonus(
        gross_profit=1_000_000_000.0,
        employee_salary=20_000_000.0,
        uses_progressive_bonus=False,
    )

    assert result["net_profit"] == 950_000_000.0
    assert result["target"] == 0.0
    assert result["pf_count_bn"] == 950_000_000.0
    assert result["bonus_rate"] == 0.20
    assert result["total_bonus_quarter"] == 190_000_000.0
    assert result["bonus_per_month"] == 63_333_333.33


def test_sales_bonus_wrapper_preserves_existing_progressive_formula():
    from app.services.salary import calculateDynamicSalesBonus, calculate_employee_bonus

    existing = calculateDynamicSalesBonus(500_000_000.0, 50_000_000.0)
    wrapped = calculate_employee_bonus(
        gross_profit=500_000_000.0,
        employee_salary=50_000_000.0,
        uses_progressive_bonus=True,
    )

    assert wrapped == existing


def test_get_sales_bonus_for_employee_period(db_session):
    from datetime import date as date_type
    from app.models.employee import Employee
    from app.models.commission import CommissionPeriod, CommissionJob, CommissionRepOverride
    from app.services.salary import get_sales_bonus_for_employee_period
    
    # 1. Create a dummy employee with a department mapping for bonus
    from app.models.department_bonus_config import DepartmentBonusConfig
    
    # Setup standard sales bonus matrix for department 1
    matrix = [
        {"min": 0, "max": 2, "rate": 0},
        {"min": 2, "max": 2.5, "rate": 0.20},
        {"min": 2.5, "max": 3.0, "rate": 0.25},
        {"min": 3.0, "max": 999, "rate": 0.30}
    ]
    dept_config = DepartmentBonusConfig(department_id=1, period="2026-05", rules=matrix)
    db_session.add(dept_config)
    
    employee = Employee(
        full_name="Nguyễn Văn A",
        contract_salary=50000000.0,
        employee_type="FULLTIME",
        machine_employee_id="9999",
        department_name="SALE LOCAL",
        bonus_coefficient="1.0"
    )
    db_session.add(employee)
    db_session.commit()
    
    # 2. Create a commission period for Q1/2026 (Jan 1 to Mar 31)
    period = CommissionPeriod(
        period_label="Q1-2026",
        from_date=date_type(2026, 1, 1),
        till_date=date_type(2026, 3, 31)
    )
    db_session.add(period)
    db_session.commit()
    
    # 3. Create a commission job for the employee
    job = CommissionJob(
        period_id=period.id,
        job_no="JOB001",
        sales_rep="Nguyễn Văn A",
        profit_loss=100000000.0
    )
    db_session.add(job)
    db_session.commit()
    
    # 4. Check bonus without overrides
    # Q1 payouts are in month 4, 5, 6. Let's query for payout period "2026-05" (May 2026)
    bonus = get_sales_bonus_for_employee_period(db_session, employee.id, "2026-05")
    # Gross profit = 100M
    # Net profit = 95M
    # Target = 100M (contract_salary * 2)
    # pf_count_bn = 95M - 100M = -5M <= 0 -> bonus = 0
    assert bonus == 0.0
    
    # 5. Create override for target to make it 50M, and update job profit_loss to 150M so coef = 2.85 (>2.0)
    job.profit_loss = 150000000.0
    db_session.commit()

    override = CommissionRepOverride(
        period_id=period.id,
        sales_rep="Nguyễn Văn A",
        override_target=50000000.0
    )
    db_session.add(override)
    db_session.commit()
    
    bonus_with_target_ov = get_sales_bonus_for_employee_period(db_session, employee.id, "2026-05")
    # Net profit = 142.5M
    # Overridden Target = 50M
    # pf_count_bn = 142.5M - 50M = 92.5M > 0
    # coef = 142.5M / 50M = 2.85 -> bonus_rate = 25% = 0.25
    # total_bonus = 92.5M * 0.25 = 23.125M
    # monthly_bonus = 23.125M / 3 = 7,708,333.33
    assert abs(bonus_with_target_ov - 7708333.33) < 1.0
    
    # 6. Override total bonus directly to 15M
    override.override_total_bonus = 15000000.0
    db_session.commit()
    
    bonus_with_total_ov = get_sales_bonus_for_employee_period(db_session, employee.id, "2026-05")
    # monthly_bonus = 15M / 3 = 5M
    assert bonus_with_total_ov == 5000000.0
    
    # 7. Override monthly bonus directly to 2M
    override.override_monthly_bonus = 2000000.0
    db_session.commit()
    
    bonus_with_monthly_ov = get_sales_bonus_for_employee_period(db_session, employee.id, "2026-05")
    assert bonus_with_monthly_ov == 2000000.0


def test_salary_sales_bonus_reads_wallet_adjustments_and_transfers(db_session):
    """The salary grid must use the wallet after a commission period is synced."""
    from datetime import date as date_type
    from app.models.employee import Employee
    from app.models.commission import (
        CommissionPeriod,
        CommissionPayoutSchedule,
        CommissionWalletLedger,
    )
    from app.services.salary import get_sales_bonus_for_employee_period

    employee = Employee(
        full_name="Nguyễn Ví Thưởng",
        contract_salary=20_000_000.0,
        employee_type="FULLTIME",
        machine_employee_id="wallet-001",
        bonus_coefficient="1.0",
    )
    source_period = CommissionPeriod(
        period_label="Q2-2026",
        from_date=date_type(2026, 4, 1),
        till_date=date_type(2026, 6, 30),
    )
    db_session.add_all([employee, source_period])
    db_session.flush()

    # Q2 creates three monthly bonus amounts: July, August and September. A
    # decrease/transfer assigned to July must not remove the August/September
    # base bonus; the transfer then appears as an addition in August.
    db_session.add_all([
        CommissionWalletLedger(period_id=source_period.id, sales_rep=employee.full_name, employee_id=employee.id, entry_type="ACCRUAL_AVAILABLE", amount=1_000_000),
        CommissionWalletLedger(period_id=source_period.id, sales_rep=employee.full_name, employee_id=employee.id, entry_type="MANUAL_DECREASE", amount=-100_000),
        CommissionWalletLedger(period_id=source_period.id, sales_rep=employee.full_name, employee_id=employee.id, entry_type="TRANSFER_OUT", amount=-300_000),
        CommissionWalletLedger(period_id=source_period.id, sales_rep=employee.full_name, employee_id=employee.id, entry_type="TRANSFER_IN", amount=300_000, payout_period="2026-08"),
    ])
    db_session.commit()

    assert get_sales_bonus_for_employee_period(db_session, employee.id, "2026-07") == 600_000.0
    assert get_sales_bonus_for_employee_period(db_session, employee.id, "2026-08") == 1_300_000.0
    assert get_sales_bonus_for_employee_period(db_session, employee.id, "2026-09") == 1_000_000.0

    # Scheduling authorizes payment but must not change the monthly bonus
    # amount; otherwise the same entitlement would be deducted twice.
    db_session.add(CommissionPayoutSchedule(
        sales_rep=employee.full_name,
        employee_id=employee.id,
        payout_period="2026-09",
        status="SCHEDULED",
        total_amount=200_000,
    ))
    db_session.add(CommissionWalletLedger(
        period_id=source_period.id,
        sales_rep=employee.full_name,
        employee_id=employee.id,
        entry_type="SCHEDULED",
        amount=200_000,
        payout_period="2026-09",
    ))
    db_session.commit()

    assert get_sales_bonus_for_employee_period(db_session, employee.id, "2026-07") == 600_000.0
    assert get_sales_bonus_for_employee_period(db_session, employee.id, "2026-09") == 1_000_000.0


def test_quarterly_wallet_hold_is_not_multiplied_across_three_payroll_months(db_session):
    from datetime import date as date_type
    from app.models.employee import Employee
    from app.models.commission import CommissionPeriod, CommissionWalletLedger
    from app.services.salary import get_sales_bonus_for_employee_period

    employee = Employee(
        full_name="NGUYEN QUARTER HOLD",
        contract_salary=20_000_000.0,
        employee_type="FULLTIME",
        machine_employee_id="wallet-hold-001",
    )
    source_period = CommissionPeriod(
        period_label="Q2-2026",
        from_date=date_type(2026, 4, 1),
        till_date=date_type(2026, 6, 30),
    )
    db_session.add_all([employee, source_period])
    db_session.flush()
    # One JOB is held for the source quarter. The 900 is distributed evenly
    # across July, August and September instead of being deducted three times.
    db_session.add(CommissionWalletLedger(
        period_id=source_period.id,
        sales_rep=employee.full_name,
        employee_id=employee.id,
        entry_type="ACCRUAL_HELD",
        amount=900,
    ))
    db_session.commit()

    assert get_sales_bonus_for_employee_period(db_session, employee.id, "2026-07") == 600.0
    assert get_sales_bonus_for_employee_period(db_session, employee.id, "2026-08") == 600.0
    assert get_sales_bonus_for_employee_period(db_session, employee.id, "2026-09") == 600.0


def test_wallet_monthly_split_reconciles_exactly_to_the_source_quarter(db_session):
    """Three payroll months must retain every decimal of the saved quarter."""
    from datetime import date as date_type
    from app.models.employee import Employee
    from app.models.commission import (
        CommissionCalculationSnapshot,
        CommissionPeriod,
        CommissionWalletLedger,
    )
    from app.services.salary import get_sales_bonus_for_employee_period

    employee = Employee(
        full_name="NGUYEN ROUNDING WALLET",
        contract_salary=20_000_000.0,
        employee_type="FULLTIME",
        machine_employee_id="wallet-rounding-001",
    )
    source_period = CommissionPeriod(
        period_label="Q2-2026",
        from_date=date_type(2026, 4, 1),
        till_date=date_type(2026, 6, 30),
    )
    db_session.add_all([employee, source_period])
    db_session.flush()
    db_session.add(CommissionCalculationSnapshot(
        period_id=source_period.id,
        sales_rep=employee.full_name,
        employee_id=employee.id,
        total_bonus_quarter=1_000.0,
        monthly_bonus=333.33,
    ))
    db_session.add(CommissionWalletLedger(
        period_id=source_period.id,
        sales_rep=employee.full_name,
        employee_id=employee.id,
        entry_type="ACCRUAL_AVAILABLE",
        amount=333.33,
    ))
    db_session.commit()

    july = get_sales_bonus_for_employee_period(db_session, employee.id, "2026-07")
    august = get_sales_bonus_for_employee_period(db_session, employee.id, "2026-08")
    september = get_sales_bonus_for_employee_period(db_session, employee.id, "2026-09")

    assert (july, august, september) == (333.33, 333.33, 333.34)
    assert round(july + august + september, 2) == 1_000.0
