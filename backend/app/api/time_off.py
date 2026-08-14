from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.roles import ADMIN, HR_ADMIN, IT_ADMIN
from app.models.department import Department
from app.models.employee import Employee
from app.models.off_request import ApprovalAction, OffRequest, OffRequestAttachment
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.notification_service import TIME_OFF, dispatch_notification


router = APIRouter(prefix="/api/time-off", tags=["time-off"])

PENDING_MANAGER = "PENDING_MANAGER"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
MORE_INFO_REQUIRED = "MORE_INFO_REQUIRED"

WORKFLOW_STATUSES = {PENDING_MANAGER, APPROVED, REJECTED, MORE_INFO_REQUIRED}
ACTIVE_OVERLAP_STATUSES = {
    "approved",
    "approve",
    "pending",
    "submitted",
    "under review",
    "under_review",
    PENDING_MANAGER.lower(),
    APPROVED.lower(),
    MORE_INFO_REQUIRED.lower(),
}
REQUEST_TYPE_LABELS = {
    "LEAVE_REQUEST": "Leave Request",
    "WORK_FROM_HOME_REQUEST": "Work From Home Request",
    "BUSINESS_TRAVEL_REQUEST": "Business Travel Request",
    # Legacy request types remain readable and accepted for existing clients.
    "ANNUAL_LEAVE": "Nghỉ phép năm",
    "UNPAID_LEAVE": "Nghỉ không lương",
    "SICK_LEAVE": "Nghỉ ốm",
    "OTHER": "Nghỉ khác",
    # Existing imported rows remain readable without being rewritten.
    "paid_leave": "Nghỉ phép năm",
    "unpaid_leave": "Nghỉ không lương",
}
LEAVE_REQUEST = "LEAVE_REQUEST"
WORK_FROM_HOME_REQUEST = "WORK_FROM_HOME_REQUEST"
BUSINESS_TRAVEL_REQUEST = "BUSINESS_TRAVEL_REQUEST"
WEBSITE_REQUEST_TYPES = {LEAVE_REQUEST, WORK_FROM_HOME_REQUEST, BUSINESS_TRAVEL_REQUEST}
LEAVE_RESERVATION_STATUSES = {PENDING_MANAGER, APPROVED}
DAY_PART_LABELS = {
    "FULL_DAY": "Cả ngày",
    "MORNING": "Buổi sáng",
    "AFTERNOON": "Buổi chiều",
    "CUSTOM_TIME": "Theo khung giờ",
}
LOCAL_TIMEZONE = ZoneInfo("Asia/Bangkok")
WORKDAY_SEGMENTS = ((time(8, 0), time(12, 0)), (time(13, 0), time(17, 0)))
WORKDAY_SECONDS = 8 * 60 * 60
TIME_OFF_ATTACHMENT_DIRECTORY = Path(__file__).resolve().parents[2] / "uploads" / "time_off"
MAX_TIME_OFF_ATTACHMENTS = 10
MAX_TIME_OFF_ATTACHMENT_BYTES = 100 * 1024 * 1024
TIME_OFF_ATTACHMENT_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx",
    ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".txt", ".zip",
}
STATUS_LABELS = {
    PENDING_MANAGER: "Under Review",
    APPROVED: "Approved",
    REJECTED: "Rejected",
    MORE_INFO_REQUIRED: "More Information Required",
}


class TimeOffRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_type: Literal[
        "LEAVE_REQUEST",
        "WORK_FROM_HOME_REQUEST",
        "BUSINESS_TRAVEL_REQUEST",
        "ANNUAL_LEAVE",
        "UNPAID_LEAVE",
        "SICK_LEAVE",
        "OTHER",
    ]
    approver_user_id: int | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    # Legacy clients remain supported while the new UI sends start_at/end_at.
    start_date: date | None = None
    end_date: date | None = None
    day_part: Literal["FULL_DAY", "MORNING", "AFTERNOON"] = "FULL_DAY"
    reason: str = Field(min_length=1, max_length=255)
    handover_employee_id: int | None = None
    handover_notes: str | None = Field(default=None, max_length=2000)
    business_travel_location: str | None = Field(default=None, max_length=255)
    business_travel_policy_acknowledged: bool = False
    attachment_ids: list[int] = Field(default_factory=list, max_length=MAX_TIME_OFF_ATTACHMENTS)


class TimeOffActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["APPROVE", "REJECT", "REQUEST_INFO"]
    comment: str | None = Field(default=None, max_length=2000)


class TimeOffScheduleUpdatePayload(BaseModel):
    """Restricted schedule-only update used by IT_ADMIN."""

    model_config = ConfigDict(extra="forbid")

    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class ResolvedApprover:
    user: User
    employee: Employee | None
    source: str


@dataclass(frozen=True)
class NormalizedTimeRange:
    start_at: datetime
    end_at: datetime
    start_date: date
    end_date: date
    day_part: str
    total_days: float


def _current_employee(db: Session, user: User) -> Employee | None:
    return db.query(Employee).filter(Employee.user_id == user.id).first()


def _require_current_employee(db: Session, user: User) -> Employee:
    employee = _current_employee(db, user)
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tài khoản chưa liên kết với hồ sơ nhân viên.",
        )
    return employee


def _employee_department(db: Session, employee: Employee) -> Department | None:
    if employee.department_id is not None:
        department = db.get(Department, employee.department_id)
        if department:
            return department
    department_name = str(employee.department_name or "").strip()
    if not department_name:
        return None
    return (
        db.query(Department)
        .filter(func.lower(Department.name) == department_name.lower())
        .first()
    )


def _approver_from_manager(db: Session, manager: Employee | None, requester: Employee) -> ResolvedApprover | None:
    if not manager or not manager.is_active or manager.id == requester.id or manager.user_id is None:
        return None
    user = db.get(User, manager.user_id)
    if not user:
        return None
    return ResolvedApprover(user=user, employee=manager, source="DEPARTMENT_MANAGER")


def _resolve_approver(db: Session, requester: Employee) -> ResolvedApprover | None:
    department = _employee_department(db, requester)
    visited: set[int] = set()
    current = department
    while current and current.id not in visited:
        visited.add(current.id)
        approver = _approver_from_manager(db, current.manager, requester)
        if approver:
            source = "DEPARTMENT_MANAGER" if current.id == getattr(department, "id", None) else "PARENT_MANAGER"
            return ResolvedApprover(user=approver.user, employee=approver.employee, source=source)
        current = current.parent

    fallback_roles = [HR_ADMIN, ADMIN, IT_ADMIN]
    fallback_users = (
        db.query(User)
        .filter(User.role.in_(fallback_roles), User.id != requester.user_id)
        .order_by(User.id.asc())
        .all()
    )
    fallback_users.sort(key=lambda user: fallback_roles.index(user.role))
    for user in fallback_users:
        employee = db.query(Employee).filter(Employee.user_id == user.id).first()
        if employee and employee.id == requester.id:
            continue
        return ResolvedApprover(user=user, employee=employee, source="FALLBACK_APPROVER")
    return None


def _selectable_approvers(db: Session, requester: Employee) -> list[ResolvedApprover]:
    """Return valid approvers in default-first order.

    The department mapping remains the default. Employees may select another
    configured Manager, but the submitted user id must be present in this
    backend-generated allow-list.
    """
    result: list[ResolvedApprover] = []
    seen_user_ids: set[int] = set()

    def append(approver: ResolvedApprover | None, source: str | None = None) -> None:
        if not approver or approver.user.id in seen_user_ids:
            return
        seen_user_ids.add(approver.user.id)
        result.append(
            ResolvedApprover(
                user=approver.user,
                employee=approver.employee,
                source=source or approver.source,
            )
        )

    # Preserve the existing resolver as the recommended/default approver.
    append(_resolve_approver(db, requester))

    department = _employee_department(db, requester)
    visited_departments: set[int] = set()
    current = department
    while current and current.id not in visited_departments:
        visited_departments.add(current.id)
        source = "DEPARTMENT_MANAGER" if current.id == getattr(department, "id", None) else "PARENT_MANAGER"
        append(_approver_from_manager(db, current.manager, requester), source)
        current = current.parent

    # Managers explicitly assigned to another Department are valid alternate
    # approvers. Merely being an employee is not sufficient.
    managed_departments = (
        db.query(Department)
        .filter(Department.manager_id.is_not(None))
        .order_by(Department.sort_order.asc(), Department.name.asc())
        .all()
    )
    for managed_department in managed_departments:
        append(
            _approver_from_manager(db, managed_department.manager, requester),
            "OTHER_DEPARTMENT_MANAGER",
        )

    # System approvers remain available as a controlled fallback choice.
    fallback_roles = [HR_ADMIN, ADMIN, IT_ADMIN]
    fallback_users = (
        db.query(User)
        .filter(User.role.in_(fallback_roles), User.id != requester.user_id)
        .order_by(User.id.asc())
        .all()
    )
    fallback_users.sort(key=lambda user: fallback_roles.index(user.role))
    for user in fallback_users:
        employee = db.query(Employee).filter(Employee.user_id == user.id).first()
        if employee and (employee.id == requester.id or not employee.is_active):
            continue
        append(
            ResolvedApprover(user=user, employee=employee, source="FALLBACK_APPROVER")
        )

    return result


def _resolve_selected_approver(
    db: Session,
    requester: Employee,
    approver_user_id: int | None,
) -> ResolvedApprover | None:
    options = _selectable_approvers(db, requester)
    if approver_user_id is None:
        return options[0] if options else None
    selected = next(
        (approver for approver in options if approver.user.id == approver_user_id),
        None,
    )
    if not selected:
        raise HTTPException(
            status_code=422,
            detail="Manager được chọn không thuộc danh sách người duyệt hợp lệ.",
        )
    return selected


def _as_local_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(second=0, microsecond=0)
    return value.astimezone(LOCAL_TIMEZONE).replace(tzinfo=None, second=0, microsecond=0)


def _legacy_time_bounds(start_date: date, end_date: date, day_part: str) -> tuple[datetime, datetime]:
    normalized_part = str(day_part or "FULL_DAY").upper()
    if normalized_part == "MORNING":
        return datetime.combine(start_date, time(8, 0)), datetime.combine(end_date, time(12, 0))
    if normalized_part == "AFTERNOON":
        return datetime.combine(start_date, time(13, 0)), datetime.combine(end_date, time(17, 0))
    return datetime.combine(start_date, time(8, 0)), datetime.combine(end_date, time(17, 0))


def _request_time_bounds(request: OffRequest) -> tuple[datetime, datetime]:
    if request.start_at is not None and request.end_at is not None:
        return _as_local_naive(request.start_at), _as_local_naive(request.end_at)
    return _legacy_time_bounds(request.start_date, request.end_date, request.day_part or "FULL_DAY")


def _business_time_days(start_at: datetime, end_at: datetime) -> float:
    if end_at <= start_at:
        raise HTTPException(status_code=422, detail="Thời gian kết thúc phải sau thời gian bắt đầu.")
    if (end_at.date() - start_at.date()).days > 370:
        raise HTTPException(status_code=422, detail="Khoảng nghỉ không được dài quá 370 ngày.")

    working_seconds = 0.0
    cursor = start_at.date()
    while cursor <= end_at.date():
        if cursor.weekday() < 5:
            for segment_start, segment_end in WORKDAY_SEGMENTS:
                segment_from = datetime.combine(cursor, segment_start)
                segment_to = datetime.combine(cursor, segment_end)
                overlap_from = max(start_at, segment_from)
                overlap_to = min(end_at, segment_to)
                if overlap_to > overlap_from:
                    working_seconds += (overlap_to - overlap_from).total_seconds()
        cursor += timedelta(days=1)

    if working_seconds <= 0:
        raise HTTPException(status_code=422, detail="Khoảng nghỉ không chứa giờ làm việc hợp lệ.")
    return round(working_seconds / WORKDAY_SECONDS, 2)


def _leave_balance(
    db: Session,
    employee: Employee,
    *,
    exclude_request_id: int | None = None,
) -> dict[str, float]:
    """Return remaining paid leave without mutating employee master data.

    ``annual_leave_used`` remains the historic/master balance already used by
    payroll. Website Leave Requests in Pending or Approved reserve the same
    quota so concurrent submissions cannot overbook it.
    """
    query = db.query(OffRequest).filter(
        OffRequest.employee_id == employee.id,
        OffRequest.request_type == LEAVE_REQUEST,
        OffRequest.status.in_(LEAVE_RESERVATION_STATUSES),
    )
    if exclude_request_id is not None:
        query = query.filter(OffRequest.id != exclude_request_id)
    reserved_request_days = sum(float(item.total_days or 0) for item in query.all())
    annual_quota = float(employee.annual_leave_quota or 0)
    annual_used = float(employee.annual_leave_used or 0)
    return {
        "annual_quota": annual_quota,
        "annual_used": annual_used,
        "reserved_request_days": round(reserved_request_days, 2),
        "available": round(annual_quota - annual_used - reserved_request_days, 2),
    }


def _ensure_leave_request_balance(
    db: Session,
    employee: Employee,
    requested_days: float,
    *,
    exclude_request_id: int | None = None,
) -> dict[str, float]:
    balance = _leave_balance(db, employee, exclude_request_id=exclude_request_id)
    if requested_days > balance["available"] + 0.0001:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Số phép còn lại không đủ cho yêu cầu này. Còn {max(balance['available'], 0):g} "
                f"ngày, yêu cầu {requested_days:g} ngày."
            ),
        )
    return balance


def _infer_day_part(start_at: datetime, end_at: datetime) -> str:
    if start_at.date() != end_at.date():
        return "CUSTOM_TIME"
    value = (start_at.time(), end_at.time())
    if value == (time(8, 0), time(12, 0)):
        return "MORNING"
    if value == (time(13, 0), time(17, 0)):
        return "AFTERNOON"
    if value == (time(8, 0), time(17, 0)):
        return "FULL_DAY"
    return "CUSTOM_TIME"


def _normalize_datetime_range(start_value: datetime, end_value: datetime) -> NormalizedTimeRange:
    start_at = _as_local_naive(start_value)
    end_at = _as_local_naive(end_value)
    if start_at.minute not in {0, 30} or end_at.minute not in {0, 30}:
        raise HTTPException(
            status_code=422,
            detail="Phút chỉ được chọn ở mốc 00 hoặc 30.",
        )
    return NormalizedTimeRange(
        start_at=start_at,
        end_at=end_at,
        start_date=start_at.date(),
        end_date=end_at.date(),
        day_part=_infer_day_part(start_at, end_at),
        total_days=_business_time_days(start_at, end_at),
    )


def _normalize_time_range(payload: TimeOffRequestPayload) -> NormalizedTimeRange:
    if payload.start_at is not None or payload.end_at is not None:
        if payload.start_at is None or payload.end_at is None:
            raise HTTPException(status_code=422, detail="Cần chọn đầy đủ thời gian bắt đầu và kết thúc.")
        return _normalize_datetime_range(payload.start_at, payload.end_at)
    else:
        if payload.start_date is None or payload.end_date is None:
            raise HTTPException(status_code=422, detail="Cần chọn khoảng ngày và giờ nghỉ.")
        if payload.end_date < payload.start_date:
            raise HTTPException(status_code=422, detail="Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.")
        if payload.day_part != "FULL_DAY" and payload.start_date != payload.end_date:
            raise HTTPException(status_code=422, detail="Đơn nửa ngày chỉ được áp dụng trong cùng một ngày.")
        start_at, end_at = _legacy_time_bounds(payload.start_date, payload.end_date, payload.day_part)
        day_part = payload.day_part

    return NormalizedTimeRange(
        start_at=start_at,
        end_at=end_at,
        start_date=start_at.date(),
        end_date=end_at.date(),
        day_part=day_part,
        total_days=_business_time_days(start_at, end_at),
    )


def _requests_overlap(existing: OffRequest, start_at: datetime, end_at: datetime) -> bool:
    existing_start, existing_end = _request_time_bounds(existing)
    return start_at < existing_end and end_at > existing_start


def _ensure_no_overlap(
    db: Session,
    *,
    employee_id: int,
    start_at: datetime,
    end_at: datetime,
    exclude_request_id: int | None = None,
) -> None:
    query = db.query(OffRequest).filter(
        OffRequest.employee_id == employee_id,
        OffRequest.start_date <= end_at.date(),
        OffRequest.end_date >= start_at.date(),
        func.lower(OffRequest.status).in_(ACTIVE_OVERLAP_STATUSES),
    )
    if exclude_request_id is not None:
        query = query.filter(OffRequest.id != exclude_request_id)
    if any(_requests_overlap(item, start_at, end_at) for item in query.all()):
        raise HTTPException(status_code=409, detail="Bạn đã có đơn nghỉ trùng thời gian này.")


def _validate_handover_employee(db: Session, requester: Employee, employee_id: int | None) -> Employee | None:
    if employee_id is None:
        return None
    employee = db.get(Employee, employee_id)
    if not employee or not employee.is_active:
        raise HTTPException(status_code=422, detail="Người bàn giao không hợp lệ hoặc không còn hoạt động.")
    if employee.id == requester.id:
        raise HTTPException(status_code=422, detail="Người bàn giao phải khác người gửi đơn.")
    return employee


def _validate_business_travel_payload(payload: TimeOffRequestPayload, *, attachment_count: int) -> None:
    if payload.request_type != BUSINESS_TRAVEL_REQUEST:
        return
    if not (payload.business_travel_location or "").strip():
        raise HTTPException(status_code=422, detail="Vui lòng nhập địa điểm công tác.")
    if not payload.business_travel_policy_acknowledged:
        raise HTTPException(
            status_code=422,
            detail="Bạn cần xác nhận đã xem qua quy định công tác trước khi gửi yêu cầu.",
        )
    if attachment_count < 1:
        raise HTTPException(status_code=422, detail="Vui lòng upload quyết định của BGĐ trước khi gửi yêu cầu công tác.")


def _serialize_attachment(attachment: OffRequestAttachment, *, staged: bool = False) -> dict:
    return {
        "id": attachment.id,
        "file_name": attachment.original_filename,
        "content_type": attachment.content_type or "application/octet-stream",
        "size_bytes": attachment.size_bytes,
        "uploaded_at": attachment.created_at,
        "is_staged": staged,
    }


def _resolve_staged_attachments(
    db: Session,
    *,
    uploader_user_id: int,
    attachment_ids: list[int],
) -> list[OffRequestAttachment]:
    unique_ids = list(dict.fromkeys(attachment_ids))
    if len(unique_ids) != len(attachment_ids):
        raise HTTPException(status_code=422, detail="Danh sách file đính kèm không hợp lệ.")
    if len(unique_ids) > MAX_TIME_OFF_ATTACHMENTS:
        raise HTTPException(status_code=422, detail=f"Chỉ được đính kèm tối đa {MAX_TIME_OFF_ATTACHMENTS} file.")
    if not unique_ids:
        return []
    attachments = (
        db.query(OffRequestAttachment)
        .filter(
            OffRequestAttachment.id.in_(unique_ids),
            OffRequestAttachment.uploaded_by_user_id == uploader_user_id,
            OffRequestAttachment.request_id.is_(None),
        )
        .all()
    )
    if len(attachments) != len(unique_ids):
        raise HTTPException(status_code=422, detail="Có file đính kèm không hợp lệ hoặc đã được sử dụng.")
    attachments_by_id = {attachment.id: attachment for attachment in attachments}
    return [attachments_by_id[attachment_id] for attachment_id in unique_ids]


def _attached_file_count(db: Session, request_id: int) -> int:
    return int(
        db.query(func.count(OffRequestAttachment.id))
        .filter(OffRequestAttachment.request_id == request_id)
        .scalar()
        or 0
    )


def _request_viewer_can_access_attachment(request: OffRequest, user: User, employee: Employee | None) -> bool:
    return _is_owner(request, user, employee) or request.approver_user_id == user.id or _is_it_schedule_editor(user)


def _canonical_status(value: str | None) -> str:
    raw = str(value or "").strip()
    upper = raw.upper().replace(" ", "_")
    if upper in WORKFLOW_STATUSES:
        return upper
    if upper in {"PENDING", "SUBMITTED", "UNDER_REVIEW"}:
        return PENDING_MANAGER
    if upper in {"APPROVE", "APPROVED"}:
        return APPROVED
    if upper in {"REJECT", "REJECTED", "CANCELLED", "CANCELED"}:
        return REJECTED
    return upper or PENDING_MANAGER


def _is_owner(request: OffRequest, user: User, employee: Employee | None) -> bool:
    return request.requester_user_id == user.id or bool(employee and request.employee_id == employee.id)


def _is_it_schedule_editor(user: User) -> bool:
    return user.role == IT_ADMIN


def _action_rows(db: Session, request_id: int) -> list[dict]:
    actions = (
        db.query(ApprovalAction)
        .filter(ApprovalAction.request_id == request_id)
        .order_by(ApprovalAction.created_at.asc(), ApprovalAction.id.asc())
        .all()
    )
    actor_employee_ids = {item.actor_employee_id for item in actions if item.actor_employee_id}
    actor_names = {
        employee.id: employee.full_name
        for employee in db.query(Employee).filter(Employee.id.in_(actor_employee_ids)).all()
    } if actor_employee_ids else {}
    actor_user_ids = {item.actor_user_id for item in actions if item.actor_user_id}
    actor_user_names = {
        user.id: user.username
        for user in db.query(User).filter(User.id.in_(actor_user_ids)).all()
    } if actor_user_ids else {}
    return [
        {
            "id": item.id,
            "action": item.action,
            "from_status": item.from_status,
            "to_status": item.to_status,
            "comment": item.comment,
            "actor_name": actor_names.get(item.actor_employee_id) or actor_user_names.get(item.actor_user_id),
            "created_at": item.created_at,
        }
        for item in actions
    ]


def _serialize_request(
    db: Session,
    request: OffRequest,
    *,
    viewer: User,
    viewer_employee: Employee | None,
    include_private: bool,
    include_actions: bool = False,
) -> dict:
    employee = db.get(Employee, request.employee_id)
    department = db.get(Department, request.department_id) if request.department_id else None
    if not department and employee:
        department = _employee_department(db, employee)
    approver_employee = db.get(Employee, request.approver_employee_id) if request.approver_employee_id else None
    approver_user = db.get(User, request.approver_user_id) if request.approver_user_id else None
    approved_by_employee = db.get(Employee, request.approved_by_user_id) if request.approved_by_user_id else None
    # Some historic approved requests were created before approved_by_user_id was
    # consistently saved. The approval action is the immutable fallback record.
    approved_by_user = (
        db.get(User, request.approved_by_user_id)
        if request.approved_by_user_id and not approved_by_employee
        else None
    )
    latest_approval = (
        db.query(ApprovalAction)
        .filter(
            ApprovalAction.request_id == request.id,
            func.upper(ApprovalAction.action) == "APPROVE",
        )
        .order_by(ApprovalAction.created_at.desc(), ApprovalAction.id.desc())
        .first()
    )
    if latest_approval:
        if not approved_by_employee and latest_approval.actor_employee_id:
            approved_by_employee = db.get(Employee, latest_approval.actor_employee_id)
        if not approved_by_user and latest_approval.actor_user_id:
            approved_by_user = db.get(User, latest_approval.actor_user_id)

    manager_employee = approved_by_employee or approver_employee
    manager_user = (
        db.get(User, manager_employee.user_id)
        if manager_employee and manager_employee.user_id
        else (approved_by_user or approver_user)
    )
    handover = db.get(Employee, request.handover_employee_id) if request.handover_employee_id else None
    attachments = (
        db.query(OffRequestAttachment)
        .filter(OffRequestAttachment.request_id == request.id)
        .order_by(OffRequestAttachment.created_at.asc(), OffRequestAttachment.id.asc())
        .all()
        if include_private
        else []
    )
    canonical_status = _canonical_status(request.status)
    own = _is_owner(request, viewer, viewer_employee)
    assigned = request.approver_user_id == viewer.id
    it_schedule_editor = _is_it_schedule_editor(viewer)
    start_at, end_at = _request_time_bounds(request)
    payload = {
        "id": request.id,
        "employee": {
            "id": (employee.id if employee else request.employee_id) if include_private else None,
            "full_name": employee.full_name if employee else "Nhân viên không còn tồn tại",
            "employee_code": employee.employee_code if include_private and employee else None,
        },
        "department": {
            "id": department.id if department else request.department_id,
            "name": department.name if department else (employee.department_name if employee else None),
        },
        "manager": {
            "employee_id": manager_employee.id if include_private and manager_employee else None,
            "user_id": (manager_user.id if manager_user else request.approver_user_id) if include_private else None,
            "full_name": (
                manager_employee.full_name
                if manager_employee
                else (manager_user.username if manager_user else None)
            ) if include_private else None,
        },
        "request_type": request.request_type if include_private else None,
        "request_type_label": REQUEST_TYPE_LABELS.get(request.request_type, request.request_type) if include_private else None,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "start_at": start_at,
        "end_at": end_at,
        "total_days": float(request.total_days or 0),
        "day_part": request.day_part or "FULL_DAY",
        "day_part_label": DAY_PART_LABELS.get(request.day_part or "FULL_DAY", request.day_part) if include_private else None,
        "reason": request.reason if include_private else None,
        "business_travel_location": request.business_travel_location if include_private else None,
        "business_travel_policy_acknowledged": bool(request.business_travel_policy_acknowledged) if include_private else None,
        "attachments": [_serialize_attachment(attachment) for attachment in attachments],
        "handover_employee": (
            {"id": handover.id, "full_name": handover.full_name}
            if include_private and handover
            else None
        ),
        "handover_notes": request.handover_notes if include_private else None,
        "manager_comment": request.manager_comment if include_private else None,
        "status": canonical_status,
        "status_label": STATUS_LABELS.get(canonical_status, canonical_status),
        "submitted_at": request.submitted_at or request.created_at,
        "updated_at": request.updated_at,
        "approved_at": request.approved_at,
        "is_own": own,
        "is_assigned_approver": assigned,
        "can_act": assigned and canonical_status == PENDING_MANAGER and not own,
        "can_edit": own and canonical_status == MORE_INFO_REQUIRED,
        "can_edit_schedule": it_schedule_editor,
    }
    if include_actions:
        payload["actions"] = _action_rows(db, request.id)
    return payload


def _format_request_period(request: OffRequest) -> str:
    start_at, end_at = _request_time_bounds(request)
    start = start_at.strftime("%d/%m/%Y %H:%M")
    end = end_at.strftime("%d/%m/%Y %H:%M")
    return f"{start} đến {end}"


def _notify_approver(db: Session, request: OffRequest, employee: Employee, department: Department, approver: ResolvedApprover, *, resubmitted: bool = False) -> None:
    event_type = "TIME_OFF_RESUBMITTED" if resubmitted else "TIME_OFF_SUBMITTED"
    verb = "đã bổ sung thông tin cho" if resubmitted else "vừa gửi"
    request_label = REQUEST_TYPE_LABELS.get(request.request_type, "yêu cầu")
    dispatch_notification(
        db,
        category=TIME_OFF,
        event_type=event_type,
        title=f"{request_label} cần duyệt",
        message=f"{employee.full_name} – {department.name} {verb} {request_label} từ {_format_request_period(request)}.",
        target_user_id=approver.user.id,
        actor_user_id=employee.user_id,
        resource_type="TIME_OFF_REQUEST",
        resource_id=request.id,
        action_url=f"/time-off/requests/{request.id}",
    )


def _notify_requester(db: Session, request: OffRequest, actor: User, action: str) -> None:
    employee = db.get(Employee, request.employee_id)
    target_user_id = request.requester_user_id or (employee.user_id if employee else None)
    if target_user_id is None:
        return
    request_label = REQUEST_TYPE_LABELS.get(request.request_type, "Yêu cầu")
    messages = {
        "APPROVE": (f"{request_label} đã được duyệt", f"{request_label} {_format_request_period(request)} của bạn đã được duyệt."),
        "REJECT": (f"{request_label} bị từ chối", f"{request_label} {_format_request_period(request)} của bạn đã bị từ chối."),
        "REQUEST_INFO": ("Yêu cầu bổ sung thông tin", f"Manager yêu cầu bạn bổ sung thông tin cho {request_label} {_format_request_period(request)}."),
    }
    title, message = messages[action]
    dispatch_notification(
        db,
        category=TIME_OFF,
        event_type=f"TIME_OFF_{action}",
        title=title,
        message=message,
        target_user_id=target_user_id,
        actor_user_id=actor.id,
        resource_type="TIME_OFF_REQUEST",
        resource_id=request.id,
        action_url=f"/time-off/requests/{request.id}",
    )


@router.get("/bootstrap")
def time_off_bootstrap(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = _current_employee(db, current_user)
    department = _employee_department(db, employee) if employee else None
    approver_options = _selectable_approvers(db, employee) if employee else []
    approver = approver_options[0] if approver_options else None
    handover_candidates = (
        db.query(Employee)
        .filter(Employee.is_active.is_(True), Employee.id != employee.id)
        .order_by(Employee.full_name.asc())
        .all()
        if employee
        else []
    )
    pending_count = (
        db.query(func.count(OffRequest.id))
        .filter(
            OffRequest.approver_user_id == current_user.id,
            OffRequest.status == PENDING_MANAGER,
        )
        .scalar()
        or 0
    )
    departments = db.query(Department).order_by(Department.name.asc()).all()
    return {
        "employee": (
            {
                "id": employee.id,
                "full_name": employee.full_name,
                "employee_code": employee.employee_code or employee.machine_employee_id,
                "department_id": department.id if department else employee.department_id,
                "department_name": department.name if department else employee.department_name,
            }
            if employee
            else None
        ),
        "manager": (
            {
                "user_id": approver.user.id,
                "employee_id": approver.employee.id if approver.employee else None,
                "full_name": approver.employee.full_name if approver.employee else approver.user.username,
                "source": approver.source,
            }
            if approver
            else None
        ),
        "approver_options": [
            {
                "user_id": item.user.id,
                "employee_id": item.employee.id if item.employee else None,
                "full_name": item.employee.full_name if item.employee else item.user.username,
                "source": item.source,
                "is_default": bool(approver and item.user.id == approver.user.id),
            }
            for item in approver_options
        ],
        "can_submit": bool(employee and department and approver),
        "pending_approval_count": pending_count,
        "handover_candidates": [
            {
                "id": item.id,
                "full_name": item.full_name,
                "department_name": item.department_name,
            }
            for item in handover_candidates
        ],
        "departments": [{"id": item.id, "name": item.name} for item in departments],
        "request_types": [
            {"value": key, "label": REQUEST_TYPE_LABELS[key]}
            for key in (LEAVE_REQUEST, WORK_FROM_HOME_REQUEST, BUSINESS_TRAVEL_REQUEST)
        ],
        "leave_balance": _leave_balance(db, employee) if employee else None,
    }


@router.post("/attachments")
async def stage_time_off_attachments(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stage private files before a request is submitted.

    A staged record is owned by the logged-in user and can only be attached to
    that user's request. This prevents trusting file identifiers from the UI.
    """
    if not files or len(files) > MAX_TIME_OFF_ATTACHMENTS:
        raise HTTPException(status_code=422, detail=f"Chỉ được tải lên từ 1 đến {MAX_TIME_OFF_ATTACHMENTS} file mỗi lần.")

    TIME_OFF_ATTACHMENT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    attachments: list[OffRequestAttachment] = []
    try:
        for upload in files:
            original_name = Path(upload.filename or "").name
            suffix = Path(original_name).suffix.lower()
            if not original_name or suffix not in TIME_OFF_ATTACHMENT_EXTENSIONS:
                allowed = ", ".join(sorted(TIME_OFF_ATTACHMENT_EXTENSIONS))
                raise HTTPException(status_code=422, detail=f"Định dạng file không được hỗ trợ. Cho phép: {allowed}")

            stored_filename = f"{uuid4().hex}{suffix}"
            destination = TIME_OFF_ATTACHMENT_DIRECTORY / stored_filename
            size_bytes = 0
            try:
                with destination.open("xb") as target:
                    while chunk := await upload.read(1024 * 1024):
                        size_bytes += len(chunk)
                        if size_bytes > MAX_TIME_OFF_ATTACHMENT_BYTES:
                            raise HTTPException(status_code=413, detail="Mỗi file đính kèm không được vượt quá 100 MB.")
                        target.write(chunk)
            except Exception:
                destination.unlink(missing_ok=True)
                raise
            finally:
                await upload.close()

            if size_bytes == 0:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=422, detail="Không thể tải lên file trống.")

            saved_paths.append(destination)
            attachment = OffRequestAttachment(
                uploaded_by_user_id=current_user.id,
                original_filename=original_name,
                stored_filename=stored_filename,
                content_type=upload.content_type or "application/octet-stream",
                size_bytes=size_bytes,
            )
            db.add(attachment)
            attachments.append(attachment)
        db.flush()
        for attachment in attachments:
            record_audit(
                db,
                actor=current_user,
                action="TIME_OFF_ATTACHMENT_STAGED",
                resource_type="TIME_OFF_ATTACHMENT",
                resource_id=attachment.id,
                summary=f"Tải file đính kèm cho Time Off: {attachment.original_filename}",
            )
        db.commit()
    except Exception:
        db.rollback()
        for saved_path in saved_paths:
            saved_path.unlink(missing_ok=True)
        raise

    for attachment in attachments:
        db.refresh(attachment)
    return {"items": [_serialize_attachment(attachment, staged=True) for attachment in attachments]}


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_staged_time_off_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attachment = (
        db.query(OffRequestAttachment)
        .filter(
            OffRequestAttachment.id == attachment_id,
            OffRequestAttachment.uploaded_by_user_id == current_user.id,
            OffRequestAttachment.request_id.is_(None),
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Không tìm thấy file đính kèm có thể gỡ.")
    path = TIME_OFF_ATTACHMENT_DIRECTORY / attachment.stored_filename
    db.delete(attachment)
    db.commit()
    path.unlink(missing_ok=True)
    return None


@router.get("/requests/{request_id}/attachments/{attachment_id}/download")
def download_time_off_attachment(
    request_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = db.get(OffRequest, request_id)
    viewer_employee = _current_employee(db, current_user)
    if not request or not _request_viewer_can_access_attachment(request, current_user, viewer_employee):
        raise HTTPException(status_code=404, detail="Không tìm thấy file đính kèm.")
    attachment = (
        db.query(OffRequestAttachment)
        .filter(OffRequestAttachment.id == attachment_id, OffRequestAttachment.request_id == request.id)
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Không tìm thấy file đính kèm.")
    path = TIME_OFF_ATTACHMENT_DIRECTORY / attachment.stored_filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File đính kèm không còn trên máy chủ.")
    return FileResponse(
        path,
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.original_filename,
        content_disposition_type="attachment",
    )


@router.post("/requests", status_code=status.HTTP_201_CREATED)
def submit_time_off_request(
    payload: TimeOffRequestPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = _require_current_employee(db, current_user)
    department = _employee_department(db, employee)
    if not department:
        raise HTTPException(status_code=409, detail="Hồ sơ nhân viên chưa được gán phòng ban hợp lệ.")
    approver = _resolve_selected_approver(db, employee, payload.approver_user_id)
    if not approver:
        raise HTTPException(status_code=409, detail="Phòng ban chưa có Manager hoặc fallback approver có tài khoản đăng nhập.")
    attachments = _resolve_staged_attachments(
        db,
        uploader_user_id=current_user.id,
        attachment_ids=payload.attachment_ids,
    )
    _validate_business_travel_payload(payload, attachment_count=len(attachments))
    time_range = _normalize_time_range(payload)
    if payload.request_type == LEAVE_REQUEST:
        _ensure_leave_request_balance(db, employee, time_range.total_days)
    _ensure_no_overlap(
        db,
        employee_id=employee.id,
        start_at=time_range.start_at,
        end_at=time_range.end_at,
    )
    handover = _validate_handover_employee(db, employee, payload.handover_employee_id)
    request = OffRequest(
        employee_id=employee.id,
        requester_user_id=current_user.id,
        department_id=department.id,
        approver_user_id=approver.user.id,
        approver_employee_id=approver.employee.id if approver.employee else None,
        request_type=payload.request_type,
        start_date=time_range.start_date,
        end_date=time_range.end_date,
        start_at=time_range.start_at,
        end_at=time_range.end_at,
        total_days=time_range.total_days,
        day_part=time_range.day_part,
        reason=payload.reason.strip(),
        handover_employee_id=handover.id if handover else None,
        handover_notes=(payload.handover_notes or "").strip() or None,
        business_travel_location=(payload.business_travel_location or "").strip() or None,
        business_travel_policy_acknowledged=(
            payload.business_travel_policy_acknowledged
            if payload.request_type == BUSINESS_TRAVEL_REQUEST
            else False
        ),
        status=PENDING_MANAGER,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(request)
    db.flush()
    for attachment in attachments:
        attachment.request_id = request.id
    db.add(
        ApprovalAction(
            request_id=request.id,
            actor_user_id=current_user.id,
            actor_employee_id=employee.id,
            action="SUBMIT",
            from_status="DRAFT",
            to_status=PENDING_MANAGER,
        )
    )
    _notify_approver(db, request, employee, department, approver)
    record_audit(
        db,
        actor=current_user,
        action="TIME_OFF_SUBMIT",
        resource_type="TIME_OFF_REQUEST",
        resource_id=request.id,
        summary=f"{employee.full_name} gửi đơn nghỉ {_format_request_period(request)}",
        after={
            "status": PENDING_MANAGER,
            "approver_user_id": approver.user.id,
            "request_type": payload.request_type,
        },
    )
    db.commit()
    db.refresh(request)
    return _serialize_request(
        db,
        request,
        viewer=current_user,
        viewer_employee=employee,
        include_private=True,
        include_actions=True,
    )


@router.put("/requests/{request_id}")
def resubmit_time_off_request(
    request_id: int,
    payload: TimeOffRequestPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = _require_current_employee(db, current_user)
    request = db.get(OffRequest, request_id)
    if not request or not _is_owner(request, current_user, employee):
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn nghỉ.")
    if _canonical_status(request.status) != MORE_INFO_REQUIRED:
        raise HTTPException(status_code=409, detail="Chỉ đơn đang yêu cầu bổ sung thông tin mới được cập nhật.")
    department = _employee_department(db, employee)
    approver = _resolve_selected_approver(db, employee, payload.approver_user_id)
    if not department or not approver:
        raise HTTPException(status_code=409, detail="Không thể xác định Manager hiện tại cho đơn nghỉ.")
    attachments = _resolve_staged_attachments(
        db,
        uploader_user_id=current_user.id,
        attachment_ids=payload.attachment_ids,
    )
    existing_attachment_count = _attached_file_count(db, request.id)
    if existing_attachment_count + len(attachments) > MAX_TIME_OFF_ATTACHMENTS:
        raise HTTPException(status_code=422, detail=f"Chỉ được đính kèm tối đa {MAX_TIME_OFF_ATTACHMENTS} file.")
    _validate_business_travel_payload(
        payload,
        attachment_count=existing_attachment_count + len(attachments),
    )
    time_range = _normalize_time_range(payload)
    if payload.request_type == LEAVE_REQUEST:
        _ensure_leave_request_balance(
            db,
            employee,
            time_range.total_days,
            exclude_request_id=request.id,
        )
    _ensure_no_overlap(
        db,
        employee_id=employee.id,
        start_at=time_range.start_at,
        end_at=time_range.end_at,
        exclude_request_id=request.id,
    )
    handover = _validate_handover_employee(db, employee, payload.handover_employee_id)
    before = {
        "status": request.status,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "start_at": request.start_at,
        "end_at": request.end_at,
        "day_part": request.day_part,
    }
    previous_status = _canonical_status(request.status)
    request.department_id = department.id
    request.approver_user_id = approver.user.id
    request.approver_employee_id = approver.employee.id if approver.employee else None
    request.request_type = payload.request_type
    request.start_date = time_range.start_date
    request.end_date = time_range.end_date
    request.start_at = time_range.start_at
    request.end_at = time_range.end_at
    request.total_days = time_range.total_days
    request.day_part = time_range.day_part
    request.reason = payload.reason.strip()
    request.handover_employee_id = handover.id if handover else None
    request.handover_notes = (payload.handover_notes or "").strip() or None
    request.business_travel_location = (payload.business_travel_location or "").strip() or None
    request.business_travel_policy_acknowledged = (
        payload.business_travel_policy_acknowledged
        if payload.request_type == BUSINESS_TRAVEL_REQUEST
        else False
    )
    request.manager_comment = None
    request.status = PENDING_MANAGER
    request.submitted_at = datetime.now(timezone.utc)
    for attachment in attachments:
        attachment.request_id = request.id
    db.add(
        ApprovalAction(
            request_id=request.id,
            actor_user_id=current_user.id,
            actor_employee_id=employee.id,
            action="RESUBMIT",
            from_status=previous_status,
            to_status=PENDING_MANAGER,
        )
    )
    _notify_approver(db, request, employee, department, approver, resubmitted=True)
    record_audit(
        db,
        actor=current_user,
        action="TIME_OFF_RESUBMIT",
        resource_type="TIME_OFF_REQUEST",
        resource_id=request.id,
        summary=f"{employee.full_name} bổ sung và gửi lại đơn nghỉ",
        before=before,
        after={"status": PENDING_MANAGER, "approver_user_id": approver.user.id},
    )
    db.commit()
    db.refresh(request)
    return _serialize_request(
        db,
        request,
        viewer=current_user,
        viewer_employee=employee,
        include_private=True,
        include_actions=True,
    )


@router.get("/requests/mine")
def my_time_off_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = _require_current_employee(db, current_user)
    items = (
        db.query(OffRequest)
        .filter(OffRequest.employee_id == employee.id)
        .order_by(OffRequest.created_at.desc(), OffRequest.id.desc())
        .all()
    )
    return [
        _serialize_request(
            db,
            item,
            viewer=current_user,
            viewer_employee=employee,
            include_private=True,
        )
        for item in items
    ]


@router.get("/requests/pending")
def pending_my_approval(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = _current_employee(db, current_user)
    items = (
        db.query(OffRequest)
        .filter(
            OffRequest.approver_user_id == current_user.id,
            OffRequest.status == PENDING_MANAGER,
        )
        .order_by(OffRequest.submitted_at.asc(), OffRequest.id.asc())
        .all()
    )
    return [
        _serialize_request(
            db,
            item,
            viewer=current_user,
            viewer_employee=employee,
            include_private=True,
        )
        for item in items
        if not _is_owner(item, current_user, employee)
    ]


@router.get("/requests/{request_id}")
def get_time_off_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = _current_employee(db, current_user)
    request = db.get(OffRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn nghỉ.")
    own = _is_owner(request, current_user, employee)
    assigned = request.approver_user_id == current_user.id and not own
    it_schedule_editor = _is_it_schedule_editor(current_user)
    is_shared_calendar_request = _canonical_status(request.status) in {APPROVED, PENDING_MANAGER}
    if not own and not assigned and not is_shared_calendar_request and not it_schedule_editor:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn nghỉ.")
    return _serialize_request(
        db,
        request,
        viewer=current_user,
        viewer_employee=employee,
        include_private=own or assigned or it_schedule_editor,
        include_actions=own or assigned or it_schedule_editor,
    )


@router.put("/requests/{request_id}/schedule")
def update_time_off_request_schedule(
    request_id: int,
    payload: TimeOffScheduleUpdatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _is_it_schedule_editor(current_user):
        raise HTTPException(status_code=403, detail="Chỉ IT_ADMIN được phép chỉnh ngày và giờ nghỉ.")

    request = db.query(OffRequest).filter(OffRequest.id == request_id).with_for_update().first()
    if not request:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn nghỉ.")

    time_range = _normalize_datetime_range(payload.start_at, payload.end_at)
    employee = db.query(Employee).filter(Employee.id == request.employee_id).with_for_update().first()
    if request.request_type == LEAVE_REQUEST and employee:
        _ensure_leave_request_balance(
            db,
            employee,
            time_range.total_days,
            exclude_request_id=request.id,
        )
    _ensure_no_overlap(
        db,
        employee_id=request.employee_id,
        start_at=time_range.start_at,
        end_at=time_range.end_at,
        exclude_request_id=request.id,
    )
    before = {
        "start_date": request.start_date,
        "end_date": request.end_date,
        "start_at": request.start_at,
        "end_at": request.end_at,
        "total_days": request.total_days,
        "day_part": request.day_part,
    }
    request.start_date = time_range.start_date
    request.end_date = time_range.end_date
    request.start_at = time_range.start_at
    request.end_at = time_range.end_at
    request.total_days = time_range.total_days
    request.day_part = time_range.day_part
    actor_employee = _current_employee(db, current_user)
    current_status = _canonical_status(request.status)
    db.add(
        ApprovalAction(
            request_id=request.id,
            actor_user_id=current_user.id,
            actor_employee_id=actor_employee.id if actor_employee else None,
            action="IT_ADMIN_UPDATE_SCHEDULE",
            from_status=current_status,
            to_status=current_status,
            comment="IT_ADMIN updated leave schedule.",
        )
    )
    record_audit(
        db,
        actor=current_user,
        action="TIME_OFF_IT_ADMIN_UPDATE_SCHEDULE",
        resource_type="TIME_OFF_REQUEST",
        resource_id=request.id,
        summary=f"IT_ADMIN chỉnh thời gian nghỉ cho {employee.full_name if employee else f'nhân viên #{request.employee_id}'}",
        before=before,
        after={
            "start_date": request.start_date,
            "end_date": request.end_date,
            "start_at": request.start_at,
            "end_at": request.end_at,
            "total_days": request.total_days,
            "day_part": request.day_part,
        },
    )
    db.commit()
    db.refresh(request)
    return _serialize_request(
        db,
        request,
        viewer=current_user,
        viewer_employee=actor_employee,
        include_private=True,
        include_actions=True,
    )


@router.post("/requests/{request_id}/actions")
def act_on_time_off_request(
    request_id: int,
    payload: TimeOffActionPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = db.query(OffRequest).filter(OffRequest.id == request_id).with_for_update().first()
    if not request or request.approver_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn thuộc phạm vi duyệt của bạn.")
    actor_employee = _current_employee(db, current_user)
    if _is_owner(request, current_user, actor_employee):
        raise HTTPException(status_code=403, detail="Bạn không thể tự duyệt đơn nghỉ của chính mình.")
    if _canonical_status(request.status) != PENDING_MANAGER:
        raise HTTPException(status_code=409, detail="Đơn nghỉ không còn ở trạng thái chờ Manager xử lý.")
    comment = (payload.comment or "").strip()
    if payload.action in {"REJECT", "REQUEST_INFO"} and not comment:
        raise HTTPException(status_code=422, detail="Vui lòng nhập lý do hoặc nội dung cần bổ sung.")
    next_status = {
        "APPROVE": APPROVED,
        "REJECT": REJECTED,
        "REQUEST_INFO": MORE_INFO_REQUIRED,
    }[payload.action]
    previous_status = _canonical_status(request.status)
    if payload.action == "APPROVE" and request.request_type == LEAVE_REQUEST:
        employee = db.query(Employee).filter(Employee.id == request.employee_id).with_for_update().first()
        if employee:
            # The request itself is already counted as a reservation. A
            # negative remainder can only occur if another request/master
            # balance changed after it was submitted.
            _ensure_leave_request_balance(db, employee, 0)
    request.status = next_status
    request.manager_comment = comment or None
    if payload.action == "APPROVE":
        request.approved_at = datetime.now(timezone.utc)
        request.approved_by_user_id = actor_employee.id if actor_employee else None
    db.add(
        ApprovalAction(
            request_id=request.id,
            actor_user_id=current_user.id,
            actor_employee_id=actor_employee.id if actor_employee else None,
            action=payload.action,
            from_status=previous_status,
            to_status=next_status,
            comment=comment or None,
        )
    )
    _notify_requester(db, request, current_user, payload.action)
    record_audit(
        db,
        actor=current_user,
        action=f"TIME_OFF_{payload.action}",
        resource_type="TIME_OFF_REQUEST",
        resource_id=request.id,
        summary=f"Xử lý đơn nghỉ #{request.id}: {previous_status} → {next_status}",
        before={"status": previous_status},
        after={"status": next_status, "comment": comment or None},
    )
    db.commit()
    db.refresh(request)
    return _serialize_request(
        db,
        request,
        viewer=current_user,
        viewer_employee=actor_employee,
        include_private=True,
        include_actions=True,
    )


@router.get("/calendar")
def time_off_calendar(
    start_date: date = Query(...),
    end_date: date = Query(...),
    status_filter: str | None = Query(default=None, alias="status"),
    department_id: int | None = Query(default=None),
    employee_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="Khoảng lịch không hợp lệ.")
    if (end_date - start_date).days > 370:
        raise HTTPException(status_code=422, detail="Khoảng lịch tối đa là 370 ngày.")
    employee = _current_employee(db, current_user)
    it_schedule_editor = _is_it_schedule_editor(current_user)
    # Approved requests and newly submitted requests are visible in the shared
    # calendar. Sensitive fields still remain private unless the viewer owns
    # the request, is its assigned approver, or is IT_ADMIN.
    visible = [
        func.lower(OffRequest.status).in_(
            {"approved", "approve", "pending_manager", "pending", "submitted", "under_review", "under review"}
        )
    ]
    if employee and not it_schedule_editor:
        visible.append(OffRequest.employee_id == employee.id)
    if not it_schedule_editor:
        visible.append(OffRequest.approver_user_id == current_user.id)
    query = db.query(OffRequest).filter(
        OffRequest.start_date <= end_date,
        OffRequest.end_date >= start_date,
    )
    if not it_schedule_editor:
        query = query.filter(or_(*visible))
    if department_id is not None:
        query = query.filter(OffRequest.department_id == department_id)
    if employee_id is not None:
        query = query.filter(OffRequest.employee_id == employee_id)
    requested_status = _canonical_status(status_filter) if status_filter else None
    items = query.order_by(OffRequest.start_date.asc(), OffRequest.id.asc()).all()
    events = []
    for item in items:
        canonical = _canonical_status(item.status)
        if requested_status and canonical != requested_status:
            continue
        own = _is_owner(item, current_user, employee)
        assigned = item.approver_user_id == current_user.id and not own
        # Shared Calendar shows Approved and pending Manager review. Other
        # non-final states remain visible only to their owner or approver.
        if canonical not in {APPROVED, PENDING_MANAGER} and not own and not assigned and not it_schedule_editor:
            continue
        serialized = _serialize_request(
            db,
            item,
            viewer=current_user,
            viewer_employee=employee,
            include_private=own or assigned or it_schedule_editor,
        )
        events.append(serialized)
    return {"start_date": start_date, "end_date": end_date, "events": events}
