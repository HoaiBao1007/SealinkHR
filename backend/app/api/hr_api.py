from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_hr_manager_user
from app.core.auth import get_password_hash
from app.core.employee_type import normalize_employee_type
from app.models.department import Department
from app.models.employee import Employee
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.notification_service import HR, actor_id, add_notification
from app.services.access_role_service import (
    infer_employee_access_role,
    sync_all_employee_access_roles,
    sync_employee_access_role,
)


router = APIRouter(
    prefix="/api/hr",
    tags=["hr-operations"],
    dependencies=[Depends(get_hr_manager_user)],
)


class HrEmployeePayload(BaseModel):
    machine_employee_id: Optional[str] = Field(default=None, max_length=50)
    biometric_id: Optional[str] = Field(default=None, max_length=50)
    full_name: Optional[str] = Field(default=None, max_length=150)
    notion_name: Optional[str] = Field(default=None, max_length=150)
    department_id: Optional[int] = None
    department_code: Optional[str] = Field(default=None, max_length=50)
    department_name: Optional[str] = Field(default=None, max_length=150)
    annual_leave_quota: Optional[float] = Field(default=None, ge=0)
    annual_leave_used: Optional[float] = Field(default=None, ge=0)
    paid_leave_balance: Optional[float] = Field(default=None, ge=0)
    unpaid_leave_balance: Optional[float] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    status: Optional[str] = Field(default=None, max_length=50)
    employee_code: Optional[str] = Field(default=None, max_length=50)
    position: Optional[str] = Field(default=None, max_length=150)
    employee_type: Optional[str] = Field(default=None, max_length=50)
    dependents_count: Optional[int] = Field(default=None, ge=0)
    start_date: Optional[date] = None
    resignation_period: Optional[str] = Field(default=None, max_length=7)
    tax_code: Optional[str] = Field(default=None, max_length=50)
    phone_number: Optional[str] = Field(default=None, max_length=50)
    company_phone_number: Optional[str] = Field(default=None, max_length=50)
    social_insurance_number: Optional[str] = Field(default=None, max_length=50)
    pvi_insurance: Optional[str] = Field(default=None, max_length=50)
    health_insurance_number: Optional[str] = Field(default=None, max_length=50)
    company_email: Optional[str] = Field(default=None, max_length=150)
    personal_email: Optional[str] = Field(default=None, max_length=150)
    notes: Optional[str] = Field(default=None, max_length=500)
    account_number: Optional[str] = Field(default=None, max_length=50)
    bank_name: Optional[str] = Field(default=None, max_length=150)
    username: Optional[str] = Field(default=None, max_length=100)
    password: Optional[str] = Field(default=None, min_length=12, max_length=128)


class HrEmployeeResponse(BaseModel):
    id: int
    machine_employee_id: str
    biometric_id: str | None
    full_name: str
    notion_name: str | None
    department_id: int | None
    department_code: str | None
    department_name: str | None
    annual_leave_quota: float
    annual_leave_used: float
    paid_leave_balance: float
    unpaid_leave_balance: float
    is_active: bool
    status: str
    employee_code: str | None
    position: str | None
    employee_type: str
    dependents_count: int
    start_date: str | None
    resignation_period: str | None
    tax_code: str | None
    phone_number: str | None
    company_phone_number: str | None
    social_insurance_number: str | None
    pvi_insurance: str | None
    health_insurance_number: str | None
    company_email: str | None
    personal_email: str | None
    notes: str | None
    account_number: str | None
    bank_name: str | None
    username: str | None
    account_role: str | None = None
    access_role: str = "USER"
    access_role_reason: str = ""
    financial_setup_status: str = "RESTRICTED"


class HrDepartmentPayload(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    manager_id: int | None = None
    parent_id: int | None = None
    sort_order: int = 0


class HrDepartmentResponse(BaseModel):
    id: int
    name: str
    manager_id: int | None
    parent_id: int | None
    sort_order: int
    employee_count: int


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _employee_snapshot(employee: Employee) -> dict:
    """A deliberately finance-free audit snapshot."""
    return {
        "id": employee.id,
        "machine_employee_id": employee.machine_employee_id,
        "biometric_id": employee.biometric_id,
        "full_name": employee.full_name,
        "notion_name": employee.notion_name,
        "department_id": employee.department_id,
        "department_name": employee.department_name,
        "annual_leave_quota": float(employee.annual_leave_quota or 0),
        "annual_leave_used": float(employee.annual_leave_used or 0),
        "is_active": employee.is_active,
        "status": employee.status,
        "employee_code": employee.employee_code,
        "position": employee.position,
        "employee_type": employee.employee_type,
        "start_date": employee.start_date,
        "resignation_period": employee.resignation_period,
        "company_email": employee.company_email,
        "personal_email": employee.personal_email,
        "phone_number": employee.phone_number,
        "company_phone_number": employee.company_phone_number,
    }


def _to_employee_response(employee: Employee, db: Session) -> HrEmployeeResponse:
    access_role, access_role_reason = infer_employee_access_role(db, employee)
    return HrEmployeeResponse(
        id=employee.id,
        machine_employee_id=employee.machine_employee_id,
        biometric_id=employee.biometric_id,
        full_name=employee.full_name,
        notion_name=employee.notion_name,
        department_id=employee.department_id,
        department_code=employee.department_code,
        department_name=employee.department_name,
        annual_leave_quota=float(employee.annual_leave_quota or 0),
        annual_leave_used=float(employee.annual_leave_used or 0),
        paid_leave_balance=float(employee.paid_leave_balance or 0),
        unpaid_leave_balance=float(employee.unpaid_leave_balance or 0),
        is_active=employee.is_active,
        status=employee.status,
        employee_code=employee.employee_code,
        position=employee.position,
        employee_type=employee.employee_type,
        dependents_count=employee.dependents_count,
        start_date=employee.start_date.isoformat() if employee.start_date else None,
        resignation_period=employee.resignation_period,
        tax_code=employee.tax_code,
        phone_number=employee.phone_number,
        company_phone_number=employee.company_phone_number,
        social_insurance_number=employee.social_insurance_number,
        pvi_insurance=employee.pvi_insurance,
        health_insurance_number=employee.health_insurance_number,
        company_email=employee.company_email,
        personal_email=employee.personal_email,
        notes=employee.notes,
        account_number=employee.account_number,
        bank_name=employee.bank_name,
        username=employee.user.username if employee.user else None,
        account_role=employee.user.role if employee.user else None,
        access_role=access_role,
        access_role_reason=access_role_reason,
    )


def _validate_identifier(
    db: Session, identifier: str, *, employee_id: int | None = None
) -> None:
    query = db.query(Employee).filter(
        or_(
            Employee.machine_employee_id == identifier,
            Employee.biometric_id == identifier,
        )
    )
    if employee_id is not None:
        query = query.filter(Employee.id != employee_id)
    if query.first():
        raise HTTPException(status_code=409, detail="Mã máy chấm công đã thuộc hồ sơ khác.")


@router.get("/employees", response_model=list[HrEmployeeResponse])
def list_hr_employees(
    q: str | None = Query(default=None),
    department_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[HrEmployeeResponse]:
    query = db.query(Employee).options(joinedload(Employee.user))
    if q:
        keyword = f"%{q.strip()}%"
        query = query.filter(
            Employee.full_name.ilike(keyword)
            | Employee.machine_employee_id.ilike(keyword)
            | Employee.notion_name.ilike(keyword)
            | Employee.employee_code.ilike(keyword)
        )
    if department_id is not None:
        query = query.filter(Employee.department_id == department_id)
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)
    return [_to_employee_response(row, db) for row in query.order_by(Employee.id.asc()).all()]


@router.get("/employees/{employee_id}", response_model=HrEmployeeResponse)
def get_hr_employee(employee_id: int, db: Session = Depends(get_db)) -> HrEmployeeResponse:
    employee = (
        db.query(Employee)
        .options(joinedload(Employee.user))
        .filter(Employee.id == employee_id)
        .first()
    )
    if not employee:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")
    return _to_employee_response(employee, db)


@router.post("/employees", response_model=HrEmployeeResponse, status_code=status.HTTP_201_CREATED)
def create_hr_employee(
    payload: HrEmployeePayload,
    db: Session = Depends(get_db),
    actor: User = Depends(get_hr_manager_user),
) -> HrEmployeeResponse:
    machine_id = _clean(payload.machine_employee_id)
    full_name = _clean(payload.full_name)
    if not machine_id or not full_name:
        raise HTTPException(status_code=422, detail="Mã máy và họ tên là bắt buộc.")
    _validate_identifier(db, machine_id)

    department = None
    if payload.department_id is not None:
        department = db.query(Department).filter(Department.id == payload.department_id).first()
        if not department:
            raise HTTPException(status_code=404, detail="Không tìm thấy phòng ban.")

    employee = Employee(
        machine_employee_id=machine_id,
        biometric_id=_clean(payload.biometric_id),
        full_name=full_name,
        notion_name=_clean(payload.notion_name),
        department_id=department.id if department else None,
        department_name=department.name if department else _clean(payload.department_name),
        department_code=_clean(payload.department_code),
        annual_leave_quota=payload.annual_leave_quota if payload.annual_leave_quota is not None else 12,
        is_active=True if payload.is_active is None else payload.is_active,
        status=_clean(payload.status) or "ACTIVE",
        employee_code=_clean(payload.employee_code),
        position=_clean(payload.position),
        employee_type=normalize_employee_type(payload.employee_type or "FULLTIME"),
        dependents_count=payload.dependents_count or 0,
        start_date=payload.start_date,
        resignation_period=_clean(payload.resignation_period),
        tax_code=_clean(payload.tax_code),
        phone_number=_clean(payload.phone_number),
        company_phone_number=_clean(payload.company_phone_number),
        social_insurance_number=_clean(payload.social_insurance_number),
        pvi_insurance=_clean(payload.pvi_insurance),
        health_insurance_number=_clean(payload.health_insurance_number),
        company_email=_clean(payload.company_email),
        personal_email=_clean(payload.personal_email),
        notes=_clean(payload.notes),
        account_number=_clean(payload.account_number),
        bank_name=_clean(payload.bank_name),
        # Operational HR may create the profile but must not assign money.
        contract_salary=0,
        meal_allowance=0,
        phone_allowance=0,
        trans_allowance=0,
        other_allowance=0,
        bonus_coefficient=0,
    )
    db.add(employee)
    db.flush()

    username = _clean(payload.username)
    if username:
        if not payload.password:
            raise HTTPException(status_code=422, detail="Cần mật khẩu khi tạo tài khoản.")
        if db.query(User).filter(User.username == username).first():
            raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại.")
        user = User(username=username, password_hash=get_password_hash(payload.password), role="USER")
        db.add(user)
        db.flush()
        employee.user_id = user.id

    sync_employee_access_role(db, employee)

    record_audit(
        db,
        actor=actor,
        action="HR_EMPLOYEE_CREATE",
        resource_type="EMPLOYEE",
        resource_id=employee.id,
        summary=f"Tạo hồ sơ nhân viên {employee.full_name}",
        after=_employee_snapshot(employee),
    )
    add_notification(
        db,
        category=HR,
        event_type="EMPLOYEE_CREATED",
        title="Có nhân viên mới",
        message=f"{actor.username} đã tạo hồ sơ nhân viên {employee.full_name} ({employee.employee_code or employee.machine_employee_id}).",
        actor_user_id=actor_id(actor),
        resource_type="EMPLOYEE",
        resource_id=employee.id,
    )
    db.commit()
    db.refresh(employee)
    return _to_employee_response(employee, db)


@router.patch("/employees/{employee_id}", response_model=HrEmployeeResponse)
def update_hr_employee(
    employee_id: int,
    payload: HrEmployeePayload,
    db: Session = Depends(get_db),
    actor: User = Depends(get_hr_manager_user),
) -> HrEmployeeResponse:
    employee = (
        db.query(Employee)
        .options(joinedload(Employee.user))
        .filter(Employee.id == employee_id)
        .first()
    )
    if not employee:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")
    before = _employee_snapshot(employee)
    values = payload.model_dump(exclude_unset=True)

    if "machine_employee_id" in values and values["machine_employee_id"]:
        machine_id = str(values["machine_employee_id"]).strip()
        _validate_identifier(db, machine_id, employee_id=employee.id)
        employee.machine_employee_id = machine_id
    if "biometric_id" in values:
        biometric_id = _clean(values["biometric_id"])
        if biometric_id:
            _validate_identifier(db, biometric_id, employee_id=employee.id)
        employee.biometric_id = biometric_id
    if "department_id" in values:
        department = None
        if values["department_id"] is not None:
            department = db.query(Department).filter(Department.id == values["department_id"]).first()
            if not department:
                raise HTTPException(status_code=404, detail="Không tìm thấy phòng ban.")
        employee.department_id = department.id if department else None
        employee.department_name = department.name if department else None

    direct_fields = {
        "full_name",
        "notion_name",
        "department_code",
        "department_name",
        "annual_leave_quota",
        "annual_leave_used",
        "paid_leave_balance",
        "unpaid_leave_balance",
        "is_active",
        "status",
        "employee_code",
        "position",
        "dependents_count",
        "start_date",
        "resignation_period",
        "tax_code",
        "phone_number",
        "company_phone_number",
        "social_insurance_number",
        "pvi_insurance",
        "health_insurance_number",
        "company_email",
        "personal_email",
        "notes",
        "account_number",
        "bank_name",
    }
    for field in direct_fields:
        if field in values and field not in {"department_name"}:
            value = values[field]
            if isinstance(value, str):
                value = _clean(value)
            setattr(employee, field, value)
    if "department_name" in values and "department_id" not in values:
        employee.department_name = _clean(values["department_name"])
    if "employee_type" in values and values["employee_type"]:
        # Classification only. This endpoint intentionally never mutates any
        # salary or allowance field.
        employee.employee_type = normalize_employee_type(values["employee_type"])

    account_user = employee.user
    username = _clean(values.get("username")) if "username" in values else None
    if "username" in values:
        if username:
            duplicate = db.query(User).filter(User.username == username)
            if employee.user_id:
                duplicate = duplicate.filter(User.id != employee.user_id)
            if duplicate.first():
                raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại.")
            if account_user:
                account_user.username = username
            else:
                password = values.get("password")
                if not password:
                    raise HTTPException(status_code=422, detail="Cần mật khẩu khi tạo tài khoản.")
                user = User(username=username, password_hash=get_password_hash(password), role="USER")
                db.add(user)
                db.flush()
                employee.user_id = user.id
                account_user = user
        elif account_user:
            employee.user_id = None
            account_user = None
    if values.get("password"):
        if not account_user:
            raise HTTPException(status_code=422, detail="Hồ sơ chưa có tài khoản.")
        account_user.password_hash = get_password_hash(values["password"])

    db.flush()
    sync_employee_access_role(db, employee)

    record_audit(
        db,
        actor=actor,
        action="HR_EMPLOYEE_UPDATE",
        resource_type="EMPLOYEE",
        resource_id=employee.id,
        summary=f"Cập nhật hồ sơ nhân viên {employee.full_name}",
        before=before,
        after=_employee_snapshot(employee),
    )
    add_notification(
        db,
        category=HR,
        event_type="EMPLOYEE_UPDATED",
        title="Hồ sơ nhân sự đã thay đổi",
        message=f"{actor.username} đã cập nhật hồ sơ của {employee.full_name}.",
        actor_user_id=actor_id(actor),
        resource_type="EMPLOYEE",
        resource_id=employee.id,
    )
    db.commit()
    db.refresh(employee)
    return _to_employee_response(employee, db)


@router.post("/employees/{employee_id}/deactivate", response_model=HrEmployeeResponse)
def deactivate_hr_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_hr_manager_user),
) -> HrEmployeeResponse:
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")
    before = _employee_snapshot(employee)
    employee.is_active = False
    employee.status = "INACTIVE"
    record_audit(
        db,
        actor=actor,
        action="HR_EMPLOYEE_DEACTIVATE",
        resource_type="EMPLOYEE",
        resource_id=employee.id,
        summary=f"Ngừng hoạt động hồ sơ {employee.full_name}",
        before=before,
        after=_employee_snapshot(employee),
    )
    add_notification(
        db,
        category=HR,
        event_type="EMPLOYEE_DEACTIVATED",
        title="Nhân viên đã ngừng hoạt động",
        message=f"{actor.username} đã chuyển hồ sơ {employee.full_name} sang trạng thái ngừng hoạt động.",
        actor_user_id=actor_id(actor),
        resource_type="EMPLOYEE",
        resource_id=employee.id,
    )
    db.commit()
    db.refresh(employee)
    return _to_employee_response(employee, db)


@router.get("/departments", response_model=list[HrDepartmentResponse])
def list_hr_departments(db: Session = Depends(get_db)) -> list[HrDepartmentResponse]:
    rows = db.query(Department).options(joinedload(Department.employees)).order_by(
        Department.sort_order.asc(), Department.name.asc()
    ).all()
    return [
        HrDepartmentResponse(
            id=row.id,
            name=row.name,
            manager_id=row.manager_id,
            parent_id=row.parent_id,
            sort_order=row.sort_order,
            employee_count=len(row.employees),
        )
        for row in rows
    ]


@router.post("/departments", response_model=HrDepartmentResponse, status_code=201)
def create_hr_department(
    payload: HrDepartmentPayload,
    db: Session = Depends(get_db),
    actor: User = Depends(get_hr_manager_user),
) -> HrDepartmentResponse:
    if db.query(Department).filter(Department.name == payload.name.strip()).first():
        raise HTTPException(status_code=409, detail="Tên phòng ban đã tồn tại.")
    department = Department(**payload.model_dump())
    department.name = department.name.strip()
    db.add(department)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="HR_DEPARTMENT_CREATE",
        resource_type="DEPARTMENT",
        resource_id=department.id,
        summary=f"Tạo phòng ban {department.name}",
        after=payload.model_dump(),
    )
    db.commit()
    return HrDepartmentResponse(
        id=department.id,
        name=department.name,
        manager_id=department.manager_id,
        parent_id=department.parent_id,
        sort_order=department.sort_order,
        employee_count=0,
    )


@router.patch("/departments/{department_id}", response_model=HrDepartmentResponse)
def update_hr_department(
    department_id: int,
    payload: HrDepartmentPayload,
    db: Session = Depends(get_db),
    actor: User = Depends(get_hr_manager_user),
) -> HrDepartmentResponse:
    department = (
        db.query(Department)
        .options(joinedload(Department.employees))
        .filter(Department.id == department_id)
        .first()
    )
    if not department:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng ban.")
    before = {
        "name": department.name,
        "manager_id": department.manager_id,
        "parent_id": department.parent_id,
        "sort_order": department.sort_order,
    }
    for field, value in payload.model_dump().items():
        setattr(department, field, value.strip() if field == "name" else value)
    record_audit(
        db,
        actor=actor,
        action="HR_DEPARTMENT_UPDATE",
        resource_type="DEPARTMENT",
        resource_id=department.id,
        summary=f"Cập nhật phòng ban {department.name}",
        before=before,
        after=payload.model_dump(),
    )
    db.commit()
    return HrDepartmentResponse(
        id=department.id,
        name=department.name,
        manager_id=department.manager_id,
        parent_id=department.parent_id,
        sort_order=department.sort_order,
        employee_count=len(department.employees),
    )


class DepartmentMembersPayload(BaseModel):
    employee_ids: list[int]


@router.put("/departments/{department_id}/employees", response_model=HrDepartmentResponse)
def set_hr_department_members(
    department_id: int,
    payload: DepartmentMembersPayload,
    db: Session = Depends(get_db),
    actor: User = Depends(get_hr_manager_user),
) -> HrDepartmentResponse:
    department = db.query(Department).filter(Department.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng ban.")
    employees = db.query(Employee).filter(Employee.id.in_(payload.employee_ids)).all()
    if len(employees) != len(set(payload.employee_ids)):
        raise HTTPException(status_code=404, detail="Có nhân viên không tồn tại.")
    old_ids = [
        row.id for row in db.query(Employee).filter(Employee.department_id == department_id).all()
    ]
    db.query(Employee).filter(Employee.department_id == department_id).update(
        {Employee.department_id: None, Employee.department_name: None},
        synchronize_session=False,
    )
    for employee in employees:
        employee.department_id = department.id
        employee.department_name = department.name
    db.flush()
    sync_all_employee_access_roles(db)
    record_audit(
        db,
        actor=actor,
        action="HR_DEPARTMENT_MEMBERS_UPDATE",
        resource_type="DEPARTMENT",
        resource_id=department.id,
        summary=f"Cập nhật {len(employees)} nhân sự trong {department.name}",
        before={"employee_ids": old_ids},
        after={"employee_ids": payload.employee_ids},
    )
    db.commit()
    return HrDepartmentResponse(
        id=department.id,
        name=department.name,
        manager_id=department.manager_id,
        parent_id=department.parent_id,
        sort_order=department.sort_order,
        employee_count=len(employees),
    )
