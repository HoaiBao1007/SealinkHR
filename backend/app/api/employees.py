from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
import os
import uuid
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_admin_user
from app.models.employee import Employee
from app.models.user import User
from app.services.access_role_service import (
    infer_employee_access_role,
    sync_employee_access_role,
)
from app.models.salary_decision import SalaryDecision
from app.models.monthly_salary_input import MonthlySalaryInput
from app.models.attendance_daily import AttendanceDaily
from app.models.attendance_log import AttendanceLog
from app.models.attendance_override_audit import AttendanceOverrideAudit
from app.models.off_request import OffRequest
from app.models.timesheet import Timesheet
from app.models.timesheet_entry import TimesheetEntry
from app.models.timesheet_period import TimesheetPeriod
from app.models.department import Department
from app.models.commission import (
    CommissionBonusEntitlement,
    CommissionCalculationSnapshot,
    CommissionPayoutPolicy,
    CommissionPayoutSchedule,
    CommissionWalletLedger,
)
from app.core.auth import get_password_hash
from app.core.employee_type import (
    FULLTIME,
    allowance_defaults_for_type,
    apply_contract_allowance_defaults,
    normalize_employee_type,
)
from app.services.salary_decision_service import apply_type_decision_to_salary_inputs
from app.services.notification_service import HR, actor_id, add_notification

router = APIRouter(tags=["employees"], dependencies=[Depends(get_admin_user)])

UPLOAD_DIRECTORY = Path(__file__).resolve().parents[2] / "uploads"
MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_DOCUMENT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


def _document_url(stored_url: str) -> str:
    """Expose documents only through the authenticated document endpoint."""
    return f"/api/documents/{Path(stored_url).name}"


def _document_urls(raw_urls: str | None) -> list[str]:
    if not raw_urls:
        return []
    return [_document_url(url) for url in json.loads(raw_urls)]


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _attendance_identifier_owner(
    db: Session,
    identifier: str,
    *,
    exclude_employee_id: int | None = None,
) -> Employee | None:
    """Find an employee using an ID as either primary or alternate machine ID."""

    query = db.query(Employee).filter(
        or_(
            Employee.machine_employee_id == identifier,
            Employee.biometric_id == identifier,
        )
    )
    if exclude_employee_id is not None:
        query = query.filter(Employee.id != exclude_employee_id)
    return query.first()


class EmployeeCreateRequest(BaseModel):
    machine_employee_id: str = Field(min_length=1, max_length=50)
    biometric_id: Optional[str] = Field(default=None, max_length=50)
    full_name: str = Field(min_length=1, max_length=150)
    notion_name: Optional[str] = Field(default=None, max_length=150)
    department_code: Optional[str] = None
    department_name: Optional[str] = None
    department_id: Optional[int] = None
    annual_leave_quota: float = 12
    is_active: bool = True
    status: Optional[str] = "ACTIVE"
    employee_code: Optional[str] = None
    position: Optional[str] = None
    contract_salary: int = 0
    meal_allowance: int = Field(default=1200000, ge=0)
    phone_allowance: int = Field(default=2000000, ge=0)
    trans_allowance: int = Field(default=2000000, ge=0)
    other_allowance: int = Field(default=0, ge=0)
    employee_type: str = "FULLTIME"
    dependents_count: int = 0
    account_number: Optional[str] = None
    bank_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = Field(default=None, max_length=128)
    start_date: Optional[str] = None
    resignation_period: Optional[str] = None
    tax_code: Optional[str] = None
    phone_number: Optional[str] = None
    company_phone_number: Optional[str] = None
    social_insurance_number: Optional[str] = None
    pvi_insurance: Optional[str] = None
    health_insurance_number: Optional[str] = None
    company_email: Optional[str] = None
    personal_email: Optional[str] = None
    notes: Optional[str] = None
    cccd_url: Optional[str] = None
    contract_url: Optional[str] = None
    bonus_coefficient: Optional[float] = 0.0

class EmployeeUpdateRequest(BaseModel):
    machine_employee_id: Optional[str] = None
    biometric_id: Optional[str] = None
    full_name: Optional[str] = None
    notion_name: Optional[str] = None
    department_code: Optional[str] = None
    department_name: Optional[str] = None
    department_id: Optional[int] = None
    annual_leave_quota: Optional[float] = None
    annual_leave_used: Optional[float] = None
    paid_leave_balance: Optional[float] = None
    unpaid_leave_balance: Optional[float] = None
    is_active: Optional[bool] = None
    status: Optional[str] = None
    employee_code: Optional[str] = None
    position: Optional[str] = None
    contract_salary: Optional[int] = None
    meal_allowance: Optional[int] = Field(default=None, ge=0)
    phone_allowance: Optional[int] = Field(default=None, ge=0)
    trans_allowance: Optional[int] = Field(default=None, ge=0)
    other_allowance: Optional[int] = Field(default=None, ge=0)
    employee_type: Optional[str] = None
    employee_type_effective_date: Optional[date] = None
    dependents_count: Optional[int] = None
    account_number: Optional[str] = None
    bank_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = Field(default=None, max_length=128)
    start_date: Optional[str] = None
    resignation_period: Optional[str] = None
    tax_code: Optional[str] = None
    phone_number: Optional[str] = None
    company_phone_number: Optional[str] = None
    social_insurance_number: Optional[str] = None
    pvi_insurance: Optional[str] = None
    health_insurance_number: Optional[str] = None
    company_email: Optional[str] = None
    personal_email: Optional[str] = None
    notes: Optional[str] = None
    cccd_url: Optional[str] = None
    contract_url: Optional[str] = None
    bonus_coefficient: Optional[float] = None

class EmployeeResponse(BaseModel):
    id: int
    machine_employee_id: str
    biometric_id: Optional[str] = None
    full_name: str
    notion_name: Optional[str]
    department_code: Optional[str]
    department_name: Optional[str]
    department_id: Optional[int]
    annual_leave_quota: float
    annual_leave_used: float
    paid_leave_balance: float
    unpaid_leave_balance: float
    is_active: bool
    status: str
    employee_code: Optional[str]
    position: Optional[str]
    contract_salary: int
    meal_allowance: int
    phone_allowance: int
    trans_allowance: int
    other_allowance: int
    employee_type: str
    dependents_count: int
    account_number: Optional[str]
    bank_name: Optional[str]
    tax_code: Optional[str]
    phone_number: Optional[str]
    company_phone_number: Optional[str]
    social_insurance_number: Optional[str]
    pvi_insurance: Optional[str] = None
    health_insurance_number: Optional[str] = None
    company_email: Optional[str] = None
    personal_email: Optional[str] = None
    notes: Optional[str] = None
    cccd_url: Optional[list[str]] = None
    contract_url: Optional[list[str]] = None
    username: Optional[str] = None
    account_role: Optional[str] = None
    access_role: str = "USER"
    access_role_reason: str = ""
    start_date: Optional[str] = None
    resignation_period: Optional[str] = None
    bonus_coefficient: float


def _to_response(emp: Employee, db: Session) -> EmployeeResponse:
    username = emp.user.username if emp.user else None
    access_role, access_role_reason = infer_employee_access_role(db, emp)
    return EmployeeResponse(
        id=emp.id,
        machine_employee_id=emp.machine_employee_id,
        biometric_id=emp.biometric_id,
        full_name=emp.full_name,
        notion_name=emp.notion_name,
        department_code=emp.department_code,
        department_name=emp.department_name,
        department_id=emp.department_id,
        annual_leave_quota=float(emp.annual_leave_quota),
        annual_leave_used=float(emp.annual_leave_used),
        paid_leave_balance=float(emp.paid_leave_balance),
        unpaid_leave_balance=float(emp.unpaid_leave_balance),
        is_active=emp.is_active,
        status=emp.status,
        employee_code=emp.employee_code,
        position=emp.position,
        contract_salary=emp.contract_salary,
        meal_allowance=emp.meal_allowance,
        phone_allowance=emp.phone_allowance,
        trans_allowance=emp.trans_allowance,
        other_allowance=emp.other_allowance,
        employee_type=emp.employee_type,
        dependents_count=emp.dependents_count,
        account_number=emp.account_number,
        bank_name=emp.bank_name,
        tax_code=emp.tax_code,
        phone_number=emp.phone_number,
        company_phone_number=emp.company_phone_number,
        social_insurance_number=emp.social_insurance_number,
        pvi_insurance=emp.pvi_insurance,
        health_insurance_number=emp.health_insurance_number,
        company_email=emp.company_email,
        personal_email=emp.personal_email,
        notes=emp.notes,
        cccd_url=_document_urls(emp.cccd_url),
        contract_url=_document_urls(emp.contract_url),
        username=username,
        account_role=emp.user.role if emp.user else None,
        access_role=access_role,
        access_role_reason=access_role_reason,
        start_date=emp.start_date.isoformat() if emp.start_date else None,
        resignation_period=emp.resignation_period,
        bonus_coefficient=float(emp.bonus_coefficient) if emp.bonus_coefficient is not None else 0.0
    )



@router.get("/api/employees", response_model=list[EmployeeResponse])
def list_employees(
    q: Optional[str] = Query(default=None),
    department: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[EmployeeResponse]:
    query = db.query(Employee)
    if q:
        keyword = f"%{q.strip()}%"
        query = query.filter(
            (Employee.full_name.ilike(keyword))
            | (Employee.machine_employee_id.ilike(keyword))
            | (Employee.notion_name.ilike(keyword))
        )
    if department:
        query = query.filter(Employee.department_name == department)
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)
    employees = query.order_by(Employee.id.asc()).all()
    return [_to_response(emp, db) for emp in employees]


@router.get("/api/employees/{employee_id}", response_model=EmployeeResponse)
def get_employee(employee_id: int, db: Session = Depends(get_db)) -> EmployeeResponse:
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if employee is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")
    return _to_response(employee, db)


@router.post("/api/employees", response_model=EmployeeResponse)
def create_employee(
    payload: EmployeeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user),
) -> EmployeeResponse:
    machine_employee_id = payload.machine_employee_id.strip()
    exists = _attendance_identifier_owner(db, machine_employee_id)
    if exists:
        raise HTTPException(
            status_code=409,
            detail="Mã máy chấm công (ID) đã được dùng làm mã chính hoặc mã phụ của nhân viên khác.",
        )

    biometric_id_val = _normalize_optional_text(payload.biometric_id)
    if biometric_id_val is not None:
        bio_exists = _attendance_identifier_owner(db, biometric_id_val)
        if bio_exists:
            raise HTTPException(
                status_code=409,
                detail="Mã vân tay (Biometric ID) đã được dùng làm mã chính hoặc mã phụ của nhân viên khác.",
            )

    notion_name = _normalize_optional_text(payload.notion_name)
    if notion_name is not None:
        notion_exists = db.query(Employee).filter(Employee.notion_name == notion_name).first()
        if notion_exists:
            raise HTTPException(status_code=409, detail="Tên Notion này đã được liên kết với nhân sự khác.")

    try:
        employee_type = normalize_employee_type(payload.employee_type)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    status_val = payload.status or ("ACTIVE" if payload.is_active else "LOCKED")
    is_active_val = True if status_val == "ACTIVE" else False

    # Auto-generate employee_code sequentially starting from SL001
    import re
    all_codes = db.query(Employee.employee_code).filter(Employee.employee_code.isnot(None)).all()
    max_num = 0
    for (code,) in all_codes:
        if code:
            match = re.match(r"^SL(\d+)$", code, re.IGNORECASE)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
    generated_employee_code = f"SL{max_num + 1:03d}"
    
    emp_code = _normalize_optional_text(payload.employee_code) or generated_employee_code

    username = _normalize_optional_text(payload.username)
    password = payload.password.strip() if payload.password and payload.password.strip() else None

    if username:
        user_exists = db.query(User).filter(User.username == username).first()
        if user_exists:
            raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại")
        if not password:
            raise HTTPException(status_code=400, detail="Mật khẩu là bắt buộc khi điền tên đăng nhập")
    if password and not username:
        raise HTTPException(status_code=400, detail="Vui lòng điền tên đăng nhập khi tạo mật khẩu")
    if password and len(password) < 12:
        raise HTTPException(status_code=422, detail="Mật khẩu phải có ít nhất 12 ký tự")
    try:
        user = None
        if username:
            user = User(
                username=username,
                password_hash=get_password_hash(password),
                role="USER",
            )
            db.add(user)
            db.flush()

        from datetime import date
        parsed_start_date = None
        if payload.start_date:
            try:
                parsed_start_date = date.fromisoformat(payload.start_date.split('T')[0])
            except ValueError:
                pass

        contract_allowances = allowance_defaults_for_type(employee_type)
        # For a newly created full-time employee, preserve any explicit
        # configuration entered by HR. Trial and intern employees always start
        # with no allowances.
        if employee_type == FULLTIME:
            contract_allowances = {
                "meal_allowance": payload.meal_allowance,
                "phone_allowance": payload.phone_allowance,
                "trans_allowance": payload.trans_allowance,
                "other_allowance": payload.other_allowance,
            }

        employee = Employee(
            machine_employee_id=payload.machine_employee_id.strip(),
            biometric_id=biometric_id_val,
            full_name=payload.full_name.strip(),
            notion_name=notion_name,
            department_code=_normalize_optional_text(payload.department_code),
            department_name=_normalize_optional_text(payload.department_name),
            department_id=payload.department_id,
            annual_leave_quota=Decimal(str(payload.annual_leave_quota)),
            annual_leave_used=Decimal("0"),
            paid_leave_balance=Decimal("0"),
            unpaid_leave_balance=Decimal("0"),
            is_active=is_active_val,
            status=status_val,
            employee_code=emp_code,
            position=_normalize_optional_text(payload.position),
            contract_salary=payload.contract_salary,
            meal_allowance=contract_allowances["meal_allowance"],
            phone_allowance=contract_allowances["phone_allowance"],
            trans_allowance=contract_allowances["trans_allowance"],
            other_allowance=contract_allowances["other_allowance"],
            employee_type=employee_type,
            dependents_count=payload.dependents_count,
            account_number=_normalize_optional_text(payload.account_number),
            bank_name=_normalize_optional_text(payload.bank_name),
            tax_code=_normalize_optional_text(payload.tax_code),
            phone_number=_normalize_optional_text(payload.phone_number),
            company_phone_number=_normalize_optional_text(payload.company_phone_number),
            social_insurance_number=_normalize_optional_text(payload.social_insurance_number),
            pvi_insurance=_normalize_optional_text(payload.pvi_insurance),
            health_insurance_number=_normalize_optional_text(payload.health_insurance_number),
            company_email=_normalize_optional_text(payload.company_email),
            personal_email=_normalize_optional_text(payload.personal_email),
            notes=_normalize_optional_text(payload.notes),
            cccd_url=_normalize_optional_text(payload.cccd_url),
            contract_url=_normalize_optional_text(payload.contract_url),
            user_id=user.id if user else None,
            start_date=parsed_start_date,
            resignation_period=_normalize_optional_text(payload.resignation_period),
        )
        db.add(employee)
        db.flush()
        sync_employee_access_role(db, employee)
        add_notification(
            db,
            category=HR,
            event_type="EMPLOYEE_CREATED",
            title="Có nhân viên mới",
            message=f"{current_user.username} đã tạo hồ sơ nhân viên {employee.full_name} ({employee.employee_code or employee.machine_employee_id}).",
            actor_user_id=actor_id(current_user),
            resource_type="EMPLOYEE",
            resource_id=employee.id,
        )
        db.commit()
        db.refresh(employee)
        return _to_response(employee, db)
    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống khi tạo nhân viên: {e}")


@router.put("/api/employees/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user),
) -> EmployeeResponse:
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="employee not found")

    previous_type = employee.employee_type
    previous_allowances = {
        "meal_allowance": employee.meal_allowance,
        "phone_allowance": employee.phone_allowance,
        "trans_allowance": employee.trans_allowance,
        "other_allowance": employee.other_allowance,
    }

    if payload.machine_employee_id is not None:
        new_machine_id = payload.machine_employee_id.strip()
        if not new_machine_id:
            raise HTTPException(status_code=400, detail="machine_employee_id cannot be empty")
        exists = _attendance_identifier_owner(
            db,
            new_machine_id,
            exclude_employee_id=employee_id,
        )
        if exists:
            raise HTTPException(
                status_code=409,
                detail="Mã máy chấm công (ID) đã được dùng làm mã chính hoặc mã phụ của nhân viên khác.",
            )
        employee.machine_employee_id = new_machine_id

    if payload.biometric_id is not None:
        new_biometric_id = _normalize_optional_text(payload.biometric_id)
        if new_biometric_id is not None:
            exists = _attendance_identifier_owner(
                db,
                new_biometric_id,
                exclude_employee_id=employee_id,
            )
            if exists:
                raise HTTPException(
                    status_code=409,
                    detail="Mã vân tay (Biometric ID) đã được dùng làm mã chính hoặc mã phụ của nhân viên khác.",
                )
        employee.biometric_id = new_biometric_id

    if payload.full_name is not None:
        employee.full_name = payload.full_name.strip()
    if payload.notion_name is not None:
        new_notion_name = _normalize_optional_text(payload.notion_name)
        if new_notion_name is not None:
            exists = db.query(Employee).filter(Employee.notion_name == new_notion_name, Employee.id != employee_id).first()
            if exists:
                raise HTTPException(status_code=409, detail="Tên Notion này đã được liên kết với nhân sự khác.")
        employee.notion_name = new_notion_name
    if payload.department_code is not None:
        employee.department_code = _normalize_optional_text(payload.department_code)
    if payload.department_name is not None:
        employee.department_name = _normalize_optional_text(payload.department_name)
    if payload.department_id is not None:
        employee.department_id = payload.department_id
    if payload.annual_leave_quota is not None:
        employee.annual_leave_quota = Decimal(str(payload.annual_leave_quota))
    if payload.annual_leave_used is not None:
        employee.annual_leave_used = Decimal(str(payload.annual_leave_used))
    if payload.paid_leave_balance is not None:
        employee.paid_leave_balance = Decimal(str(payload.paid_leave_balance))
    if payload.unpaid_leave_balance is not None:
        employee.unpaid_leave_balance = Decimal(str(payload.unpaid_leave_balance))
    
    if payload.status is not None:
        employee.status = payload.status
        employee.is_active = True if payload.status == "ACTIVE" else False
        if payload.status != "RESIGNED":
            employee.resignation_period = None
    elif payload.is_active is not None:
        employee.is_active = payload.is_active
        if payload.is_active:
            employee.status = "ACTIVE"
            employee.resignation_period = None
        elif employee.status == "ACTIVE":
            employee.status = "LOCKED"

    if payload.resignation_period is not None:
        employee.resignation_period = _normalize_optional_text(payload.resignation_period)
    if payload.start_date is not None:
        val = _normalize_optional_text(payload.start_date)
        if val:
            try:
                employee.start_date = date.fromisoformat(val.split('T')[0])
            except ValueError:
                pass
        else:
            employee.start_date = None

    if payload.employee_code is not None:
        employee.employee_code = _normalize_optional_text(payload.employee_code)
    if payload.position is not None:
        employee.position = _normalize_optional_text(payload.position)
    if payload.contract_salary is not None:
        employee.contract_salary = payload.contract_salary
    if payload.meal_allowance is not None:
        employee.meal_allowance = payload.meal_allowance
    if payload.phone_allowance is not None:
        employee.phone_allowance = payload.phone_allowance
    if payload.trans_allowance is not None:
        employee.trans_allowance = payload.trans_allowance
    if payload.other_allowance is not None:
        employee.other_allowance = payload.other_allowance
    if payload.employee_type is not None:
        try:
            employee_type = normalize_employee_type(payload.employee_type)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        type_changed = previous_type != employee_type
        if type_changed:
            allowance_fields = (
                payload.meal_allowance,
                payload.phone_allowance,
                payload.trans_allowance,
                payload.other_allowance,
            )
            if employee_type != FULLTIME or not any(value is not None for value in allowance_fields):
                apply_contract_allowance_defaults(employee, employee_type)

            effective_date = payload.employee_type_effective_date or date.today()
            type_decision = SalaryDecision(
                employee_id=employee.id,
                old_salary=employee.contract_salary,
                new_salary=employee.contract_salary,
                meal_allowance=employee.meal_allowance,
                trans_allowance=employee.trans_allowance,
                phone_allowance=employee.phone_allowance,
                other_allowance=employee.other_allowance,
                bonus_coefficient=employee.bonus_coefficient,
                old_employee_type=previous_type,
                new_employee_type=employee_type,
                old_meal_allowance=previous_allowances["meal_allowance"],
                old_trans_allowance=previous_allowances["trans_allowance"],
                old_phone_allowance=previous_allowances["phone_allowance"],
                old_other_allowance=previous_allowances["other_allowance"],
                effective_date=effective_date,
                reason=f"Chuyển loại nhân viên: {previous_type} → {employee_type}",
                status="ACTIVE" if effective_date <= date.today() else "PENDING",
            )
            db.add(type_decision)

            if effective_date <= date.today():
                employee.employee_type = employee_type
                apply_type_decision_to_salary_inputs(db, type_decision)
            else:
                # Keep the live profile unchanged until the scheduled promotion date.
                employee.employee_type = previous_type
                employee.meal_allowance = previous_allowances["meal_allowance"]
                employee.phone_allowance = previous_allowances["phone_allowance"]
                employee.trans_allowance = previous_allowances["trans_allowance"]
                employee.other_allowance = previous_allowances["other_allowance"]
        else:
            employee.employee_type = employee_type
    if payload.dependents_count is not None:
        employee.dependents_count = payload.dependents_count
    if payload.account_number is not None:
        employee.account_number = _normalize_optional_text(payload.account_number)
    if payload.bank_name is not None:
        employee.bank_name = _normalize_optional_text(payload.bank_name)
    if payload.tax_code is not None:
        employee.tax_code = _normalize_optional_text(payload.tax_code)
    if payload.phone_number is not None:
        employee.phone_number = _normalize_optional_text(payload.phone_number)
    if payload.company_phone_number is not None:
        employee.company_phone_number = _normalize_optional_text(payload.company_phone_number)
    if payload.social_insurance_number is not None:
        employee.social_insurance_number = _normalize_optional_text(payload.social_insurance_number)
    if payload.pvi_insurance is not None:
        employee.pvi_insurance = _normalize_optional_text(payload.pvi_insurance)
    if payload.health_insurance_number is not None:
        employee.health_insurance_number = _normalize_optional_text(payload.health_insurance_number)
    if payload.company_email is not None:
        employee.company_email = _normalize_optional_text(payload.company_email)
    if payload.personal_email is not None:
        employee.personal_email = _normalize_optional_text(payload.personal_email)
    if payload.notes is not None:
        employee.notes = _normalize_optional_text(payload.notes)

    username = _normalize_optional_text(payload.username)
    password = payload.password.strip() if payload.password and payload.password.strip() else None

    if password and len(password) < 12:
        raise HTTPException(status_code=422, detail="Mật khẩu phải có ít nhất 12 ký tự")
    if password and not username and not employee.user_id:
        raise HTTPException(status_code=400, detail="Vui lòng điền tên đăng nhập khi tạo mật khẩu")

    try:
        if employee.user_id:
            user = db.query(User).filter(User.id == employee.user_id).first()
            if user:
                if username and username != user.username:
                    user_exists = db.query(User).filter(User.username == username).first()
                    if user_exists:
                        raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại")
                    user.username = username
                if password:
                    user.password_hash = get_password_hash(password)
                db.add(user)
        else:
            if username:
                user_exists = db.query(User).filter(User.username == username).first()
                if user_exists:
                    raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại")
                
                if not password:
                    raise HTTPException(status_code=400, detail="Mật khẩu là bắt buộc khi tạo tài khoản đăng nhập")
                user = User(
                    username=username,
                    password_hash=get_password_hash(password),
                    role="USER",
                )
                db.add(user)
                db.flush()
                employee.user_id = user.id

        employee.updated_at = datetime.now(timezone.utc)
        db.flush()
        sync_employee_access_role(db, employee)
        add_notification(
            db,
            category=HR,
            event_type="EMPLOYEE_UPDATED",
            title="Hồ sơ nhân viên đã được cập nhật",
            message=f"{current_user.username} đã cập nhật hồ sơ nhân viên {employee.full_name} ({employee.employee_code or employee.machine_employee_id}).",
            actor_user_id=actor_id(current_user),
            resource_type="EMPLOYEE",
            resource_id=employee.id,
        )
        db.commit()
        db.refresh(employee)
        return _to_response(employee, db)
    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống khi cập nhật nhân viên: {e}")


from PIL import Image
import io

class DeleteDocumentRequest(BaseModel):
    url: str
    doc_type: str  # 'cccd' or 'contract'

def process_and_save_upload(employee_id: int, file: UploadFile, prefix: str) -> str:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Tệp tải lên không có tên hợp lệ.")

    file_extension = Path(file.filename).suffix.lower()
    if file_extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận ảnh JPG/PNG/WEBP hoặc tệp PDF.")

    content = file.file.read()
    if not content or len(content) > MAX_DOCUMENT_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Tệp phải có dung lượng từ 1 byte đến 10 MB.")

    is_image = file_extension in {".jpg", ".jpeg", ".png", ".webp"}
    if is_image:
        try:
            image = Image.open(io.BytesIO(content))
            image.verify()
            image = Image.open(io.BytesIO(content))
            image = image.convert('RGB')
            unique_filename = f"{prefix}_{employee_id}_{uuid.uuid4().hex}.webp"
            UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
            file_path = UPLOAD_DIRECTORY / unique_filename
            image.save(file_path, "WEBP")
            return f"/api/documents/{unique_filename}"
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Tệp ảnh không hợp lệ.") from exc

    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Tệp PDF không hợp lệ.")
    unique_filename = f"{prefix}_{employee_id}_{uuid.uuid4().hex}{file_extension}"
    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIRECTORY / unique_filename).write_bytes(content)
    return f"/api/documents/{unique_filename}"


@router.get("/api/documents/{filename}")
def download_employee_document(filename: str, db: Session = Depends(get_db)) -> FileResponse:
    safe_filename = Path(filename).name
    if safe_filename != filename:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")

    is_referenced = any(
        safe_filename in {Path(url).name for url in json.loads(employee.cccd_url or "[]") + json.loads(employee.contract_url or "[]")}
        for employee in db.query(Employee).all()
    )
    if not is_referenced:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")

    path = UPLOAD_DIRECTORY / safe_filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp trên máy chủ.")
    return FileResponse(path, filename=safe_filename, content_disposition_type="inline")


@router.post("/api/employees/{employee_id}/upload-cccd", response_model=EmployeeResponse)
def upload_employee_cccd(employee_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên")
    
    current_urls = json.loads(employee.cccd_url) if employee.cccd_url else []
    for file in files:
        url = process_and_save_upload(employee_id, file, "cccd")
        current_urls.append(url)
        
    employee.cccd_url = json.dumps(current_urls)
    db.commit()
    db.refresh(employee)
    return _to_response(employee, db)


@router.post("/api/employees/{employee_id}/upload-contract", response_model=EmployeeResponse)
def upload_employee_contract(employee_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên")
    
    current_urls = json.loads(employee.contract_url) if employee.contract_url else []
    for file in files:
        url = process_and_save_upload(employee_id, file, "contract")
        current_urls.append(url)
        
    employee.contract_url = json.dumps(current_urls)
    db.commit()
    db.refresh(employee)
    return _to_response(employee, db)


@router.post("/api/employees/{employee_id}/delete-document", response_model=EmployeeResponse)
def delete_employee_document(employee_id: int, req: DeleteDocumentRequest, db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên")
        
    if req.doc_type not in {'cccd', 'contract'}:
        raise HTTPException(status_code=400, detail="Loại tài liệu không hợp lệ")

    urls_attr = 'cccd_url' if req.doc_type == 'cccd' else 'contract_url'
    urls_str = getattr(employee, urls_attr)
    urls = json.loads(urls_str) if urls_str else []
    target_filename = Path(req.url).name
    stored_url = next((url for url in urls if Path(url).name == target_filename), None)

    if stored_url:
        urls.remove(stored_url)
        setattr(employee, urls_attr, json.dumps(urls))
        db.commit()
        db.refresh(employee)
        
        try:
            file_path = UPLOAD_DIRECTORY / target_filename
            if file_path.is_file():
                os.remove(file_path)
        except Exception:
            pass
            
    return _to_response(employee, db)


@router.delete("/api/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user),
) -> Response:
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="employee not found")

    # Employee removal is intentionally a full cleanup for a test/temporary
    # employee. Child rows must be cleared before the parent; MySQL otherwise
    # correctly rejects DELETE employees because timesheet_entries and other
    # operational records still reference it.
    user_id = employee.user_id
    employee_label = employee.employee_code or employee.machine_employee_id
    employee_name = employee.full_name
    document_urls = [
        *(_document_urls(employee.cccd_url)),
        *(_document_urls(employee.contract_url)),
    ]
    try:
        # Audit/approval references are not owned by the employee being
        # deleted, but they cannot retain a non-null FK to this employee.
        db.query(AttendanceOverrideAudit).filter(
            (AttendanceOverrideAudit.employee_id == employee_id)
            | (AttendanceOverrideAudit.changed_by_user_id == employee_id)
        ).delete(synchronize_session=False)
        db.query(TimesheetEntry).filter(
            (TimesheetEntry.employee_id == employee_id)
            | (TimesheetEntry.overridden_by_user_id == employee_id)
        ).delete(synchronize_session=False)
        db.query(OffRequest).filter(OffRequest.approved_by_user_id == employee_id).update(
            {OffRequest.approved_by_user_id: None}, synchronize_session=False
        )
        db.query(OffRequest).filter(OffRequest.employee_id == employee_id).delete(synchronize_session=False)
        db.query(Timesheet).filter(Timesheet.approved_by_user_id == employee_id).update(
            {Timesheet.approved_by_user_id: None}, synchronize_session=False
        )
        db.query(TimesheetPeriod).filter(TimesheetPeriod.locked_by_user_id == employee_id).update(
            {TimesheetPeriod.locked_by_user_id: None}, synchronize_session=False
        )
        db.query(Timesheet).filter(Timesheet.employee_id == employee_id).delete(synchronize_session=False)
        db.query(AttendanceDaily).filter(AttendanceDaily.employee_id == employee_id).delete(synchronize_session=False)
        db.query(AttendanceLog).filter(AttendanceLog.employee_id == employee_id).delete(synchronize_session=False)
        db.query(MonthlySalaryInput).filter(MonthlySalaryInput.employee_id == employee_id).delete(synchronize_session=False)
        db.query(SalaryDecision).filter(SalaryDecision.employee_id == employee_id).delete(synchronize_session=False)

        # Keep the commission ledger as an accounting trail, but detach the
        # deleted test employee. This works even on older databases whose FK
        # migration did not yet include ON DELETE SET NULL.
        for model in (
            CommissionWalletLedger,
            CommissionBonusEntitlement,
            CommissionCalculationSnapshot,
            CommissionPayoutPolicy,
            CommissionPayoutSchedule,
        ):
            db.query(model).filter(model.employee_id == employee_id).update(
                {model.employee_id: None}, synchronize_session=False
            )
        db.query(Department).filter(Department.manager_id == employee_id).update(
            {Department.manager_id: None}, synchronize_session=False
        )

        add_notification(
            db,
            category=HR,
            event_type="EMPLOYEE_DELETED",
            title="Hồ sơ nhân viên đã bị xóa",
            message=f"{current_user.username} đã xóa hồ sơ nhân viên {employee_name} ({employee_label}).",
            actor_user_id=actor_id(current_user),
            resource_type="EMPLOYEE",
            resource_id=employee_id,
        )

        db.delete(employee)
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                db.delete(user)
        db.commit()
    except Exception:
        db.rollback()
        raise

    for url in document_urls:
        try:
            file_path = UPLOAD_DIRECTORY / Path(url).name
            if file_path.is_file():
                os.remove(file_path)
        except OSError:
            pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)

from datetime import date

class SalaryDecisionCreate(BaseModel):
    old_salary: int
    new_salary: int
    meal_allowance: int = 1200000
    trans_allowance: int = 2000000
    phone_allowance: int = 2000000
    other_allowance: int = 0
    bonus_coefficient: float = 0.0
    effective_date: date
    reason: Optional[str] = None

class SalaryDecisionUpdate(BaseModel):
    old_salary: Optional[int] = None
    new_salary: Optional[int] = None
    meal_allowance: Optional[int] = None
    trans_allowance: Optional[int] = None
    phone_allowance: Optional[int] = None
    other_allowance: Optional[int] = None
    bonus_coefficient: Optional[float] = None
    effective_date: Optional[date] = None
    reason: Optional[str] = None
    status: Optional[str] = None

class SalaryDecisionResponse(BaseModel):
    id: int
    employee_id: int
    old_salary: int
    new_salary: int
    meal_allowance: int
    trans_allowance: int
    phone_allowance: int
    other_allowance: int
    bonus_coefficient: float
    old_employee_type: Optional[str] = None
    new_employee_type: Optional[str] = None
    effective_date: date
    reason: Optional[str] = None
    status: str
    
    class Config:
        from_attributes = True

@router.get("/api/employees/{employee_id}/salary-decisions", response_model=list[SalaryDecisionResponse])
def get_salary_decisions(employee_id: int, db: Session = Depends(get_db)):
    decisions = db.query(SalaryDecision).filter(SalaryDecision.employee_id == employee_id).order_by(SalaryDecision.effective_date.desc()).all()
    return decisions

@router.post("/api/employees/{employee_id}/salary-decisions", response_model=SalaryDecisionResponse)
def create_salary_decision(employee_id: int, req: SalaryDecisionCreate, db: Session = Depends(get_db)):
    decision = SalaryDecision(
        employee_id=employee_id,
        old_salary=req.old_salary,
        new_salary=req.new_salary,
        meal_allowance=req.meal_allowance,
        trans_allowance=req.trans_allowance,
        phone_allowance=req.phone_allowance,
        other_allowance=req.other_allowance,
        bonus_coefficient=req.bonus_coefficient,
        effective_date=req.effective_date,
        reason=req.reason,
        status="PENDING" if req.effective_date > date.today() else "ACTIVE"
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    
    # If active immediately, update contract_salary
    if decision.status == "ACTIVE":
        emp = db.query(Employee).filter(Employee.id == employee_id).first()
        if emp:
            emp.contract_salary = decision.new_salary
            emp.meal_allowance = decision.meal_allowance
            emp.trans_allowance = decision.trans_allowance
            emp.phone_allowance = decision.phone_allowance
            emp.other_allowance = decision.other_allowance
            db.commit()
            
    return decision

@router.put("/api/salary-decisions/{decision_id}", response_model=SalaryDecisionResponse)
def update_salary_decision(decision_id: int, req: SalaryDecisionUpdate, db: Session = Depends(get_db)):
    decision = db.query(SalaryDecision).filter(SalaryDecision.id == decision_id).first()
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
        
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(decision, k, v)
        
    db.commit()
    db.refresh(decision)
    return decision

@router.delete("/api/salary-decisions/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_salary_decision(decision_id: int, db: Session = Depends(get_db)):
    decision = db.query(SalaryDecision).filter(SalaryDecision.id == decision_id).first()
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
        
    db.delete(decision)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
