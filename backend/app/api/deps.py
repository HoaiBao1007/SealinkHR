from collections.abc import Generator
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth import verify_token
from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.user import User
from app.models.employee import Employee
from app.core.roles import (
    ADMIN,
    ATTENDANCE_MANAGER_ROLES,
    AUDIT_READER_ROLES,
    BUSINESS_ADMIN_ROLES,
    HR_MANAGER_ROLES,
    IT_ADMIN,
    PERSONAL_PORTAL_ROLES,
)
from app.services.access_role_service import sync_employee_access_role
from app.services.trusted_device_service import active_device_for_credential, TRUSTED_DEVICE_COOKIE


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.split(" ")[1]
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yêu cầu đăng nhập. Thiếu hoặc sai định dạng token.",
        )
    
    payload = verify_token(raw_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập hết hạn hoặc không hợp lệ. Vui lòng đăng nhập lại.",
        )
    
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thông tin xác thực không hợp lệ.",
        )
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tài khoản không tồn tại.",
        )
    if user.role == IT_ADMIN and settings.it_admin_trusted_device_required:
        token_device_id = payload.get("trusted_device_id")
        raw_device_credential = request.cookies.get(TRUSTED_DEVICE_COOKIE)
        trusted_device = active_device_for_credential(
            db,
            user_id=user.id,
            raw_credential=raw_device_credential,
        )
        if not trusted_device or str(trusted_device.id) != str(token_device_id):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Phiên IT_ADMIN không thuộc thiết bị đã đăng ký. Vui lòng đăng nhập lại trên máy IT được phép.",
            )
    if user.role != ADMIN:
        employee = db.query(Employee).filter(Employee.user_id == user.id).first()
        if employee:
            _, _, changed = sync_employee_access_role(db, employee)
            if changed:
                db.commit()
                db.refresh(user)
    return user


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    return _require_role(
        current_user,
        BUSINESS_ADMIN_ROLES,
        "Quyền truy cập bị từ chối. Chỉ dành cho Giám đốc, Kế toán trưởng hoặc IT_ADMIN.",
    )


def _require_role(current_user: User, allowed_roles: frozenset[str], detail: str) -> User:
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    return current_user


def get_hr_manager_user(current_user: User = Depends(get_current_user)) -> User:
    """Allow chief accountant or operational HR administrator."""
    return _require_role(
        current_user,
        HR_MANAGER_ROLES,
        "Bạn không có quyền quản lý hồ sơ nhân sự.",
    )


def get_attendance_manager_user(current_user: User = Depends(get_current_user)) -> User:
    """Allow roles that may import, review and override attendance."""
    return _require_role(
        current_user,
        ATTENDANCE_MANAGER_ROLES,
        "Bạn không có quyền quản lý bảng công.",
    )


def get_it_admin_user(current_user: User = Depends(get_current_user)) -> User:
    return _require_role(
        current_user,
        frozenset({IT_ADMIN}),
        "Chức năng này chỉ dành cho bộ phận IT.",
    )


def get_audit_reader_user(current_user: User = Depends(get_current_user)) -> User:
    return _require_role(
        current_user,
        AUDIT_READER_ROLES,
        "Bạn không có quyền xem nhật ký hệ thống.",
    )


def get_personal_portal_user(current_user: User = Depends(get_current_user)) -> User:
    return _require_role(
        current_user,
        PERSONAL_PORTAL_ROLES,
        "Tài khoản này không sử dụng cổng thông tin cá nhân.",
    )


def get_admin_employee_actor(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> Employee:
    """Return the employee profile linked to the authenticated administrator.

    Legacy audit tables reference employees, so accepting an actor identifier from
    a request would allow an administrator to impersonate another employee.
    """
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tài khoản quản trị chưa liên kết với hồ sơ nhân sự để ghi audit.",
        )
    return employee


def get_attendance_employee_actor(
    current_user: User = Depends(get_attendance_manager_user),
    db: Session = Depends(get_db),
) -> Employee:
    """Return the employee profile used by legacy attendance audit tables."""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tài khoản chưa liên kết với hồ sơ nhân sự để ghi lịch sử thao tác.",
        )
    return employee
