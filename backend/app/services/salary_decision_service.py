from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.salary_decision import SalaryDecision
from app.models.employee import Employee
from app.models.monthly_salary_input import MonthlySalaryInput
from app.core.employee_type import apply_monthly_allowance_defaults


def _period_end_date(period: str) -> date:
    year, month = map(int, period.split("-"))
    return date(year, month, 22)


def period_effective_date(period: str) -> date:
    """Return the calendar-month marker used for a type change in a payroll period.

    Employee classification and its allowances are configured per displayed
    salary month (``YYYY-MM``), rather than being prorated at the 23→22
    payroll boundary.  For example, a change selected in ``2026-07`` affects
    July and all later displayed salary periods.
    """
    year, month = map(int, period.split("-"))
    return date(year, month, 1)


def _apply_type_decision_to_employee(employee: Employee, decision: SalaryDecision) -> None:
    """Apply a promotion/reclassification decision to the live employee profile."""
    if not decision.new_employee_type:
        return
    employee.employee_type = decision.new_employee_type
    employee.meal_allowance = decision.meal_allowance
    employee.trans_allowance = decision.trans_allowance
    employee.phone_allowance = decision.phone_allowance
    employee.other_allowance = decision.other_allowance


def apply_type_decision_to_salary_inputs(db: Session, decision: SalaryDecision) -> None:
    """Synchronize the changed salary month and all later salary periods."""
    if not decision.new_employee_type:
        return
    inputs = db.query(MonthlySalaryInput).filter(
        MonthlySalaryInput.employee_id == decision.employee_id
    ).all()
    effective_period = decision.effective_date.strftime("%Y-%m")
    for monthly_input in inputs:
        if monthly_input.salary_period >= effective_period:
            monthly_input.employee_type = decision.new_employee_type
            apply_monthly_allowance_defaults(monthly_input, decision.new_employee_type)
            # A full-time promotion may use an HR-configured allowance instead
            # of the system defaults.
            if decision.new_employee_type == "FULLTIME":
                monthly_input.meal_allowance_free = decision.meal_allowance
                monthly_input.phone_allowance_free = decision.phone_allowance
                monthly_input.trans_allowance_tax = decision.trans_allowance
                monthly_input.perf_allowance_tax = decision.other_allowance


def resolve_employee_type_for_period(db: Session, employee: Employee, period: str) -> dict:
    """Return the type and allowance snapshot applicable to a salary period.

    A classification change belongs to its displayed salary month. This
    preserves periods before that month while using the new classification
    from that month onward, including periods not materialized yet.
    """
    decisions = db.execute(
        select(SalaryDecision).where(
            SalaryDecision.employee_id == employee.id,
            SalaryDecision.new_employee_type.is_not(None),
        ).order_by(SalaryDecision.effective_date.asc(), SalaryDecision.id.asc())
    ).scalars().all()

    if not decisions:
        return {
            "employee_type": employee.employee_type,
            "meal_allowance": employee.meal_allowance,
            "phone_allowance": employee.phone_allowance,
            "trans_allowance": employee.trans_allowance,
            "other_allowance": employee.other_allowance,
            "from_type_decision": False,
        }

    applicable = [
        decision
        for decision in decisions
        if decision.effective_date.strftime("%Y-%m") <= period
    ]
    if applicable:
        decision = applicable[-1]
        return {
            "employee_type": decision.new_employee_type,
            "meal_allowance": decision.meal_allowance,
            "phone_allowance": decision.phone_allowance,
            "trans_allowance": decision.trans_allowance,
            "other_allowance": decision.other_allowance,
            "from_type_decision": True,
        }

    first_change = decisions[0]
    return {
        "employee_type": first_change.old_employee_type or employee.employee_type,
        "meal_allowance": first_change.old_meal_allowance if first_change.old_meal_allowance is not None else employee.meal_allowance,
        "phone_allowance": first_change.old_phone_allowance if first_change.old_phone_allowance is not None else employee.phone_allowance,
        "trans_allowance": first_change.old_trans_allowance if first_change.old_trans_allowance is not None else employee.trans_allowance,
        "other_allowance": first_change.old_other_allowance if first_change.old_other_allowance is not None else employee.other_allowance,
        "from_type_decision": True,
    }

def apply_pending_salary_decisions(db: Session):
    """
    Finds all PENDING salary decisions whose effective_date is <= today.
    Applies the new salary to the employee's profile and marks the decision as ACTIVE.
    """
    today = date.today()
    stmt = select(SalaryDecision).where(
        SalaryDecision.status == "PENDING",
        SalaryDecision.effective_date <= today
    )
    pending_decisions = db.execute(stmt).scalars().all()
    
    for decision in pending_decisions:
        emp = db.get(Employee, decision.employee_id)
        if emp:
            if decision.new_employee_type:
                _apply_type_decision_to_employee(emp, decision)
                apply_type_decision_to_salary_inputs(db, decision)
            else:
                emp.contract_salary = decision.new_salary
                emp.meal_allowance = decision.meal_allowance
                emp.trans_allowance = decision.trans_allowance
                emp.phone_allowance = decision.phone_allowance
                emp.other_allowance = decision.other_allowance
                emp.bonus_coefficient = decision.bonus_coefficient
            decision.status = "ACTIVE"
    
    if pending_decisions:
        db.commit()

import calendar

def get_blended_salary_for_period(db: Session, employee_id: int, period: str, current_salary: int) -> dict:
    """
    Check if there's an ACTIVE salary decision in this period.
    Returns dict: 
        is_mid_month_change (bool), 
        blended_salary (int), 
        prorated_old_salary (int), 
        prorated_new_salary (int),
        prorated_days_old (int),
        prorated_days_new (int)
    """
    year, month = map(int, period.split('-'))
    
    prev_year = year
    prev_month = month - 1
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
        
    start_date = date(prev_year, prev_month, 23)
    end_date = date(year, month, 22)

    stmt = select(SalaryDecision).where(
        SalaryDecision.employee_id == employee_id,
        SalaryDecision.status == "ACTIVE",
        SalaryDecision.new_employee_type.is_(None),
        SalaryDecision.effective_date >= start_date,
        SalaryDecision.effective_date <= end_date
    ).order_by(SalaryDecision.effective_date.desc())
    decision = db.execute(stmt).scalars().first()

    if not decision:
        # Determine the flat historical salary for this period
        # 1. Find the latest decision that took effect ON or BEFORE end_date
        stmt_before = select(SalaryDecision).where(
            SalaryDecision.employee_id == employee_id,
            SalaryDecision.status == "ACTIVE",
            SalaryDecision.new_employee_type.is_(None),
            SalaryDecision.effective_date <= end_date
        ).order_by(SalaryDecision.effective_date.desc())
        decision_before = db.execute(stmt_before).scalars().first()
        
        if decision_before:
            historical_salary = decision_before.new_salary
        else:
            # 2. If no decision before, find the earliest decision AFTER end_date
            stmt_after = select(SalaryDecision).where(
                SalaryDecision.employee_id == employee_id,
                SalaryDecision.status == "ACTIVE",
                SalaryDecision.new_employee_type.is_(None),
                SalaryDecision.effective_date > end_date
            ).order_by(SalaryDecision.effective_date.asc())
            decision_after = db.execute(stmt_after).scalars().first()
            
            if decision_after:
                historical_salary = decision_after.old_salary
            else:
                # 3. Fallback to current salary
                historical_salary = current_salary

        return {
            "is_mid_month_change": False,
            "blended_salary": historical_salary,
            "prorated_old_salary": None,
            "prorated_new_salary": None,
            "prorated_days_old": None,
            "prorated_days_new": None,
            "effective_date_str": None
        }

    days_old = (decision.effective_date - start_date).days
    days_new = (end_date - decision.effective_date).days + 1
    total_days = (end_date - start_date).days + 1

    blended = (decision.old_salary * days_old + decision.new_salary * days_new) / total_days

    return {
        "is_mid_month_change": True,
        "blended_salary": int(round(blended)),
        "prorated_old_salary": decision.old_salary,
        "prorated_new_salary": decision.new_salary,
        "prorated_days_old": days_old,
        "prorated_days_new": days_new,
        "effective_date_str": decision.effective_date.isoformat()
    }
