from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.core.auth import verify_password, generate_token
from app.models.user import User
from app.models.employee import Employee
from app.schemas.user_schemas import UserLoginPayload, TokenResponse, UserResponse
from app.core.roles import ADMIN
from app.core.roles import IT_ADMIN
from app.core.settings import settings
from app.models.trusted_device import TrustedDevice
from app.services.audit_service import record_audit
from app.services.access_role_service import sync_employee_access_role
from app.services.trusted_device_service import (
    TRUSTED_DEVICE_COOKIE,
    enroll_pending_device,
    recover_active_device_from_enrollment_ip,
    request_device,
    request_source_ip,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: UserLoginPayload,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        if user:
            known_device = request_device(db, request, user_id=user.id)
            record_audit(
                db,
                actor=user,
                action="AUTH_LOGIN",
                resource_type="USER_SESSION",
                resource_id=user.id,
                summary=f"Đăng nhập thất bại cho tài khoản {user.username}",
                status="FAILED",
                source_ip=request_source_ip(request),
                device_address=known_device.device_label if known_device else None,
            )
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tên đăng nhập hoặc mật khẩu không chính xác.",
        )

    employee = db.query(Employee).filter(Employee.user_id == user.id).first()
    if employee and user.role != ADMIN:
        sync_employee_access_role(db, employee)
        db.flush()

    source_ip = request_source_ip(request)
    trusted_device = None
    new_device_credential = None
    if user.role == IT_ADMIN and settings.it_admin_trusted_device_required:
        trusted_device = request_device(db, request, user_id=user.id)
        if not trusted_device:
            active_device = (
                db.query(TrustedDevice)
                .filter(TrustedDevice.user_id == user.id, TrustedDevice.is_active.is_(True))
                .first()
            )
            recovered = None
            if active_device and settings.trusted_device_allow_same_ip_recovery:
                recovered = recover_active_device_from_enrollment_ip(
                    db,
                    user_id=user.id,
                    source_ip=source_ip,
                )
            if recovered:
                trusted_device, new_device_credential = recovered
                record_audit(
                    db,
                    actor=user,
                    action="AUTH_LOGIN_DEVICE_RECOVERED",
                    resource_type="TRUSTED_DEVICE",
                    resource_id=trusted_device.id,
                    summary=(
                        f"Cấp lại định danh trình duyệt cho thiết bị "
                        f"{trusted_device.device_label} sau khi cookie bị mất"
                    ),
                    source_ip=source_ip,
                    device_address=trusted_device.device_label,
                )
            enrollment = None
            if not recovered:
                enrollment = enroll_pending_device(
                    db,
                    user_id=user.id,
                    source_ip=source_ip,
                    # Additional admin browsers are allowed only after a
                    # server operator has created a pending enrollment for
                    # this exact source IP. Initial provisioning keeps the
                    # existing optional-IP behavior.
                    require_explicit_enrollment_ip=active_device is not None,
                )
            if not recovered and enrollment:
                trusted_device, new_device_credential = enrollment
            elif not recovered:
                record_audit(
                    db,
                    actor=user,
                    action="AUTH_LOGIN_DEVICE_DENIED",
                    resource_type="USER_SESSION",
                    resource_id=user.id,
                    summary=f"Từ chối đăng nhập {user.username}: thiết bị chưa được đăng ký",
                    status="FAILED",
                    source_ip=source_ip,
                )
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Thiết bị này chưa được phép sử dụng tài khoản IT_ADMIN.",
                )
        trusted_device.last_used_at = datetime.now(timezone.utc)

    # Resolve fullname if linked to an employee
    fullname = None
    if employee:
        fullname = employee.full_name
    elif user.role == ADMIN:
        fullname = "Kế toán trưởng"

    # Generate token
    token_payload = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
    }
    if trusted_device:
        token_payload["trusted_device_id"] = trusted_device.id
    token = generate_token(token_payload)
    record_audit(
        db,
        actor=user,
        action="AUTH_LOGIN",
        resource_type="USER_SESSION",
        resource_id=user.id,
        summary=f"Đăng nhập tài khoản {user.username}",
        source_ip=source_ip,
        device_address=trusted_device.device_label if trusted_device else None,
    )
    db.commit()

    if new_device_credential:
        response.set_cookie(
            key=TRUSTED_DEVICE_COOKIE,
            value=new_device_credential,
            max_age=365 * 24 * 60 * 60,
            httponly=True,
            secure=settings.trusted_device_cookie_secure,
            samesite="strict",
            path="/api",
        )

    return TokenResponse(
        access_token=token,
        role=user.role,
        username=user.username,
        fullname=fullname,
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
