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
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_hr_manager_user
from app.api.employees import UPLOAD_DIRECTORY
from app.core.employee_type import FULLTIME, INTERN, PROBATION, TRAINEE
from app.core.roles import HR_MANAGER_ROLES
from app.models.department import Department
from app.models.employee import Employee
from app.models.onboarding import OnboardingAttachment, OnboardingFormVersion, OnboardingSubmission
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.notification_service import HR, actor_id, add_notification


router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

ALLOWED_FIELD_TYPES = {"text", "textarea", "email", "phone", "date", "select", "multiselect", "number", "file"}
CORE_REQUIRED_KEYS = {"full_name", "email", "application_type"}
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_FILES_PER_SUBMISSION = 10
ALLOWED_FILE_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx"}
PROCESSING_STATUSES = {
    "NEW", "NEEDS_INFO", "REJECTED", "INTERN", "TRAINEE", "PROBATION", "OFFICIAL", "PART_TIME", "DONE"
}


DEFAULT_FIELDS: list[dict[str, Any]] = [
    {"key": "full_name", "label": "Họ và tên", "type": "text", "required": True, "active": True, "section": "Thông tin cá nhân", "placeholder": "Nguyễn Văn A"},
    {"key": "english_name", "label": "Tên tiếng Anh", "type": "text", "required": True, "active": True, "section": "Thông tin cá nhân", "placeholder": "Ví dụ: Anna Nguyen"},
    {"key": "date_of_birth", "label": "Ngày sinh", "type": "date", "required": True, "active": True, "section": "Thông tin cá nhân"},
    {"key": "address", "label": "Địa chỉ hiện tại", "type": "textarea", "required": True, "active": True, "section": "Thông tin cá nhân"},
    {"key": "personal_phone", "label": "Số điện thoại cá nhân", "type": "phone", "required": True, "active": True, "section": "Thông tin liên hệ"},
    {"key": "company_extension", "label": "Số nội bộ công ty", "type": "text", "required": False, "active": True, "section": "Thông tin liên hệ"},
    {"key": "email", "label": "Email", "type": "email", "required": True, "active": True, "section": "Thông tin liên hệ"},
    {"key": "application_type", "label": "Loại ứng tuyển", "type": "select", "required": True, "active": True, "section": "Thông tin công việc", "options": [
        {"value": "INTERN", "label": "Thực tập"}, {"value": "TRAINEE", "label": "Học việc"},
        {"value": "PROBATION", "label": "Thử việc"}, {"value": "OFFICIAL", "label": "Chính thức"},
        {"value": "PART_TIME", "label": "Part-time"},
    ]},
    {"key": "position_applied", "label": "Vị trí ứng tuyển", "type": "text", "required": True, "active": True, "section": "Thông tin công việc"},
    {"key": "marital_status", "label": "Tình trạng hôn nhân", "type": "select", "required": True, "active": True, "section": "Thông tin bổ sung", "options": [
        {"value": "SINGLE", "label": "Độc thân"}, {"value": "MARRIED", "label": "Đã kết hôn"}, {"value": "OTHER", "label": "Khác"},
    ]},
    {"key": "health_status", "label": "Tình trạng sức khỏe", "type": "textarea", "required": True, "active": True, "section": "Thông tin bổ sung"},
    {"key": "bank_name", "label": "Ngân hàng", "type": "text", "required": True, "active": True, "section": "Thông tin ngân hàng"},
    {"key": "bank_account", "label": "Số tài khoản", "type": "text", "required": True, "active": True, "section": "Thông tin ngân hàng"},
    {"key": "identity_documents", "label": "CCCD/CMND hai mặt", "type": "file", "required": True, "active": True, "section": "Hồ sơ đính kèm", "description": "Tải mặt trước và mặt sau; hỗ trợ ảnh hoặc PDF, tối đa 15 MB/tệp.", "max_files": 2},
    {"key": "required_documents", "label": "Hồ sơ sẽ nộp cho công ty", "type": "multiselect", "required": True, "active": True, "section": "Hồ sơ đính kèm", "options": [
        {"value": "CV", "label": "CV"}, {"value": "DIPLOMA", "label": "Bằng cấp/chứng chỉ"},
        {"value": "HEALTH_CHECK", "label": "Giấy khám sức khỏe"}, {"value": "RESIDENCE", "label": "Thông tin cư trú"},
    ]},
    {"key": "company_notes", "label": "Ghi chú cho công ty", "type": "textarea", "required": False, "active": True, "section": "Thông tin bổ sung"},
    {"key": "office_days_per_week", "label": "Số ngày làm trực tiếp tại công ty mỗi tuần", "type": "number", "required": True, "active": True, "section": "Thông tin công việc", "min": 0, "max": 7},
    {"key": "intern_school", "label": "Trường đang theo học", "type": "text", "required": True, "active": True, "section": "Thông tin học tập", "visible_when": {"field": "application_type", "operator": "in", "values": ["INTERN"]}},
    {"key": "available_start_date", "label": "Ngày có thể bắt đầu", "type": "date", "required": True, "active": True, "section": "Thông tin công việc", "visible_when": {"field": "application_type", "operator": "in", "values": ["INTERN", "TRAINEE", "PROBATION", "OFFICIAL", "PART_TIME"]}},
]


class FormConfigurationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    success_message: str = Field(default="", max_length=5000)
    fields: list[dict[str, Any]] = Field(min_length=1, max_length=80)


class ReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=3, max_length=5000)


class StatusPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    note: str | None = Field(default=None, max_length=5000)


class ApprovePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    machine_employee_id: str = Field(min_length=1, max_length=50)
    department_id: int | None = None
    employee_code: str | None = Field(default=None, max_length=50)
    start_date: date | None = None


def _json_load(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _default_config_payload() -> dict[str, Any]:
    return {
        "title": "Thông tin Onboarding nhân viên mới",
        "description": "Chào mừng bạn đến với SEALINK. Vui lòng hoàn thành thông tin dưới đây để công ty chuẩn bị hồ sơ tiếp nhận.",
        "success_message": "SEALINK đã nhận hồ sơ. Vui lòng lưu mã theo dõi để kiểm tra khi công ty yêu cầu bổ sung.",
        "fields": DEFAULT_FIELDS,
    }


def _serialize_form(row: OnboardingFormVersion) -> dict[str, Any]:
    return {
        "id": row.id,
        "version_number": row.version_number,
        "status": row.status,
        "title": row.title,
        "description": row.description,
        "success_message": row.success_message,
        "fields": _json_load(row.fields_json, []),
        "updated_at": row.updated_at,
        "published_at": row.published_at,
    }


def _ensure_default_forms(db: Session) -> tuple[OnboardingFormVersion, OnboardingFormVersion]:
    published = db.query(OnboardingFormVersion).filter(OnboardingFormVersion.status == "PUBLISHED").order_by(OnboardingFormVersion.version_number.desc()).first()
    draft = db.query(OnboardingFormVersion).filter(OnboardingFormVersion.status == "DRAFT").order_by(OnboardingFormVersion.version_number.desc()).first()
    if published and draft:
        return published, draft
    config = _default_config_payload()
    if not published:
        published = OnboardingFormVersion(
            version_number=1,
            status="PUBLISHED",
            title=config["title"],
            description=config["description"],
            success_message=config["success_message"],
            fields_json=json.dumps(config["fields"], ensure_ascii=False),
            published_at=datetime.now(timezone.utc),
        )
        db.add(published)
        db.flush()
    if not draft:
        draft = OnboardingFormVersion(
            version_number=published.version_number + 1,
            status="DRAFT",
            title=published.title,
            description=published.description,
            success_message=published.success_message,
            fields_json=published.fields_json,
        )
        db.add(draft)
    db.commit()
    db.refresh(published)
    db.refresh(draft)
    return published, draft


def _validate_configuration(payload: FormConfigurationPayload) -> list[dict[str, Any]]:
    keys: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for index, item in enumerate(payload.fields):
        key = re.sub(r"[^a-z0-9_]+", "_", str(item.get("key") or "").strip().lower()).strip("_")
        label = str(item.get("label") or "").strip()
        field_type = str(item.get("type") or "text").strip().lower()
        if not key or not label:
            raise HTTPException(status_code=422, detail=f"Trường số {index + 1} thiếu mã hoặc nhãn.")
        if key in keys:
            raise HTTPException(status_code=422, detail=f"Mã trường bị trùng: {key}")
        if field_type not in ALLOWED_FIELD_TYPES:
            raise HTTPException(status_code=422, detail=f"Loại trường không hỗ trợ: {field_type}")
        keys.add(key)
        value = dict(item)
        value.update({"key": key, "label": label, "type": field_type, "active": bool(item.get("active", True)), "required": bool(item.get("required", False))})
        value["order"] = index
        if field_type in {"select", "multiselect"}:
            options = item.get("options") or []
            if not isinstance(options, list) or not options:
                raise HTTPException(status_code=422, detail=f"Trường {label} phải có lựa chọn.")
        cleaned.append(value)
    for key in CORE_REQUIRED_KEYS:
        field = next((item for item in cleaned if item["key"] == key), None)
        if not field or not field["active"] or not field["required"]:
            raise HTTPException(status_code=422, detail=f"Trường hệ thống {key} phải được bật và bắt buộc.")
    for field in cleaned:
        condition = field.get("visible_when")
        if not condition:
            continue
        if not isinstance(condition, dict):
            raise HTTPException(status_code=422, detail=f"Điều kiện của {field['label']} không hợp lệ.")
        source_key = str(condition.get("field") or "").strip()
        operator = str(condition.get("operator") or "in")
        values = condition.get("values") or []
        if source_key not in keys or source_key == field["key"]:
            raise HTTPException(status_code=422, detail=f"Trường điều kiện của {field['label']} không tồn tại.")
        if operator not in {"in", "not_in"} or not isinstance(values, list) or not values:
            raise HTTPException(status_code=422, detail=f"Giá trị điều kiện của {field['label']} không hợp lệ.")
        field["visible_when"] = {"field": source_key, "operator": operator, "values": [str(item) for item in values]}
    return cleaned


def _is_visible(field: dict[str, Any], answers: dict[str, Any]) -> bool:
    condition = field.get("visible_when")
    if not condition or not isinstance(condition, dict):
        return True
    source = answers.get(str(condition.get("field") or ""))
    values = condition.get("values") or []
    operator = condition.get("operator", "in")
    return (source in values) if operator == "in" else (source not in values)


def _validate_submission(fields: list[dict[str, Any]], answers: dict[str, Any], file_keys: list[str]) -> None:
    if not isinstance(answers, dict):
        raise HTTPException(status_code=422, detail="Dữ liệu biểu mẫu không hợp lệ.")
    active_keys = {str(field.get("key")) for field in fields if field.get("active", True)}
    file_fields = {
        str(field.get("key")): field
        for field in fields
        if field.get("active", True) and field.get("type") == "file" and _is_visible(field, answers)
    }
    unknown = set(answers) - active_keys
    if unknown:
        raise HTTPException(status_code=422, detail=f"Biểu mẫu có trường không hợp lệ: {', '.join(sorted(unknown))}")
    unknown_file_keys = set(file_keys) - set(file_fields)
    if unknown_file_keys:
        raise HTTPException(status_code=422, detail="Tệp đính kèm không thuộc trường đang hiển thị.")
    for key, field in file_fields.items():
        count = file_keys.count(key)
        max_files = max(1, min(int(field.get("max_files") or 1), MAX_FILES_PER_SUBMISSION))
        if count > max_files:
            raise HTTPException(status_code=422, detail=f"{field.get('label')} chỉ nhận tối đa {max_files} tệp.")
    for field in fields:
        if not field.get("active", True) or not _is_visible(field, answers):
            continue
        key = str(field.get("key"))
        value = answers.get(key)
        empty = value is None or value == "" or value == []
        if field.get("required") and ((field.get("type") == "file" and key not in file_keys) or (field.get("type") != "file" and empty)):
            raise HTTPException(status_code=422, detail=f"Vui lòng nhập: {field.get('label')}")
        if empty:
            continue
        if field.get("type") == "email" and not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", str(value)):
            raise HTTPException(status_code=422, detail=f"Email không hợp lệ: {field.get('label')}")
        if field.get("type") == "number":
            try:
                number = float(value)
            except (TypeError, ValueError) as error:
                raise HTTPException(status_code=422, detail=f"Giá trị số không hợp lệ: {field.get('label')}") from error
            if field.get("min") is not None and number < float(field["min"]):
                raise HTTPException(status_code=422, detail=f"{field.get('label')} phải từ {field['min']}.")
            if field.get("max") is not None and number > float(field["max"]):
                raise HTTPException(status_code=422, detail=f"{field.get('label')} tối đa {field['max']}.")


def _serialize_submission(row: OnboardingSubmission, *, include_answers: bool = True) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": row.id,
        "public_id": row.public_id,
        "status": row.status,
        "full_name": row.full_name,
        "email": row.email,
        "application_type": row.application_type,
        "review_note": row.review_note,
        "employee_id": row.employee_id,
        "submitted_at": row.submitted_at,
        "updated_at": row.updated_at,
        "reviewed_at": row.reviewed_at,
        "form_version": row.form_version.version_number if row.form_version else None,
        "attachments": [
            {
                "id": attachment.id,
                "field_key": attachment.field_key,
                "original_name": attachment.original_name,
                "content_type": attachment.content_type,
                "size_bytes": attachment.size_bytes,
                "download_url": f"/api/onboarding/admin/submissions/{row.id}/attachments/{attachment.id}",
            }
            for attachment in row.attachments
        ],
    }
    if include_answers:
        value["answers"] = _json_load(row.answers_json, {})
        value["fields"] = _json_load(row.form_version.fields_json, []) if row.form_version else []
    return value


def _notify_admins(db: Session, submission: OnboardingSubmission) -> None:
    admins = db.query(User).filter(User.role.in_(tuple(HR_MANAGER_ROLES))).all()
    for admin in admins:
        add_notification(
            db,
            category=HR,
            event_type="ONBOARDING_SUBMITTED",
            title="Có hồ sơ onboarding mới",
            message=f"{submission.full_name} đã gửi hồ sơ onboarding ({submission.application_type}).",
            target_user_id=admin.id,
            resource_type="ONBOARDING_SUBMISSION",
            resource_id=submission.id,
            action_url="/hr/onboarding" if admin.role == "HR_ADMIN" else "/admin/onboarding",
        )


@router.get("/form")
def get_public_form(db: Session = Depends(get_db)) -> dict[str, Any]:
    published, _ = _ensure_default_forms(db)
    return _serialize_form(published)


@router.post("/submissions", status_code=status.HTTP_201_CREATED)
async def create_submission(
    answers_json: str = Form(...),
    file_keys_json: str = Form(default="[]"),
    files: list[UploadFile] | None = File(default=None),
    website: str = Form(default=""),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if website:
        raise HTTPException(status_code=400, detail="Yêu cầu không hợp lệ.")
    published, _ = _ensure_default_forms(db)
    answers = _json_load(answers_json, None)
    file_keys = _json_load(file_keys_json, [])
    upload_files = files or []
    if not isinstance(file_keys, list) or len(file_keys) != len(upload_files):
        raise HTTPException(status_code=422, detail="Thông tin tệp đính kèm không khớp.")
    if len(upload_files) > MAX_FILES_PER_SUBMISSION:
        raise HTTPException(status_code=422, detail=f"Chỉ được tải tối đa {MAX_FILES_PER_SUBMISSION} tệp.")
    fields = _json_load(published.fields_json, [])
    _validate_submission(fields, answers, [str(key) for key in file_keys])

    submission = OnboardingSubmission(
        public_id=str(uuid4()),
        form_version_id=published.id,
        status="NEW",
        full_name=str(answers.get("full_name") or "").strip(),
        email=str(answers.get("email") or "").strip().lower(),
        application_type=str(answers.get("application_type") or "").strip().upper(),
        answers_json=json.dumps(answers, ensure_ascii=False),
    )
    db.add(submission)
    db.flush()
    folder = UPLOAD_DIRECTORY / "onboarding" / submission.public_id
    folder.mkdir(parents=True, exist_ok=True)
    try:
        for field_key, upload in zip(file_keys, upload_files):
            suffix = Path(upload.filename or "").suffix.lower()
            if suffix not in ALLOWED_FILE_SUFFIXES:
                raise HTTPException(status_code=422, detail=f"Định dạng tệp không hỗ trợ: {upload.filename}")
            content = await upload.read(MAX_FILE_BYTES + 1)
            if len(content) > MAX_FILE_BYTES:
                raise HTTPException(status_code=422, detail=f"Tệp {upload.filename} vượt quá 15 MB.")
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(upload.filename or "file").name)
            stored_name = f"{uuid4().hex}_{safe_name}"
            target = folder / stored_name
            target.write_bytes(content)
            db.add(OnboardingAttachment(
                submission_id=submission.id,
                field_key=str(field_key),
                original_name=Path(upload.filename or "file").name,
                stored_path=str(target.relative_to(UPLOAD_DIRECTORY)).replace("\\", "/"),
                content_type=upload.content_type,
                size_bytes=len(content),
            ))
        _notify_admins(db, submission)
        db.commit()
    except Exception:
        db.rollback()
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
        raise
    return {"public_id": submission.public_id, "status": submission.status, "message": published.success_message}


@router.get("/submissions/{public_id}/status")
def public_submission_status(public_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.query(OnboardingSubmission).filter(OnboardingSubmission.public_id == public_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ.")
    return {"public_id": row.public_id, "status": row.status, "review_note": row.review_note, "updated_at": row.updated_at}


@router.get("/admin/config")
def get_admin_configuration(
    db: Session = Depends(get_db),
    _: User = Depends(get_hr_manager_user),
) -> dict[str, Any]:
    published, draft = _ensure_default_forms(db)
    return {"published": _serialize_form(published), "draft": _serialize_form(draft), "public_path": "/onboarding"}


@router.put("/admin/config")
def save_draft_configuration(
    payload: FormConfigurationPayload,
    db: Session = Depends(get_db),
    actor: User = Depends(get_hr_manager_user),
) -> dict[str, Any]:
    _, draft = _ensure_default_forms(db)
    fields = _validate_configuration(payload)
    draft.title = payload.title.strip()
    draft.description = payload.description.strip()
    draft.success_message = payload.success_message.strip()
    draft.fields_json = json.dumps(fields, ensure_ascii=False)
    draft.created_by_id = actor.id
    db.commit()
    db.refresh(draft)
    return _serialize_form(draft)


@router.post("/admin/config/publish")
def publish_configuration(
    payload: FormConfigurationPayload | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(get_hr_manager_user),
) -> dict[str, Any]:
    current, draft = _ensure_default_forms(db)
    if payload is not None:
        fields = _validate_configuration(payload)
        draft.title = payload.title.strip()
        draft.description = payload.description.strip()
        draft.success_message = payload.success_message.strip()
        draft.fields_json = json.dumps(fields, ensure_ascii=False)
    else:
        _validate_configuration(FormConfigurationPayload(
            title=draft.title,
            description=draft.description,
            success_message=draft.success_message,
            fields=_json_load(draft.fields_json, []),
        ))
    current.status = "ARCHIVED"
    draft.status = "PUBLISHED"
    draft.published_at = datetime.now(timezone.utc)
    draft.created_by_id = actor.id
    db.flush()
    next_draft = OnboardingFormVersion(
        version_number=draft.version_number + 1,
        status="DRAFT",
        title=draft.title,
        description=draft.description,
        success_message=draft.success_message,
        fields_json=draft.fields_json,
        created_by_id=actor.id,
    )
    db.add(next_draft)
    record_audit(
        db,
        actor=actor,
        action="ONBOARDING_FORM_PUBLISH",
        resource_type="ONBOARDING_FORM",
        resource_id=draft.id,
        summary=f"Phát hành biểu mẫu onboarding phiên bản {draft.version_number}",
        after={"version": draft.version_number, "title": draft.title},
    )
    db.commit()
    db.refresh(next_draft)
    return {"published": _serialize_form(draft), "draft": _serialize_form(next_draft)}


@router.get("/admin/submissions")
def list_submissions(
    submission_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(get_hr_manager_user),
) -> list[dict[str, Any]]:
    query = db.query(OnboardingSubmission).options(
        joinedload(OnboardingSubmission.form_version), joinedload(OnboardingSubmission.attachments)
    )
    if submission_status:
        query = query.filter(OnboardingSubmission.status == submission_status.upper())
    rows = query.order_by(OnboardingSubmission.submitted_at.desc(), OnboardingSubmission.id.desc()).all()
    return [_serialize_submission(row) for row in rows]


def _submission_or_404(db: Session, submission_id: int) -> OnboardingSubmission:
    row = db.query(OnboardingSubmission).options(
        joinedload(OnboardingSubmission.form_version), joinedload(OnboardingSubmission.attachments)
    ).filter(OnboardingSubmission.id == submission_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ onboarding.")
    return row


@router.post("/admin/submissions/{submission_id}/request-changes")
def request_changes(
    submission_id: int,
    payload: ReviewPayload,
    db: Session = Depends(get_db),
    actor: User = Depends(get_hr_manager_user),
) -> dict[str, Any]:
    row = _submission_or_404(db, submission_id)
    if row.employee_id:
        raise HTTPException(status_code=409, detail="Hồ sơ đã tạo nhân viên chính thức.")
    row.status = "NEEDS_INFO"
    row.review_note = payload.note.strip()
    row.reviewer_id = actor.id
    row.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return _serialize_submission(row)


@router.post("/admin/submissions/{submission_id}/reject")
def reject_submission(
    submission_id: int,
    payload: ReviewPayload,
    db: Session = Depends(get_db),
    actor: User = Depends(get_hr_manager_user),
) -> dict[str, Any]:
    row = _submission_or_404(db, submission_id)
    if row.employee_id:
        raise HTTPException(status_code=409, detail="Hồ sơ đã tạo nhân viên chính thức.")
    row.status = "REJECTED"
    row.review_note = payload.note.strip()
    row.reviewer_id = actor.id
    row.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return _serialize_submission(row)


def _next_employee_code(db: Session) -> str:
    max_number = 0
    for (code,) in db.query(Employee.employee_code).filter(Employee.employee_code.isnot(None)).all():
        match = re.match(r"^SL(\d+)$", str(code or ""), re.IGNORECASE)
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"SL{max_number + 1:03d}"


def _employee_type(application_type: str) -> str:
    if application_type == "INTERN":
        return TRAINEE
    if application_type == "TRAINEE":
        return INTERN
    if application_type == "PROBATION":
        return PROBATION
    return FULLTIME


def _approved_status(application_type: str) -> str:
    return application_type if application_type in {"INTERN", "TRAINEE", "PROBATION", "OFFICIAL", "PART_TIME"} else "OFFICIAL"


@router.post("/admin/submissions/{submission_id}/approve")
def approve_submission(
    submission_id: int,
    payload: ApprovePayload,
    db: Session = Depends(get_db),
    actor: User = Depends(get_hr_manager_user),
) -> dict[str, Any]:
    row = _submission_or_404(db, submission_id)
    if row.employee_id:
        raise HTTPException(status_code=409, detail="Hồ sơ này đã được tạo thành nhân viên.")
    machine_id = payload.machine_employee_id.strip()
    if not machine_id:
        raise HTTPException(status_code=422, detail="Cần nhập mã máy chấm công trước khi phê duyệt.")
    if db.query(Employee).filter(Employee.machine_employee_id == machine_id).first():
        raise HTTPException(status_code=409, detail="Mã chấm công đã thuộc về nhân viên khác.")
    employee_code = (payload.employee_code or "").strip() or _next_employee_code(db)
    if db.query(Employee).filter(Employee.employee_code == employee_code).first():
        raise HTTPException(status_code=409, detail="Mã nhân viên đã tồn tại.")
    department = None
    if payload.department_id is not None:
        department = db.query(Department).filter(Department.id == payload.department_id).first()
        if not department:
            raise HTTPException(status_code=404, detail="Không tìm thấy phòng ban.")
    answers = _json_load(row.answers_json, {})
    notes = str(answers.get("company_notes") or "").strip() or None
    employee = Employee(
        machine_employee_id=machine_id,
        full_name=row.full_name,
        notion_name=(str(answers.get("english_name") or "").strip() or None),
        department_id=department.id if department else None,
        department_name=department.name if department else None,
        employee_code=employee_code,
        position=(str(answers.get("position_applied") or "").strip() or None),
        employee_type=_employee_type(row.application_type),
        start_date=payload.start_date or _parse_date(answers.get("available_start_date")),
        phone_number=(str(answers.get("personal_phone") or "").strip() or None),
        company_phone_number=(str(answers.get("company_extension") or "").strip() or None),
        personal_email=row.email,
        bank_name=(str(answers.get("bank_name") or "").strip() or None),
        account_number=(str(answers.get("bank_account") or "").strip() or None),
        notes=notes,
        annual_leave_quota=12,
        is_active=True,
        status="ACTIVE",
        contract_salary=0,
        meal_allowance=0,
        phone_allowance=0,
        trans_allowance=0,
        other_allowance=0,
        bonus_coefficient=0,
    )
    db.add(employee)
    db.flush()

    identity_urls: list[str] = []
    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for attachment in row.attachments:
        if attachment.field_key != "identity_documents":
            continue
        source = UPLOAD_DIRECTORY / attachment.stored_path
        if not source.is_file():
            continue
        suffix = source.suffix.lower()
        target_name = f"cccd_{employee.id}_{uuid4().hex}{suffix}"
        shutil.copy2(source, UPLOAD_DIRECTORY / target_name)
        identity_urls.append(f"/uploads/{target_name}")
    if identity_urls:
        employee.cccd_url = json.dumps(identity_urls, ensure_ascii=False)

    row.employee_id = employee.id
    row.status = _approved_status(row.application_type)
    row.review_note = "Đã phê duyệt và tạo hồ sơ nhân viên chính thức."
    row.reviewer_id = actor.id
    row.reviewed_at = datetime.now(timezone.utc)
    record_audit(
        db,
        actor=actor,
        action="ONBOARDING_APPROVE",
        resource_type="ONBOARDING_SUBMISSION",
        resource_id=row.id,
        summary=f"Duyệt onboarding và tạo nhân viên {employee.full_name}",
        after={"employee_id": employee.id, "employee_code": employee.employee_code, "status": row.status},
    )
    add_notification(
        db,
        category=HR,
        event_type="ONBOARDING_APPROVED",
        title="Hồ sơ onboarding đã được duyệt",
        message=f"{actor.username} đã duyệt hồ sơ {employee.full_name} và tạo mã {employee.employee_code}.",
        actor_user_id=actor_id(actor),
        resource_type="EMPLOYEE",
        resource_id=employee.id,
        action_url="/admin/employees",
    )
    db.commit()
    db.refresh(row)
    return _serialize_submission(row)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


@router.patch("/admin/submissions/{submission_id}/status")
def update_submission_status(
    submission_id: int,
    payload: StatusPayload,
    db: Session = Depends(get_db),
    actor: User = Depends(get_hr_manager_user),
) -> dict[str, Any]:
    row = _submission_or_404(db, submission_id)
    new_status = payload.status.strip().upper()
    if new_status not in PROCESSING_STATUSES:
        raise HTTPException(status_code=422, detail="Trạng thái onboarding không hợp lệ.")
    if new_status in {"INTERN", "TRAINEE", "PROBATION", "OFFICIAL", "PART_TIME", "DONE"} and not row.employee_id:
        raise HTTPException(status_code=409, detail="Cần phê duyệt và tạo nhân viên trước khi chuyển trạng thái này.")
    row.status = new_status
    row.review_note = payload.note.strip() if payload.note else row.review_note
    row.reviewer_id = actor.id
    row.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return _serialize_submission(row)


@router.get("/admin/submissions/{submission_id}/attachments/{attachment_id}")
def download_attachment(
    submission_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_hr_manager_user),
) -> FileResponse:
    attachment = db.query(OnboardingAttachment).filter(
        OnboardingAttachment.id == attachment_id,
        OnboardingAttachment.submission_id == submission_id,
    ).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp.")
    path = (UPLOAD_DIRECTORY / attachment.stored_path).resolve()
    upload_root = UPLOAD_DIRECTORY.resolve()
    if upload_root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp trên máy chủ.")
    return FileResponse(path, filename=attachment.original_name, content_type=attachment.content_type)
