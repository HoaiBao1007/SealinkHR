from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user, get_db
from app.core.auth import get_password_hash
from app.core.roles import DIRECTOR, HR_ADMIN, IT_ADMIN, USER
from app.models.employee import Employee
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.access_role_service import (
    infer_employee_access_role,
    sync_all_employee_access_roles,
)


router = APIRouter(
    prefix="/api/access",
    tags=["access-control"],
    dependencies=[Depends(get_admin_user)],
)

ASSIGNABLE_ROLES = {DIRECTOR, HR_ADMIN, IT_ADMIN, USER}


class AccessUserPayload(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    role: str | None = None
    employee_id: int


@router.get("/users")
def list_access_users(db: Session = Depends(get_db)):
    sync_all_employee_access_roles(db)
    db.commit()
    employees = {row.user_id: row for row in db.query(Employee).filter(Employee.user_id.is_not(None)).all()}
    return [
        {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "employee_id": employees[user.id].id if user.id in employees else None,
            "employee_name": employees[user.id].full_name if user.id in employees else None,
        }
        for user in db.query(User).order_by(User.id.asc()).all()
    ]


@router.post("/users", status_code=201)
def create_access_user(
    payload: AccessUserPayload,
    db: Session = Depends(get_db),
    actor: User = Depends(get_admin_user),
):
    employee = db.get(Employee, payload.employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ nhân viên.")
    role, role_reason = infer_employee_access_role(db, employee)
    requested_role = payload.role.strip().upper() if payload.role else None
    if requested_role and requested_role not in ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=422,
            detail="Chỉ được cấp vai trò DIRECTOR, HR_ADMIN, IT_ADMIN hoặc USER tại đây.",
        )
    if requested_role and requested_role != role:
        raise HTTPException(
            status_code=422,
            detail=f"Vai trò được xác định tự động là {role}: {role_reason}.",
        )
    username = payload.username.strip()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại.")
    if employee.user_id:
        raise HTTPException(status_code=409, detail="Hồ sơ nhân viên đã liên kết tài khoản.")
    user = User(
        username=username,
        password_hash=get_password_hash(payload.password),
        role=role,
    )
    db.add(user)
    db.flush()
    employee.user_id = user.id
    record_audit(
        db,
        actor=actor,
        action="ACCESS_USER_CREATE",
        resource_type="USER",
        resource_id=user.id,
        summary=f"Tạo tài khoản {username} với vai trò {role}",
        after={"username": username, "role": role, "employee_id": employee.id},
    )
    db.commit()
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "employee_id": employee.id,
        "employee_name": employee.full_name,
        "role_reason": role_reason,
    }


@router.post("/sync")
def sync_access_roles(
    db: Session = Depends(get_db),
    actor: User = Depends(get_admin_user),
):
    rows = sync_all_employee_access_roles(db)
    changed = [row for row in rows if row["changed"]]
    record_audit(
        db,
        actor=actor,
        action="ACCESS_ROLE_SYNC",
        resource_type="USER",
        summary=f"Đồng bộ quyền theo cơ cấu tổ chức: {len(changed)} tài khoản thay đổi",
        after={"changed": changed},
    )
    db.commit()
    return {"changed_count": len(changed), "rows": rows}
