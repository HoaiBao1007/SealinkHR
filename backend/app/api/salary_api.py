from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import List, Optional, Union
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_admin_user
from app.models.employee import Employee
from app.models.monthly_salary_input import MonthlySalaryInput
from app.models.salary_policy import SalaryPolicy
from app.models.salary_decision import SalaryDecision
from app.models.user import User
from app.schemas.salary_schemas import (
    EmployeeSalaryUpdate,
    EmployeeSalaryResponse,
    MonthlySalaryInputCreate,
    MonthlySalaryInputUpdate,
    MonthlySalaryInputResponse,
)
from app.services.salary_decision_service import (
    apply_pending_salary_decisions,
    apply_type_decision_to_salary_inputs,
    get_blended_salary_for_period,
    period_effective_date,
    resolve_employee_type_for_period,
)
from app.core.employee_type import (
    allowance_defaults_for_type,
    apply_contract_allowance_defaults,
    apply_monthly_allowance_defaults,
    normalize_employee_type,
)
from app.services.notification_service import PAYROLL, actor_id, add_employee_notifications
from app.services.salary_policy import (
    DEFAULT_PIT_BRACKETS,
    ensure_default_salary_policy,
    policy_to_dict,
    resolve_salary_policy,
)

router = APIRouter(prefix="/api/salary", tags=["salary"], dependencies=[Depends(get_admin_user)])

OTHER_INCOME_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "salary_other_income"
OTHER_INCOME_MAX_FILE_SIZE = 15 * 1024 * 1024
OTHER_INCOME_ALLOWED_EXTENSIONS = {
    ".pdf",
    ".xlsx",
    ".xls",
    ".csv",
    ".doc",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
}


class SalaryTaxBracketPayload(BaseModel):
    up_to: Optional[int] = Field(default=None, ge=0)
    rate: float = Field(ge=0, le=1)
    deduction: int = Field(default=0, ge=0)


class SalaryPolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    effective_from: date
    legal_basis: Optional[str] = Field(default=None, max_length=500)
    note: Optional[str] = Field(default=None, max_length=2000)
    common_minimum_wage: int = Field(ge=0)
    regional_minimum_wage_i: int = Field(ge=0)
    regional_minimum_wage_ii: int = Field(ge=0)
    regional_minimum_wage_iii: int = Field(ge=0)
    regional_minimum_wage_iv: int = Field(ge=0)
    default_region: str = Field(default="I", pattern=r"^(I|II|III|IV)$")
    social_health_salary_cap: int = Field(ge=0)
    unemployment_cap_multiplier: int = Field(ge=0)
    social_employee_rate: float = Field(ge=0, le=1)
    health_employee_rate: float = Field(ge=0, le=1)
    unemployment_employee_rate: float = Field(ge=0, le=1)
    social_employer_rate: float = Field(ge=0, le=1)
    health_employer_rate: float = Field(ge=0, le=1)
    unemployment_employer_rate: float = Field(ge=0, le=1)
    union_fund_employer_rate: float = Field(ge=0, le=1)
    union_employee_rate: float = Field(ge=0, le=1)
    union_employee_cap: int = Field(ge=0)
    personal_deduction: int = Field(ge=0)
    dependent_deduction: int = Field(ge=0)
    probation_withholding_rate: float = Field(ge=0, le=1)
    probation_withholding_threshold: int = Field(ge=0)
    pit_brackets: List[SalaryTaxBracketPayload] = Field(default_factory=lambda: [SalaryTaxBracketPayload(**item) for item in DEFAULT_PIT_BRACKETS])


def _other_income_response_fields(item: MonthlySalaryInput) -> dict:
    return {
        "other_income_note": item.other_income_note,
        "other_income_document_name": item.other_income_document_name,
        "other_income_document_content_type": item.other_income_document_content_type,
        "other_income_document_size": item.other_income_document_size,
        "other_income_document_uploaded_at": item.other_income_document_uploaded_at,
    }


@router.get("/policies")
def list_salary_policies(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Return policy history.  Policies are immutable once created."""
    ensure_default_salary_policy(db)
    db.commit()
    policies = db.query(SalaryPolicy).order_by(
        SalaryPolicy.effective_from.desc(), SalaryPolicy.id.desc()
    ).limit(limit).all()
    return [policy_to_dict(policy) for policy in policies]


@router.get("/policy")
def get_effective_salary_policy(
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    """Resolve the policy for a payroll month, preferring that month's snapshot."""
    ensure_default_salary_policy(db)
    saved_policy_id = db.query(MonthlySalaryInput.salary_policy_id).filter(
        MonthlySalaryInput.salary_period == period,
        MonthlySalaryInput.salary_policy_id.is_not(None),
    ).order_by(MonthlySalaryInput.id.asc()).scalar()
    policy = db.get(SalaryPolicy, saved_policy_id) if saved_policy_id else None
    legacy_published = db.query(MonthlySalaryInput.id).filter(
        MonthlySalaryInput.salary_period == period,
        MonthlySalaryInput.is_published.is_(True),
        MonthlySalaryInput.salary_policy_id.is_(None),
    ).first()
    if policy is None:
        # Months published before this feature existed have no policy ID.
        # Their historical calculation must stay on the baseline version.
        policy = ensure_default_salary_policy(db) if legacy_published else resolve_salary_policy(db, period)
    db.commit()
    return {"policy": policy_to_dict(policy), "snapshot": bool(saved_policy_id)}


@router.post("/policies", status_code=status.HTTP_201_CREATED)
def create_salary_policy(
    payload: SalaryPolicyCreate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Create a new dated version without changing prior payroll snapshots."""
    ensure_default_salary_policy(db)
    duplicate = db.query(SalaryPolicy).filter(
        SalaryPolicy.effective_from == payload.effective_from,
        SalaryPolicy.name == payload.name.strip(),
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Đã có phiên bản chính sách cùng tên và ngày hiệu lực")

    month_key = payload.effective_from.strftime("%Y%m")
    count = db.query(SalaryPolicy).filter(SalaryPolicy.version_code.like(f"CS-{month_key}-%")).count()
    policy = SalaryPolicy(
        version_code=f"CS-{month_key}-{count + 1:03d}",
        name=payload.name.strip(),
        effective_from=payload.effective_from,
        legal_basis=(payload.legal_basis or "").strip() or None,
        note=(payload.note or "").strip() or None,
        common_minimum_wage=payload.common_minimum_wage,
        regional_minimum_wage_i=payload.regional_minimum_wage_i,
        regional_minimum_wage_ii=payload.regional_minimum_wage_ii,
        regional_minimum_wage_iii=payload.regional_minimum_wage_iii,
        regional_minimum_wage_iv=payload.regional_minimum_wage_iv,
        default_region=payload.default_region,
        social_health_salary_cap=payload.social_health_salary_cap,
        unemployment_cap_multiplier=payload.unemployment_cap_multiplier,
        social_employee_rate=payload.social_employee_rate,
        health_employee_rate=payload.health_employee_rate,
        unemployment_employee_rate=payload.unemployment_employee_rate,
        social_employer_rate=payload.social_employer_rate,
        health_employer_rate=payload.health_employer_rate,
        unemployment_employer_rate=payload.unemployment_employer_rate,
        union_fund_employer_rate=payload.union_fund_employer_rate,
        union_employee_rate=payload.union_employee_rate,
        union_employee_cap=payload.union_employee_cap,
        personal_deduction=payload.personal_deduction,
        dependent_deduction=payload.dependent_deduction,
        probation_withholding_rate=payload.probation_withholding_rate,
        probation_withholding_threshold=payload.probation_withholding_threshold,
        pit_brackets_json=json.dumps([item.model_dump() for item in payload.pit_brackets]),
        created_by=current_user.id,
    )
    db.add(policy)
    db.flush()

    # Bản lương đã phát hành là lịch sử không được thay đổi.  Các tháng chưa
    # phát hành từ ngày hiệu lực trở đi sẽ dùng phiên bản mới này, kể cả khi
    # các dòng input của tháng đã được tạo trước đó.
    affected_period = payload.effective_from.strftime("%Y-%m")
    db.query(MonthlySalaryInput).filter(
        MonthlySalaryInput.salary_period >= affected_period,
        MonthlySalaryInput.is_published.is_(False),
    ).update({MonthlySalaryInput.salary_policy_id: policy.id}, synchronize_session=False)
    db.commit()
    db.refresh(policy)
    return policy_to_dict(policy)


def _get_or_create_monthly_input(
    db: Session,
    employee: Employee,
    period: str,
) -> MonthlySalaryInput:
    item = db.query(MonthlySalaryInput).filter(
        MonthlySalaryInput.employee_id == employee.id,
        MonthlySalaryInput.salary_period == period,
    ).first()
    if item:
        return item

    period_compensation = resolve_employee_type_for_period(db, employee, period)
    blended_data = get_blended_salary_for_period(db, employee.id, period, employee.contract_salary)
    item = MonthlySalaryInput(
        employee_id=employee.id,
        salary_period=period,
        salary_policy_id=resolve_salary_policy(db, period).id,
        actual_working_days=22.0,
        meal_allowance_free=period_compensation["meal_allowance"],
        meal_allowance_tax=0,
        phone_allowance_free=period_compensation["phone_allowance"],
        trans_allowance_tax=period_compensation["trans_allowance"],
        perf_allowance_tax=period_compensation["other_allowance"],
        other_income=0,
        bonus=0,
        advance_payment=0,
        pit_refund=0,
        other_deductions=0,
        bonus_14=0,
        contract_salary=blended_data["blended_salary"],
        is_mid_month_change=blended_data["is_mid_month_change"],
        prorated_old_salary=blended_data["prorated_old_salary"],
        prorated_new_salary=blended_data["prorated_new_salary"],
        prorated_days_old=blended_data["prorated_days_old"],
        prorated_days_new=blended_data["prorated_days_new"],
        mid_month_effective_date=blended_data.get("effective_date_str"),
    )
    db.add(item)
    db.flush()
    return item


def _resolve_private_other_income_file(item: MonthlySalaryInput) -> Path:
    if not item.other_income_document_path:
        raise HTTPException(status_code=404, detail="Chưa có chứng từ Thu nhập khác")
    upload_root = OTHER_INCOME_UPLOAD_DIR.resolve()
    file_path = Path(item.other_income_document_path).resolve()
    try:
        file_path.relative_to(upload_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Đường dẫn chứng từ không hợp lệ") from exc
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy chứng từ Thu nhập khác")
    return file_path


@router.get("/employees", response_model=List[EmployeeSalaryResponse])
def list_employees_salary(
    q: Optional[str] = Query(default=None),
    period: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    apply_pending_salary_decisions(db)

    if period:
        query = db.query(Employee, MonthlySalaryInput).outerjoin(
            MonthlySalaryInput,
            (MonthlySalaryInput.employee_id == Employee.id) & (MonthlySalaryInput.salary_period == period)
        )
    else:
        query = db.query(Employee)

    if q:
        keyword = f"%{q.strip()}%"
        query = query.filter(
            (Employee.full_name.ilike(keyword))
            | (Employee.employee_code.ilike(keyword))
            | (Employee.machine_employee_id.ilike(keyword))
        )
    results = query.order_by(Employee.id.asc()).all()
    
    # Map model objects to the schema
    response_data = []
    for row in results:
        if period:
            emp, m_input = row
        else:
            emp, m_input = row, None
            
        if period:
            # If there's an existing salary input record, always show them to protect historical inputs.
            if m_input is None:
                # Filter by start date: hide if start date is in a future period
                if emp.start_date:
                    start_period = emp.start_date.strftime("%Y-%m")
                    if start_period > period:
                        continue
                
                # Filter by resignation period: hide if resignation period is in the past/present
                if emp.status == 'RESIGNED':
                    if emp.resignation_period:
                        if emp.resignation_period <= period:
                            continue
                    else:
                        # Resigned with no period set (fallback to hiding)
                        continue

        # Apply overrides from MonthlySalaryInput if present
        fullname = emp.full_name
        position = emp.position
        employee_type = emp.employee_type
        period_compensation = None
        dependents_count = emp.dependents_count
        account_number = emp.account_number
        bank_name = emp.bank_name

        is_mid_month_change = False
        prorated_old_salary = None
        prorated_new_salary = None
        prorated_days_old = None
        prorated_days_new = None
        mid_month_effective_date = None

        if period:
            period_compensation = resolve_employee_type_for_period(db, emp, period)
            employee_type = period_compensation["employee_type"]
            blended_data = get_blended_salary_for_period(db, emp.id, period, emp.contract_salary)
            if blended_data["is_mid_month_change"]:
                is_mid_month_change = True
                prorated_old_salary = blended_data["prorated_old_salary"]
                prorated_new_salary = blended_data["prorated_new_salary"]
                prorated_days_old = blended_data["prorated_days_old"]
                prorated_days_new = blended_data["prorated_days_new"]
                mid_month_effective_date = blended_data["effective_date_str"]
                contract_salary = blended_data["blended_salary"]
            else:
                contract_salary = blended_data["blended_salary"]

            # If m_input exists, we auto-sync these fields to the DB if they changed
            if m_input:
                changed = False
                if m_input.is_mid_month_change != is_mid_month_change:
                    m_input.is_mid_month_change = is_mid_month_change
                    changed = True
                if m_input.prorated_old_salary != prorated_old_salary:
                    m_input.prorated_old_salary = prorated_old_salary
                    changed = True
                if m_input.prorated_new_salary != prorated_new_salary:
                    m_input.prorated_new_salary = prorated_new_salary
                    changed = True
                if m_input.prorated_days_old != prorated_days_old:
                    m_input.prorated_days_old = prorated_days_old
                    changed = True
                if m_input.prorated_days_new != prorated_days_new:
                    m_input.prorated_days_new = prorated_days_new
                    changed = True
                if m_input.mid_month_effective_date != mid_month_effective_date:
                    m_input.mid_month_effective_date = mid_month_effective_date
                    changed = True
                # The blended_salary from get_blended_salary_for_period now correctly determines the historical snapshot.
                target_salary = blended_data["blended_salary"]
                if m_input.contract_salary != target_salary:
                    m_input.contract_salary = target_salary
                    changed = True
                
                if changed:
                    db.commit()
                    db.refresh(m_input)

                # Now read values from synced m_input
                if m_input.contract_salary is not None:
                    contract_salary = m_input.contract_salary
        else:
            contract_salary = emp.contract_salary

        if m_input:
            if m_input.fullname is not None:
                fullname = m_input.fullname
            if m_input.position is not None:
                position = m_input.position
            # Type changes are timeline-based.  A legacy value saved directly
            # in one monthly row must never override a recorded type decision
            # for this period (or any later period).
            if m_input.employee_type is not None and not (
                period_compensation and period_compensation["from_type_decision"]
            ):
                employee_type = m_input.employee_type
            if m_input.dependents_count is not None:
                dependents_count = m_input.dependents_count
            if m_input.account_number is not None:
                account_number = m_input.account_number
            if m_input.bank_name is not None:
                bank_name = m_input.bank_name

        response_data.append(
            EmployeeSalaryResponse(
                id=emp.id,
                machine_employee_id=emp.machine_employee_id,
                employee_code=emp.employee_code,
                fullname=fullname,
                position=position,
                contract_salary=contract_salary,
                employee_type=employee_type,
                dependents_count=dependents_count,
                account_number=account_number,
                bank_name=bank_name,
                is_mid_month_change=is_mid_month_change,
                prorated_old_salary=prorated_old_salary,
                prorated_new_salary=prorated_new_salary,
                prorated_days_old=prorated_days_old,
                prorated_days_new=prorated_days_new,
                mid_month_effective_date=mid_month_effective_date,
            )
        )
    return response_data


@router.put("/employees/{employee_id}", response_model=EmployeeSalaryResponse)
def update_employee_salary(
    employee_id: int,
    payload: EmployeeSalaryUpdate,
    period: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    if period:
        # Period-specific update: save overrides to MonthlySalaryInput
        m_input = db.query(MonthlySalaryInput).filter(
            MonthlySalaryInput.employee_id == employee_id,
            MonthlySalaryInput.salary_period == period
        ).first()
        
        if not m_input:
            blended_data = get_blended_salary_for_period(db, employee_id, period, employee.contract_salary)
            m_input = MonthlySalaryInput(
                employee_id=employee_id,
                salary_period=period,
                salary_policy_id=resolve_salary_policy(db, period).id,
                actual_working_days=22.0,
                meal_allowance_free=resolve_employee_type_for_period(db, employee, period)["meal_allowance"],
                meal_allowance_tax=0,
                phone_allowance_free=resolve_employee_type_for_period(db, employee, period)["phone_allowance"],
                trans_allowance_tax=resolve_employee_type_for_period(db, employee, period)["trans_allowance"],
                perf_allowance_tax=resolve_employee_type_for_period(db, employee, period)["other_allowance"],
                other_income=0,
                bonus=0,
                bonus_14=0,
                advance_payment=0,
                pit_refund=0,
                other_deductions=0,
                contract_salary=blended_data["blended_salary"],
                is_mid_month_change=blended_data["is_mid_month_change"],
                prorated_old_salary=blended_data["prorated_old_salary"],
                prorated_new_salary=blended_data["prorated_new_salary"],
                prorated_days_old=blended_data["prorated_days_old"],
                prorated_days_new=blended_data["prorated_days_new"],
                mid_month_effective_date=blended_data.get("effective_date_str")
            )
            db.add(m_input)
            
        if payload.fullname is not None:
            m_input.fullname = payload.fullname.strip() or None
        if payload.position is not None:
            m_input.position = payload.position.strip() or None
        if payload.contract_salary is not None:
            m_input.contract_salary = payload.contract_salary
        if payload.employee_type is not None:
            try:
                employee_type = normalize_employee_type(payload.employee_type)
            except ValueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            period_compensation = resolve_employee_type_for_period(db, employee, period)
            current_period_type = m_input.employee_type or period_compensation["employee_type"]
            type_changed = current_period_type != employee_type
            if type_changed:
                new_allowances = allowance_defaults_for_type(employee_type)
                effective_date = period_effective_date(period)
                type_decision = SalaryDecision(
                    employee_id=employee.id,
                    old_salary=employee.contract_salary,
                    new_salary=employee.contract_salary,
                    meal_allowance=new_allowances["meal_allowance"],
                    trans_allowance=new_allowances["trans_allowance"],
                    phone_allowance=new_allowances["phone_allowance"],
                    other_allowance=new_allowances["other_allowance"],
                    bonus_coefficient=employee.bonus_coefficient,
                    old_employee_type=current_period_type,
                    new_employee_type=employee_type,
                    old_meal_allowance=m_input.meal_allowance_free,
                    old_trans_allowance=m_input.trans_allowance_tax,
                    old_phone_allowance=m_input.phone_allowance_free,
                    old_other_allowance=m_input.perf_allowance_tax,
                    effective_date=effective_date,
                    reason=f"Chuyển loại nhân viên từ kỳ {period}: {period_compensation['employee_type']} → {employee_type}",
                    status="ACTIVE" if effective_date <= date.today() else "PENDING",
                )
                db.add(type_decision)
                db.flush()
                apply_type_decision_to_salary_inputs(db, type_decision)

                # Keep the live profile in sync only when this is the latest
                # scheduled type change.  A later decision remains the source
                # of truth for the employee's current profile.
                has_later_change = db.query(SalaryDecision.id).filter(
                    SalaryDecision.employee_id == employee.id,
                    SalaryDecision.new_employee_type.is_not(None),
                    SalaryDecision.effective_date > effective_date,
                ).first()
                if not has_later_change and effective_date <= date.today():
                    employee.employee_type = employee_type
                    employee.meal_allowance = new_allowances["meal_allowance"]
                    employee.phone_allowance = new_allowances["phone_allowance"]
                    employee.trans_allowance = new_allowances["trans_allowance"]
                    employee.other_allowance = new_allowances["other_allowance"]
            m_input.employee_type = employee_type
            if type_changed:
                apply_monthly_allowance_defaults(m_input, employee_type)
        if payload.dependents_count is not None:
            m_input.dependents_count = payload.dependents_count
        if payload.account_number is not None:
            m_input.account_number = payload.account_number.strip() or None
        if payload.bank_name is not None:
            m_input.bank_name = payload.bank_name.strip() or None

        # employee_code is global only, update Employee if provided
        if payload.employee_code is not None:
            code = payload.employee_code.strip()
            if code:
                existing = db.query(Employee).filter(Employee.employee_code == code, Employee.id != employee_id).first()
                if existing:
                    raise HTTPException(status_code=409, detail="Employee code already exists")
                employee.employee_code = code
            else:
                employee.employee_code = None

        db.commit()
        db.refresh(m_input)
        db.refresh(employee)

        return EmployeeSalaryResponse(
            id=employee.id,
            machine_employee_id=employee.machine_employee_id,
            employee_code=employee.employee_code,
            fullname=m_input.fullname or employee.full_name,
            position=m_input.position or employee.position,
            contract_salary=m_input.contract_salary if m_input.contract_salary is not None else employee.contract_salary,
            employee_type=m_input.employee_type or employee.employee_type,
            dependents_count=m_input.dependents_count if m_input.dependents_count is not None else employee.dependents_count,
            account_number=m_input.account_number or employee.account_number,
            bank_name=m_input.bank_name or employee.bank_name,
            is_mid_month_change=m_input.is_mid_month_change,
            prorated_old_salary=m_input.prorated_old_salary,
            prorated_new_salary=m_input.prorated_new_salary,
            prorated_days_old=m_input.prorated_days_old,
            prorated_days_new=m_input.prorated_days_new,
            mid_month_effective_date=m_input.mid_month_effective_date,
        )
    else:
        # Global update: update Employee directly
        if payload.employee_code is not None:
            code = payload.employee_code.strip()
            if code:
                existing = db.query(Employee).filter(Employee.employee_code == code, Employee.id != employee_id).first()
                if existing:
                    raise HTTPException(status_code=409, detail="Employee code already exists")
                employee.employee_code = code
            else:
                employee.employee_code = None

        if payload.fullname is not None:
            name = payload.fullname.strip()
            if not name:
                raise HTTPException(status_code=400, detail="Fullname cannot be empty")
            employee.full_name = name  # updates synonym and full_name

        if payload.position is not None:
            employee.position = payload.position.strip() or None

        if payload.contract_salary is not None:
            employee.contract_salary = payload.contract_salary

        if payload.employee_type is not None:
            try:
                employee_type = normalize_employee_type(payload.employee_type)
            except ValueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            type_changed = employee.employee_type != employee_type
            employee.employee_type = employee_type
            if type_changed:
                apply_contract_allowance_defaults(employee, employee_type)

        if payload.dependents_count is not None:
            employee.dependents_count = payload.dependents_count

        if payload.account_number is not None:
            employee.account_number = payload.account_number.strip() or None

        if payload.bank_name is not None:
            employee.bank_name = payload.bank_name.strip() or None

        db.commit()
        db.refresh(employee)

        return EmployeeSalaryResponse(
            id=employee.id,
            machine_employee_id=employee.machine_employee_id,
            employee_code=employee.employee_code,
            fullname=employee.full_name,
            position=employee.position,
            contract_salary=employee.contract_salary,
            employee_type=employee.employee_type,
            dependents_count=employee.dependents_count,
            account_number=employee.account_number,
            bank_name=employee.bank_name,
        )


@router.get("/inputs", response_model=List[MonthlySalaryInputResponse])
def list_monthly_salary_inputs(
    period: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    apply_pending_salary_decisions(db)
    query = db.query(MonthlySalaryInput)
    if period:
        query = query.filter(MonthlySalaryInput.salary_period == period)
    
    inputs = query.order_by(MonthlySalaryInput.id.asc()).all()
    
    from app.services.salary import get_sales_bonus_for_employee_period
    
    if period:
        employees = db.query(Employee).order_by(Employee.id.asc()).all()
        existing_inputs_map = {item.employee_id: item for item in inputs}
        
        response_data = []
        import datetime
        now = datetime.datetime.now()
        
        for emp in employees:
            period_compensation = resolve_employee_type_for_period(db, emp, period)
            has_input = emp.id in existing_inputs_map
            if not has_input:
                if emp.start_date:
                    start_period = emp.start_date.strftime("%Y-%m")
                    if start_period > period:
                        continue
                if emp.status == 'RESIGNED':
                    if emp.resignation_period:
                        if emp.resignation_period <= period:
                            continue
                    else:
                        continue
            
            sales_bonus = round(get_sales_bonus_for_employee_period(db, emp.id, period), 2)
            
            if has_input:
                item = existing_inputs_map[emp.id]
                # A type saved explicitly for this monthly row is the current
                # period's approved classification and allowance snapshot.
                # Otherwise resolve the timeline so unmaterialised and legacy
                # rows follow the employee's classification decisions.
                use_type_snapshot = (
                    period_compensation["from_type_decision"]
                    and item.employee_type is None
                )
                response_data.append(
                    MonthlySalaryInputResponse(
                        id=item.id,
                        employee_id=item.employee_id,
                        employee_name=item.employee.full_name if item.employee else emp.full_name,
                        employee_code=item.employee.employee_code if item.employee else emp.employee_code,
                        salary_period=item.salary_period,
                        actual_working_days=item.actual_working_days,
                        meal_allowance_free=period_compensation["meal_allowance"] if use_type_snapshot else item.meal_allowance_free,
                        meal_allowance_tax=item.meal_allowance_tax,
                        phone_allowance_free=period_compensation["phone_allowance"] if use_type_snapshot else item.phone_allowance_free,
                        trans_allowance_tax=period_compensation["trans_allowance"] if use_type_snapshot else item.trans_allowance_tax,
                        perf_allowance_tax=period_compensation["other_allowance"] if use_type_snapshot else item.perf_allowance_tax,
                        other_income=item.other_income,
                        **_other_income_response_fields(item),
                        bonus=item.bonus,
                        advance_payment=item.advance_payment,
                        pit_refund=item.pit_refund,
                        other_deductions=item.other_deductions,
                        bonus_14=item.bonus_14,
                        sales_bonus=sales_bonus,
                        created_at=item.created_at,
                        updated_at=item.updated_at,
                    )
                )
            else:
                response_data.append(
                    MonthlySalaryInputResponse(
                        id=-emp.id,
                        employee_id=emp.id,
                        employee_name=emp.full_name,
                        employee_code=emp.employee_code,
                        salary_period=period,
                        actual_working_days=22.0,
                        meal_allowance_free=period_compensation["meal_allowance"],
                        meal_allowance_tax=0,
                        phone_allowance_free=period_compensation["phone_allowance"],
                        trans_allowance_tax=period_compensation["trans_allowance"],
                        perf_allowance_tax=period_compensation["other_allowance"],
                        other_income=0,
                        other_income_note=None,
                        other_income_document_name=None,
                        other_income_document_content_type=None,
                        other_income_document_size=None,
                        other_income_document_uploaded_at=None,
                        bonus=0,
                        advance_payment=0,
                        pit_refund=0,
                        other_deductions=0,
                        bonus_14=0,
                        sales_bonus=sales_bonus,
                        created_at=now,
                        updated_at=now,
                    )
                )
        return response_data

    response_data = []
    for item in inputs:
        sales_bonus = round(get_sales_bonus_for_employee_period(db, item.employee_id, item.salary_period), 2)
        response_data.append(
            MonthlySalaryInputResponse(
                id=item.id,
                employee_id=item.employee_id,
                employee_name=item.employee.full_name if item.employee else None,
                employee_code=item.employee.employee_code if item.employee else None,
                salary_period=item.salary_period,
                actual_working_days=item.actual_working_days,
                meal_allowance_free=item.meal_allowance_free,
                meal_allowance_tax=item.meal_allowance_tax,
                phone_allowance_free=item.phone_allowance_free,
                trans_allowance_tax=item.trans_allowance_tax,
                perf_allowance_tax=item.perf_allowance_tax,
                other_income=item.other_income,
                **_other_income_response_fields(item),
                bonus=item.bonus,
                advance_payment=item.advance_payment,
                pit_refund=item.pit_refund,
                other_deductions=item.other_deductions,
                bonus_14=item.bonus_14,
                sales_bonus=sales_bonus,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )
    return response_data


@router.post("/inputs", response_model=List[MonthlySalaryInputResponse])
def upsert_monthly_salary_inputs(
    payload: Union[List[MonthlySalaryInputCreate], MonthlySalaryInputCreate],
    db: Session = Depends(get_db),
):
    items_to_process = payload if isinstance(payload, list) else [payload]
    results = []

    for item in items_to_process:
        # Check if employee exists
        employee = db.query(Employee).filter(Employee.id == item.employee_id).first()
        if not employee:
            raise HTTPException(
                status_code=404, 
                detail=f"Employee with id {item.employee_id} not found"
            )

        # Upsert: check if record exists for this employee and period
        existing = db.query(MonthlySalaryInput).filter(
            MonthlySalaryInput.employee_id == item.employee_id,
            MonthlySalaryInput.salary_period == item.salary_period
        ).first()

        if existing:
            # Update fields only if they were explicitly provided in the payload
            update_data = item.model_dump(exclude_unset=True, exclude={"employee_id", "salary_period"})
            for key, value in update_data.items():
                setattr(existing, key, value)
            # Snapshot the policy the first time an unissued legacy month is edited.
            # This prevents a later policy change from silently changing this month's payroll.
            if existing.salary_policy_id is None:
                existing.salary_policy_id = resolve_salary_policy(db, item.salary_period).id
            db_item = existing
        else:
            blended_data = get_blended_salary_for_period(db, employee.id, item.salary_period, employee.contract_salary)
            # Create new
            db_item = MonthlySalaryInput(
                employee_id=item.employee_id,
                salary_period=item.salary_period,
                salary_policy_id=resolve_salary_policy(db, item.salary_period).id,
                actual_working_days=item.actual_working_days,
                meal_allowance_free=item.meal_allowance_free,
                meal_allowance_tax=item.meal_allowance_tax,
                phone_allowance_free=item.phone_allowance_free,
                trans_allowance_tax=item.trans_allowance_tax,
                perf_allowance_tax=item.perf_allowance_tax,
                other_income=item.other_income,
                bonus=item.bonus,
                advance_payment=item.advance_payment,
                pit_refund=item.pit_refund,
                other_deductions=item.other_deductions,
                bonus_14=item.bonus_14,
                contract_salary=blended_data["blended_salary"],
                is_mid_month_change=blended_data["is_mid_month_change"],
                prorated_old_salary=blended_data["prorated_old_salary"],
                prorated_new_salary=blended_data["prorated_new_salary"],
                prorated_days_old=blended_data["prorated_days_old"],
                prorated_days_new=blended_data["prorated_days_new"],
                mid_month_effective_date=blended_data.get("effective_date_str")
            )
            db.add(db_item)
            
        db.commit()
        db.refresh(db_item)
        results.append(db_item)

    from app.services.salary import get_sales_bonus_for_employee_period
    response_data = []
    for item in results:
        sales_bonus = round(get_sales_bonus_for_employee_period(db, item.employee_id, item.salary_period), 2)
        response_data.append(
            MonthlySalaryInputResponse(
                id=item.id,
                employee_id=item.employee_id,
                employee_name=item.employee.full_name if item.employee else None,
                employee_code=item.employee.employee_code if item.employee else None,
                salary_period=item.salary_period,
                actual_working_days=item.actual_working_days,
                meal_allowance_free=item.meal_allowance_free,
                meal_allowance_tax=item.meal_allowance_tax,
                phone_allowance_free=item.phone_allowance_free,
                trans_allowance_tax=item.trans_allowance_tax,
                perf_allowance_tax=item.perf_allowance_tax,
                other_income=item.other_income,
                **_other_income_response_fields(item),
                bonus=item.bonus,
                advance_payment=item.advance_payment,
                pit_refund=item.pit_refund,
                other_deductions=item.other_deductions,
                bonus_14=item.bonus_14,
                sales_bonus=sales_bonus,
                is_mid_month_change=item.is_mid_month_change,
                prorated_old_salary=item.prorated_old_salary,
                prorated_new_salary=item.prorated_new_salary,
                prorated_days_old=item.prorated_days_old,
                prorated_days_new=item.prorated_days_new,
                mid_month_effective_date=item.mid_month_effective_date,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )
    return response_data


@router.post("/other-income-evidence/{employee_id}")
async def save_other_income_evidence(
    employee_id: int,
    period: str = Form(..., pattern=r"^\d{4}-\d{2}$"),
    other_income: int = Form(..., ge=0),
    note: str = Form(...),
    document: Optional[UploadFile] = File(default=None),
    db: Session = Depends(get_db),
):
    """Save the manual other-income amount, explanation and optional private evidence."""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên")

    clean_note = note.strip()
    if other_income > 0 and not clean_note:
        raise HTTPException(status_code=422, detail="Vui lòng nhập lý do cho khoản Thu nhập khác")
    if len(clean_note) > 2000:
        raise HTTPException(status_code=422, detail="Lý do không được vượt quá 2.000 ký tự")

    item = _get_or_create_monthly_input(db, employee, period)
    previous_path = item.other_income_document_path
    new_file_path: Optional[Path] = None

    if document and document.filename:
        original_name = Path(document.filename).name
        suffix = Path(original_name).suffix.lower()
        if suffix not in OTHER_INCOME_ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(OTHER_INCOME_ALLOWED_EXTENSIONS))
            raise HTTPException(status_code=422, detail=f"Định dạng chứng từ không được hỗ trợ. Cho phép: {allowed}")

        contents = await document.read(OTHER_INCOME_MAX_FILE_SIZE + 1)
        if len(contents) > OTHER_INCOME_MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="Chứng từ không được vượt quá 15 MB")
        if not contents:
            raise HTTPException(status_code=422, detail="Chứng từ tải lên đang trống")

        OTHER_INCOME_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        new_file_path = OTHER_INCOME_UPLOAD_DIR / f"{employee_id}_{period}_{uuid4().hex}{suffix}"
        new_file_path.write_bytes(contents)
        item.other_income_document_path = str(new_file_path)
        item.other_income_document_name = original_name
        item.other_income_document_content_type = document.content_type or "application/octet-stream"
        item.other_income_document_size = len(contents)
        item.other_income_document_uploaded_at = datetime.now(timezone.utc)

    item.other_income = other_income
    item.other_income_note = clean_note or None

    try:
        db.commit()
        db.refresh(item)
    except Exception:
        db.rollback()
        if new_file_path and new_file_path.exists():
            new_file_path.unlink(missing_ok=True)
        raise

    if new_file_path and previous_path and previous_path != str(new_file_path):
        old_path = Path(previous_path)
        try:
            if old_path.resolve().is_relative_to(OTHER_INCOME_UPLOAD_DIR.resolve()):
                old_path.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass

    return {
        "employee_id": employee.id,
        "employee_name": employee.full_name,
        "salary_period": period,
        "other_income": item.other_income,
        **_other_income_response_fields(item),
        "message": "Đã lưu Thu nhập khác và chứng từ liên quan",
    }


@router.get("/other-income-evidence/{employee_id}/file")
def download_other_income_evidence(
    employee_id: int,
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    item = db.query(MonthlySalaryInput).filter(
        MonthlySalaryInput.employee_id == employee_id,
        MonthlySalaryInput.salary_period == period,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Chưa có dữ liệu Thu nhập khác cho tháng này")
    file_path = _resolve_private_other_income_file(item)
    return FileResponse(
        path=file_path,
        media_type=item.other_income_document_content_type or "application/octet-stream",
        filename=item.other_income_document_name or file_path.name,
    )


@router.delete("/other-income-evidence/{employee_id}/file", status_code=status.HTTP_204_NO_CONTENT)
def delete_other_income_evidence(
    employee_id: int,
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    item = db.query(MonthlySalaryInput).filter(
        MonthlySalaryInput.employee_id == employee_id,
        MonthlySalaryInput.salary_period == period,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Chưa có dữ liệu Thu nhập khác cho tháng này")
    file_path = _resolve_private_other_income_file(item)
    item.other_income_document_path = None
    item.other_income_document_name = None
    item.other_income_document_content_type = None
    item.other_income_document_size = None
    item.other_income_document_uploaded_at = None
    db.commit()
    file_path.unlink(missing_ok=True)
    return None


@router.put("/inputs/{input_id}", response_model=MonthlySalaryInputResponse)
def update_monthly_salary_input(
    input_id: int,
    payload: MonthlySalaryInputUpdate,
    db: Session = Depends(get_db),
):
    item = db.query(MonthlySalaryInput).filter(MonthlySalaryInput.id == input_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Monthly salary input record not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    db.commit()
    db.refresh(item)

    from app.services.salary import get_sales_bonus_for_employee_period
    sales_bonus = round(get_sales_bonus_for_employee_period(db, item.employee_id, item.salary_period), 2)
    return MonthlySalaryInputResponse(
        id=item.id,
        employee_id=item.employee_id,
        employee_name=item.employee.full_name if item.employee else None,
        employee_code=item.employee.employee_code if item.employee else None,
        salary_period=item.salary_period,
        actual_working_days=item.actual_working_days,
        meal_allowance_free=item.meal_allowance_free,
        meal_allowance_tax=item.meal_allowance_tax,
        phone_allowance_free=item.phone_allowance_free,
        trans_allowance_tax=item.trans_allowance_tax,
        perf_allowance_tax=item.perf_allowance_tax,
        other_income=item.other_income,
        **_other_income_response_fields(item),
        bonus=item.bonus,
        advance_payment=item.advance_payment,
        pit_refund=item.pit_refund,
        other_deductions=item.other_deductions,
        bonus_14=item.bonus_14,
        sales_bonus=sales_bonus,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.delete("/inputs/{input_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_monthly_salary_input(
    input_id: int,
    db: Session = Depends(get_db),
):
    item = db.query(MonthlySalaryInput).filter(MonthlySalaryInput.id == input_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Monthly salary input record not found")

    evidence_path: Optional[Path] = None
    if item.other_income_document_path:
        try:
            candidate = Path(item.other_income_document_path).resolve()
            if candidate.is_relative_to(OTHER_INCOME_UPLOAD_DIR.resolve()):
                evidence_path = candidate
        except (OSError, ValueError):
            evidence_path = None

    db.delete(item)
    db.commit()
    if evidence_path:
        evidence_path.unlink(missing_ok=True)
    return None


@router.get("/export")
def download_salary_report(
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    from app.services.salary import export_salary_report
    try:
        output = export_salary_report(db, period)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
        
    filename = f"salary_table_{period}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


class PublishPayslipsPayload(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    is_published: bool = True


@router.post("/publish")
def publish_payslips(
    payload: PublishPayslipsPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    employees = db.query(Employee).filter(Employee.is_active == True).all()
    
    # Also include inactive employees if they already have a drafted row for this period
    # Or maybe just query all inputs first, and active employees.
    existing_inputs = db.query(MonthlySalaryInput).filter(MonthlySalaryInput.salary_period == payload.period).all()
    existing_by_emp = {item.employee_id: item for item in existing_inputs}

    published_count = 0

    for emp in employees:
        m_input = existing_by_emp.get(emp.id)
        if not m_input:
            # Materialize the row since it hasn't been saved yet
            blended_data = get_blended_salary_for_period(db, emp.id, payload.period, emp.contract_salary)
            
            m_input = MonthlySalaryInput(
                employee_id=emp.id,
                salary_period=payload.period,
                salary_policy_id=resolve_salary_policy(db, payload.period).id,
                actual_working_days=22.0,
                meal_allowance_free=emp.meal_allowance,
                meal_allowance_tax=0,
                phone_allowance_free=emp.phone_allowance,
                trans_allowance_tax=emp.trans_allowance,
                perf_allowance_tax=emp.other_allowance,
                other_income=0,
                bonus=0,
                bonus_14=0,
                advance_payment=0,
                pit_refund=0,
                other_deductions=0,
                is_mid_month_change=blended_data.get("is_mid_month_change", False),
                prorated_old_salary=blended_data.get("prorated_old_salary"),
                prorated_new_salary=blended_data.get("prorated_new_salary"),
                prorated_days_old=blended_data.get("prorated_days_old"),
                prorated_days_new=blended_data.get("prorated_days_new"),
                mid_month_effective_date=blended_data.get("effective_date_str"),
                contract_salary=blended_data.get("blended_salary", emp.contract_salary),
                fullname=emp.full_name,
                position=emp.position,
                employee_type=emp.employee_type,
                dependents_count=emp.dependents_count,
                account_number=emp.account_number,
                bank_name=emp.bank_name
            )
            db.add(m_input)
            existing_by_emp[emp.id] = m_input

    newly_published_employee_ids: list[int] = []
    # Now toggle the is_published flag for all these inputs
    for item in existing_by_emp.values():
        if payload.is_published and not bool(item.is_published):
            newly_published_employee_ids.append(item.employee_id)
        item.is_published = payload.is_published
        published_count += 1

    if newly_published_employee_ids:
        notification_employees = (
            db.query(Employee)
            .filter(Employee.id.in_(newly_published_employee_ids), Employee.user_id.isnot(None))
            .all()
        )
        add_employee_notifications(
            db,
            notification_employees,
            category=PAYROLL,
            event_type="PAYSLIP_PUBLISHED",
            title=f"Phiếu lương tháng {payload.period[5:7]}/{payload.period[:4]} đã phát hành",
            message="Kế toán trưởng đã phát hành phiếu lương. Bạn có thể mở Phiếu lương cá nhân để xem và tải PDF.",
            actor_user_id=actor_id(current_user),
            resource_type="SALARY_PERIOD",
            resource_id=payload.period,
            action_url="/user/my-payslip",
        )

    db.commit()

    return {
        "status": "ok",
        "published_count": published_count,
        "is_published": payload.is_published,
    }
