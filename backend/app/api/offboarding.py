from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
import shutil
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_hr_manager_user
from app.api.employees import UPLOAD_DIRECTORY
from app.core.roles import HR_MANAGER_ROLES
from app.models.employee import Employee
from app.models.offboarding import OffboardingAction, OffboardingAttachment, OffboardingFormVersion, OffboardingRequest
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.notification_service import HR, add_notification

router = APIRouter(prefix="/api/offboarding", tags=["offboarding"])

ALLOWED_FIELD_TYPES = {"text", "textarea", "email", "phone", "date", "select", "multiselect", "number", "file"}
CORE_REQUIRED_KEYS = {"full_name", "email", "reason", "desired_last_working_date"}
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_FILES_PER_SUBMISSION = 10
ALLOWED_FILE_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx"}

DEFAULT_FIELDS: list[dict[str, Any]] = [
    {"key": "full_name", "label": "Họ và tên", "type": "text", "required": True, "active": True, "section": "Thông tin nhân viên"},
    {"key": "email", "label": "Email liên hệ", "type": "email", "required": True, "active": True, "section": "Thông tin nhân viên"},
    {"key": "employee_code", "label": "Mã nhân viên", "type": "text", "required": False, "active": True, "section": "Thông tin nhân viên"},
    {"key": "position", "label": "Chức vụ", "type": "text", "required": True, "active": True, "section": "Thông tin công việc"},
    {"key": "department", "label": "Phòng ban", "type": "text", "required": True, "active": True, "section": "Thông tin công việc"},
    {"key": "request_date", "label": "Ngày làm đơn", "type": "date", "required": True, "active": True, "section": "Thông tin nghỉ việc"},
    {"key": "notice_period_days", "label": "Thời hạn báo trước", "type": "select", "required": True, "active": True, "section": "Thông tin nghỉ việc", "options": [{"value": "30", "label": "30 ngày"}, {"value": "45", "label": "45 ngày"}]},
    {"key": "desired_last_working_date", "label": "Ngày làm việc cuối cùng mong muốn", "type": "date", "required": True, "active": True, "section": "Thông tin nghỉ việc"},
    {"key": "reason", "label": "Lý do nghỉ việc", "type": "textarea", "required": True, "active": True, "section": "Thông tin nghỉ việc"},
    {"key": "personal_opinion", "label": "Ý kiến cá nhân dành cho Công ty", "type": "textarea", "required": True, "active": True, "section": "Ý kiến & bàn giao"},
    {"key": "direct_manager_name", "label": "Quản lý trực tiếp nhận bàn giao", "type": "text", "required": False, "active": True, "section": "Ý kiến & bàn giao"},
    {"key": "no_grievance_confirmed", "label": "Xác nhận không còn khiếu nại", "type": "select", "required": True, "active": True, "section": "Cam kết", "options": [{"value": "YES", "label": "Tôi xác nhận"}]},
    {"key": "handover_commitment_confirmed", "label": "Cam kết hoàn tất bàn giao", "type": "select", "required": True, "active": True, "section": "Cam kết", "options": [{"value": "YES", "label": "Tôi cam kết"}]},
    {"key": "supporting_documents", "label": "Tài liệu đính kèm", "type": "file", "required": False, "active": True, "section": "Tài liệu", "max_files": 5},
]


class FormConfigurationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=3000)
    success_message: str = Field(min_length=3, max_length=2000)
    fields: list[dict[str, Any]] = Field(min_length=1, max_length=80)


class ReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=3, max_length=3000)


class ApprovePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=3000)
    employee_id: int | None = None
    confirmed_last_working_date: date | None = None
    last_pay_date: date | None = None


def _json_load(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def _serialize_form(row: OffboardingFormVersion) -> dict[str, Any]:
    return {"id": row.id, "version_number": row.version_number, "status": row.status, "title": row.title, "description": row.description, "success_message": row.success_message, "fields": _json_load(row.fields_json, []), "updated_at": row.updated_at, "published_at": row.published_at}


def _ensure_default_forms(db: Session) -> tuple[OffboardingFormVersion, OffboardingFormVersion]:
    published = db.query(OffboardingFormVersion).filter(OffboardingFormVersion.status == "PUBLISHED").order_by(OffboardingFormVersion.version_number.desc()).first()
    draft = db.query(OffboardingFormVersion).filter(OffboardingFormVersion.status == "DRAFT").order_by(OffboardingFormVersion.version_number.desc()).first()
    if not published:
        published = OffboardingFormVersion(version_number=1, status="PUBLISHED", title="Đơn xin nghỉ việc", description="Vui lòng hoàn thành biểu mẫu. Bộ phận Nhân sự sẽ tiếp nhận và liên hệ khi cần bổ sung thông tin.", success_message="SEALINK đã nhận đơn xin nghỉ việc của bạn. Vui lòng lưu mã theo dõi hồ sơ.", fields_json=json.dumps(DEFAULT_FIELDS, ensure_ascii=False), published_at=datetime.now(timezone.utc))
        db.add(published); db.flush()
    if not draft:
        draft = OffboardingFormVersion(version_number=published.version_number + 1, status="DRAFT", title=published.title, description=published.description, success_message=published.success_message, fields_json=published.fields_json)
        db.add(draft)
    db.commit(); db.refresh(published); db.refresh(draft)
    return published, draft


def _validate_configuration(payload: FormConfigurationPayload) -> list[dict[str, Any]]:
    keys: set[str] = set(); cleaned: list[dict[str, Any]] = []
    for index, item in enumerate(payload.fields):
        key = re.sub(r"[^a-z0-9_]+", "_", str(item.get("key") or "").strip().lower()).strip("_")
        label = str(item.get("label") or "").strip(); field_type = str(item.get("type") or "text").strip().lower()
        if not key or not label: raise HTTPException(status_code=422, detail=f"Trường số {index + 1} thiếu mã hoặc nhãn.")
        if key in keys: raise HTTPException(status_code=422, detail=f"Mã trường bị trùng: {key}")
        if field_type not in ALLOWED_FIELD_TYPES: raise HTTPException(status_code=422, detail=f"Loại trường không hỗ trợ: {field_type}")
        keys.add(key); value = dict(item)
        value.update({"key": key, "label": label, "type": field_type, "active": bool(item.get("active", True)), "required": bool(item.get("required", False)), "order": index})
        if field_type in {"select", "multiselect"} and not isinstance(item.get("options"), list): raise HTTPException(status_code=422, detail=f"Trường {label} phải có lựa chọn.")
        cleaned.append(value)
    for key in CORE_REQUIRED_KEYS:
        field = next((item for item in cleaned if item["key"] == key), None)
        if not field or not field["active"] or not field["required"]: raise HTTPException(status_code=422, detail=f"Trường hệ thống {key} phải được bật và bắt buộc.")
    return cleaned


def _validate_submission(fields: list[dict[str, Any]], answers: dict[str, Any], file_keys: list[str]) -> None:
    if not isinstance(answers, dict): raise HTTPException(status_code=422, detail="Dữ liệu biểu mẫu không hợp lệ.")
    active = {str(field.get("key")): field for field in fields if field.get("active", True)}
    if set(answers) - set(active): raise HTTPException(status_code=422, detail="Biểu mẫu có trường không hợp lệ.")
    file_fields = {key: field for key, field in active.items() if field.get("type") == "file"}
    if set(file_keys) - set(file_fields): raise HTTPException(status_code=422, detail="Tệp đính kèm không thuộc trường hợp lệ.")
    for key, field in active.items():
        value = answers.get(key); empty = value is None or value == "" or value == []
        if field.get("required") and ((field.get("type") == "file" and key not in file_keys) or (field.get("type") != "file" and empty)): raise HTTPException(status_code=422, detail=f"Vui lòng nhập: {field.get('label')}")
        if not empty and field.get("type") == "email" and not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", str(value)): raise HTTPException(status_code=422, detail="Email không hợp lệ.")


def _parse_date(value: Any, fallback: date | None = None) -> date | None:
    if not value: return fallback
    try: return date.fromisoformat(str(value))
    except ValueError as error: raise HTTPException(status_code=422, detail=f"Ngày không hợp lệ: {value}") from error


def _serialize_submission(row: OffboardingRequest) -> dict[str, Any]:
    answers = _json_load(row.answers_json, {})
    fields = _json_load(row.form_version.fields_json, []) if row.form_version else []
    if not fields:
        fields = [field for field in DEFAULT_FIELDS if field["key"] != "supporting_documents"]
        answers = {
            "full_name": row.employee_name_snapshot, "email": row.email_snapshot or "",
            "employee_code": row.employee_code_snapshot or "", "position": row.position_snapshot or "",
            "department": row.department_snapshot or "", "request_date": str(row.request_date),
            "notice_period_days": str(row.notice_period_days), "desired_last_working_date": str(row.desired_last_working_date),
            "reason": row.reason, "personal_opinion": row.personal_opinion,
            "direct_manager_name": row.manager_name_snapshot or "",
            "no_grievance_confirmed": "YES" if row.no_grievance_confirmed else "NO",
            "handover_commitment_confirmed": "YES" if row.handover_commitment_confirmed else "NO",
        }
    return {
        "id": row.id, "public_id": row.public_id, "status": row.status, "full_name": row.employee_name_snapshot,
        "email": row.email_snapshot, "employee_id": row.employee_id, "employee_code": row.employee_code_snapshot,
        "position": row.position_snapshot, "department": row.department_snapshot, "request_date": row.request_date,
        "desired_last_working_date": row.desired_last_working_date, "confirmed_last_working_date": row.confirmed_last_working_date,
        "last_pay_date": row.last_pay_date, "review_note": row.review_note, "submitted_at": row.submitted_at,
        "updated_at": row.updated_at, "reviewed_at": row.reviewed_at, "answers": answers,
        "fields": fields,
        "form_version": row.form_version.version_number if row.form_version else None,
        "attachments": [{"id": item.id, "field_key": item.field_key, "original_name": item.original_name, "size_bytes": item.size_bytes, "download_url": f"/api/offboarding/admin/submissions/{row.id}/attachments/{item.id}"} for item in row.attachments],
    }


def _submission_or_404(db: Session, submission_id: int) -> OffboardingRequest:
    row = db.query(OffboardingRequest).options(joinedload(OffboardingRequest.form_version), joinedload(OffboardingRequest.attachments)).filter(OffboardingRequest.id == submission_id).first()
    if not row: raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ nghỉ việc.")
    return row


def _record_action(db: Session, row: OffboardingRequest, actor: User | None, action: str, target: str, note: str | None = None) -> None:
    previous = row.status
    db.add(OffboardingAction(request_id=row.id, actor_user_id=actor.id if actor else None, action=action, from_status=previous, to_status=target, note=note))
    row.status = target


@router.get("/form")
def get_public_form(db: Session = Depends(get_db)) -> dict[str, Any]:
    published, _ = _ensure_default_forms(db); return _serialize_form(published)


@router.post("/submissions", status_code=status.HTTP_201_CREATED)
async def create_submission(answers_json: str = Form(...), file_keys_json: str = Form(default="[]"), files: list[UploadFile] | None = File(default=None), website: str = Form(default=""), db: Session = Depends(get_db)) -> dict[str, Any]:
    if website: raise HTTPException(status_code=400, detail="Yêu cầu không hợp lệ.")
    published, _ = _ensure_default_forms(db); answers = _json_load(answers_json, None); file_keys = _json_load(file_keys_json, []); upload_files = files or []
    if not isinstance(file_keys, list) or len(file_keys) != len(upload_files) or len(upload_files) > MAX_FILES_PER_SUBMISSION: raise HTTPException(status_code=422, detail="Thông tin tệp đính kèm không khớp.")
    _validate_submission(_json_load(published.fields_json, []), answers, [str(key) for key in file_keys])
    desired_date = _parse_date(answers.get("desired_last_working_date"))
    if desired_date is None: raise HTTPException(status_code=422, detail="Vui lòng nhập ngày làm việc cuối cùng mong muốn.")
    try: notice_days = int(answers.get("notice_period_days") or 30)
    except (TypeError, ValueError) as error: raise HTTPException(status_code=422, detail="Thời hạn báo trước không hợp lệ.") from error
    row = OffboardingRequest(public_id=str(uuid4()), form_version_id=published.id, status="NEW", request_date=_parse_date(answers.get("request_date"), date.today()) or date.today(), notice_period_days=notice_days, desired_last_working_date=desired_date, reason=str(answers.get("reason") or "").strip(), personal_opinion=str(answers.get("personal_opinion") or "").strip(), no_grievance_confirmed=str(answers.get("no_grievance_confirmed") or "").upper() == "YES", handover_commitment_confirmed=str(answers.get("handover_commitment_confirmed") or "").upper() == "YES", employee_name_snapshot=str(answers.get("full_name") or "").strip(), employee_code_snapshot=str(answers.get("employee_code") or "").strip() or None, position_snapshot=str(answers.get("position") or "").strip() or None, department_snapshot=str(answers.get("department") or "").strip() or None, manager_name_snapshot=str(answers.get("direct_manager_name") or "").strip() or None, email_snapshot=str(answers.get("email") or "").strip().lower(), answers_json=json.dumps(answers, ensure_ascii=False))
    db.add(row); db.flush(); folder = UPLOAD_DIRECTORY / "offboarding" / row.public_id; folder.mkdir(parents=True, exist_ok=True)
    try:
        for field_key, upload in zip(file_keys, upload_files):
            suffix = Path(upload.filename or "").suffix.lower()
            if suffix not in ALLOWED_FILE_SUFFIXES: raise HTTPException(status_code=422, detail=f"Định dạng tệp không hỗ trợ: {upload.filename}")
            content = await upload.read(MAX_FILE_BYTES + 1)
            if len(content) > MAX_FILE_BYTES: raise HTTPException(status_code=422, detail=f"Tệp {upload.filename} vượt quá 15 MB.")
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(upload.filename or "file").name); target = folder / f"{uuid4().hex}_{safe_name}"; target.write_bytes(content)
            db.add(OffboardingAttachment(submission_id=row.id, field_key=str(field_key), original_name=Path(upload.filename or "file").name, stored_path=str(target.relative_to(UPLOAD_DIRECTORY)).replace("\\", "/"), content_type=upload.content_type, size_bytes=len(content)))
        _record_action(db, row, None, "SUBMIT", "NEW")
        for admin in db.query(User).filter(User.role.in_(tuple(HR_MANAGER_ROLES))).all(): add_notification(db, category=HR, event_type="OFFBOARDING_SUBMITTED", title="Có đơn nghỉ việc mới", message=f"{row.employee_name_snapshot} đã gửi đơn nghỉ việc.", target_user_id=admin.id, resource_type="OFFBOARDING_SUBMISSION", resource_id=row.id, action_url="/hr/offboarding" if admin.role == "HR_ADMIN" else "/admin/offboarding")
        db.commit()
    except Exception:
        db.rollback(); shutil.rmtree(folder, ignore_errors=True); raise
    return {"public_id": row.public_id, "status": row.status, "message": published.success_message}


@router.get("/submissions/{public_id}/status")
def public_submission_status(public_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.query(OffboardingRequest).filter(OffboardingRequest.public_id == public_id).first()
    if not row: raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ.")
    return {"public_id": row.public_id, "status": row.status, "review_note": row.review_note, "updated_at": row.updated_at}


@router.get("/admin/config")
def get_admin_configuration(db: Session = Depends(get_db), _: User = Depends(get_hr_manager_user)) -> dict[str, Any]:
    published, draft = _ensure_default_forms(db); return {"published": _serialize_form(published), "draft": _serialize_form(draft), "public_path": "/offboarding"}


@router.put("/admin/config")
def save_draft_configuration(payload: FormConfigurationPayload, db: Session = Depends(get_db), actor: User = Depends(get_hr_manager_user)) -> dict[str, Any]:
    _, draft = _ensure_default_forms(db); draft.title = payload.title.strip(); draft.description = payload.description.strip(); draft.success_message = payload.success_message.strip(); draft.fields_json = json.dumps(_validate_configuration(payload), ensure_ascii=False); draft.created_by_id = actor.id; db.commit(); db.refresh(draft); return _serialize_form(draft)


@router.post("/admin/config/publish")
def publish_configuration(payload: FormConfigurationPayload, db: Session = Depends(get_db), actor: User = Depends(get_hr_manager_user)) -> dict[str, Any]:
    current, draft = _ensure_default_forms(db); draft.title = payload.title.strip(); draft.description = payload.description.strip(); draft.success_message = payload.success_message.strip(); draft.fields_json = json.dumps(_validate_configuration(payload), ensure_ascii=False); draft.created_by_id = actor.id; current.status = "ARCHIVED"; draft.status = "PUBLISHED"; draft.published_at = datetime.now(timezone.utc); db.flush()
    next_draft = OffboardingFormVersion(version_number=draft.version_number + 1, status="DRAFT", title=draft.title, description=draft.description, success_message=draft.success_message, fields_json=draft.fields_json, created_by_id=actor.id); db.add(next_draft)
    record_audit(db, actor=actor, action="OFFBOARDING_FORM_PUBLISH", resource_type="OFFBOARDING_FORM", resource_id=draft.id, summary=f"Phát hành biểu mẫu offboarding phiên bản {draft.version_number}", after={"version": draft.version_number, "title": draft.title}); db.commit(); db.refresh(next_draft)
    return {"published": _serialize_form(draft), "draft": _serialize_form(next_draft)}


@router.get("/admin/submissions")
def list_submissions(submission_status: str | None = Query(default=None, alias="status"), db: Session = Depends(get_db), _: User = Depends(get_hr_manager_user)) -> list[dict[str, Any]]:
    query = db.query(OffboardingRequest).options(joinedload(OffboardingRequest.form_version), joinedload(OffboardingRequest.attachments))
    if submission_status: query = query.filter(OffboardingRequest.status == submission_status.upper())
    return [_serialize_submission(row) for row in query.order_by(OffboardingRequest.submitted_at.desc(), OffboardingRequest.id.desc()).all()]


@router.get("/admin/employees")
def employee_options(search: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_hr_manager_user)) -> list[dict[str, Any]]:
    query = db.query(Employee).filter(Employee.is_active.is_(True))
    if search:
        like = f"%{search.strip()}%"; query = query.filter(or_(Employee.full_name.ilike(like), Employee.employee_code.ilike(like), Employee.personal_email.ilike(like), Employee.company_email.ilike(like)))
    return [{"id": item.id, "full_name": item.full_name, "employee_code": item.employee_code, "personal_email": item.personal_email, "company_email": item.company_email} for item in query.order_by(Employee.full_name.asc()).limit(200).all()]


def _review(db: Session, row: OffboardingRequest, actor: User, target: str, action: str, note: str) -> dict[str, Any]:
    _record_action(db, row, actor, action, target, note); row.review_note = note; row.reviewer_id = actor.id; row.reviewed_at = datetime.now(timezone.utc); db.commit(); return _serialize_submission(_submission_or_404(db, row.id))


@router.post("/admin/submissions/{submission_id}/request-changes")
def request_changes(submission_id: int, payload: ReviewPayload, db: Session = Depends(get_db), actor: User = Depends(get_hr_manager_user)) -> dict[str, Any]: return _review(db, _submission_or_404(db, submission_id), actor, "NEEDS_INFO", "REQUEST_CHANGES", payload.note.strip())


@router.post("/admin/submissions/{submission_id}/reject")
def reject_submission(submission_id: int, payload: ReviewPayload, db: Session = Depends(get_db), actor: User = Depends(get_hr_manager_user)) -> dict[str, Any]: return _review(db, _submission_or_404(db, submission_id), actor, "REJECTED", "REJECT", payload.note.strip())


def _resolve_employee_for_approval(
    db: Session,
    row: OffboardingRequest,
    requested_employee_id: int | None,
) -> Employee | None:
    if requested_employee_id is not None:
        return db.get(Employee, requested_employee_id)

    code = (row.employee_code_snapshot or "").strip()
    if code:
        matches = db.query(Employee).filter(
            or_(Employee.machine_employee_id == code, Employee.employee_code == code)
        ).all()
        if len(matches) == 1:
            return matches[0]

    email = (row.email_snapshot or "").strip().lower()
    if email:
        matches = db.query(Employee).filter(
            or_(
                func.lower(Employee.personal_email) == email,
                func.lower(Employee.company_email) == email,
            )
        ).all()
        if len(matches) == 1:
            return matches[0]

    name = (row.employee_name_snapshot or "").strip().lower()
    if name:
        matches = db.query(Employee).filter(func.lower(Employee.full_name) == name).all()
        if len(matches) == 1:
            return matches[0]
    return None


@router.post("/admin/submissions/{submission_id}/approve")
def approve_submission(submission_id: int, payload: ApprovePayload, db: Session = Depends(get_db), actor: User = Depends(get_hr_manager_user)) -> dict[str, Any]:
    row = _submission_or_404(db, submission_id); employee = _resolve_employee_for_approval(db, row, payload.employee_id)
    if not employee: raise HTTPException(status_code=422, detail="Không thể tự đối chiếu nhân viên. Vui lòng chọn đúng nhân viên trước khi phê duyệt.")
    if employee: row.employee_id = employee.id; row.employee_code_snapshot = employee.employee_code
    row.confirmed_last_working_date = payload.confirmed_last_working_date or row.desired_last_working_date; row.last_pay_date = payload.last_pay_date
    if employee and row.confirmed_last_working_date:
        employee.is_active = False
        employee.status = "RESIGNED"
        employee.resignation_period = row.confirmed_last_working_date.strftime("%Y-%m")
        employee.last_working_date = row.confirmed_last_working_date
        employee.last_pay_date = row.last_pay_date
    _record_action(db, row, actor, "APPROVE", "APPROVED", payload.note); row.review_note = payload.note; row.reviewer_id = actor.id; row.reviewed_at = datetime.now(timezone.utc)
    record_audit(db, actor=actor, action="OFFBOARDING_APPROVE", resource_type="OFFBOARDING_SUBMISSION", resource_id=row.id, summary=f"Phê duyệt đơn nghỉ việc của {row.employee_name_snapshot}", after={"employee_id": row.employee_id, "employee_status": employee.status if employee else None, "last_working_date": str(row.confirmed_last_working_date), "last_pay_date": str(row.last_pay_date) if row.last_pay_date else None}); db.commit(); return _serialize_submission(_submission_or_404(db, row.id))


@router.get("/admin/submissions/{submission_id}/attachments/{attachment_id}")
def download_attachment(submission_id: int, attachment_id: int, db: Session = Depends(get_db), _: User = Depends(get_hr_manager_user)) -> FileResponse:
    attachment = db.query(OffboardingAttachment).filter(OffboardingAttachment.id == attachment_id, OffboardingAttachment.submission_id == submission_id).first()
    if not attachment: raise HTTPException(status_code=404, detail="Không tìm thấy tệp đính kèm.")
    path = UPLOAD_DIRECTORY / attachment.stored_path
    if not path.is_file(): raise HTTPException(status_code=404, detail="Tệp không còn tồn tại.")
    return FileResponse(path, filename=attachment.original_name, media_type=attachment.content_type)
