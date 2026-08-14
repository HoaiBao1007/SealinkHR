import json
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, aliased

from app.api.deps import get_db, get_it_admin_user
from app.models.system_audit_event import SystemAuditEvent
from app.models.attendance_override_audit import AttendanceOverrideAudit
from app.models.employee import Employee
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.backup_service import backup_capability, create_backup, list_backups


router = APIRouter(
    prefix="/api/it",
    tags=["it-operations"],
    dependencies=[Depends(get_it_admin_user)],
)


def _decode(value: str | None):
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


@router.get("/backups")
def backups_status():
    backups = list_backups()
    return {
        "capability": backup_capability(),
        "last_backup": backups[0] if backups else None,
        "backups": backups,
        "policy": {
            "schedule": "23:30 hằng ngày",
            "retention_count": 30,
            "restore_requires_approval": True,
        },
    }


@router.post("/backups/run")
def run_backup(
    db: Session = Depends(get_db),
    actor: User = Depends(get_it_admin_user),
):
    try:
        result = create_backup()
    except RuntimeError as exc:
        record_audit(
            db,
            actor=actor,
            action="IT_BACKUP_RUN",
            resource_type="DATABASE_BACKUP",
            summary=f"Backup thất bại: {exc}",
            status="FAILED",
        )
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    record_audit(
        db,
        actor=actor,
        action="IT_BACKUP_RUN",
        resource_type="DATABASE_BACKUP",
        resource_id=result["name"],
        summary=f"Tạo backup {result['name']}",
        after=result,
    )
    db.commit()
    return result


@router.get("/audit")
def read_audit(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    username: str | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    query = db.query(SystemAuditEvent)
    if from_date:
        query = query.filter(
            SystemAuditEvent.occurred_at >= datetime.combine(from_date, time.min, tzinfo=timezone.utc)
        )
    if to_date:
        query = query.filter(
            SystemAuditEvent.occurred_at <= datetime.combine(to_date, time.max, tzinfo=timezone.utc)
        )
    if username:
        query = query.filter(SystemAuditEvent.actor_username.ilike(f"%{username.strip()}%"))
    if action:
        query = query.filter(SystemAuditEvent.action == action)
    if resource_type:
        query = query.filter(SystemAuditEvent.resource_type == resource_type)
    rows = query.order_by(SystemAuditEvent.id.desc()).limit(limit).all()
    return [
        {
            "id": row.id,
            "occurred_at": row.occurred_at.isoformat(),
            "actor_username": row.actor_username,
            "actor_role": row.actor_role,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "status": row.status,
            "summary": row.summary,
            "before": _decode(row.before_json),
            "after": _decode(row.after_json),
            "source_ip": row.source_ip,
            "device_address": row.device_address,
        }
        for row in rows
    ]


@router.get("/attendance-overrides")
def read_attendance_overrides(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Expose the legacy attendance override ledger to IT as read-only data."""
    employee_alias = aliased(Employee)
    changer_alias = aliased(Employee)
    query = (
        db.query(AttendanceOverrideAudit, employee_alias.full_name, changer_alias.full_name)
        .outerjoin(employee_alias, employee_alias.id == AttendanceOverrideAudit.employee_id)
        .outerjoin(changer_alias, changer_alias.id == AttendanceOverrideAudit.changed_by_user_id)
    )
    if from_date:
        query = query.filter(AttendanceOverrideAudit.changed_at >= datetime.combine(from_date, time.min))
    if to_date:
        query = query.filter(AttendanceOverrideAudit.changed_at <= datetime.combine(to_date, time.max))
    rows = (
        query.order_by(AttendanceOverrideAudit.changed_at.desc(), AttendanceOverrideAudit.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": audit.id,
            "changed_at": audit.changed_at.isoformat(),
            "employee_id": audit.employee_id,
            "employee_name": employee_name or f"Nhân viên #{audit.employee_id}",
            "work_date": audit.work_date.isoformat(),
            "old_symbol": audit.old_symbol,
            "new_symbol": audit.new_symbol,
            "old_check_in": audit.old_check_in,
            "new_check_in": audit.new_check_in,
            "old_check_out": audit.old_check_out,
            "new_check_out": audit.new_check_out,
            "reason": audit.reason,
            "changed_by_user_id": audit.changed_by_user_id,
            "changed_by_name": changer_name or f"Nhân viên #{audit.changed_by_user_id}",
            "source_ip": audit.source_ip,
            "device_address": audit.device_address,
        }
        for audit, employee_name, changer_name in rows
    ]
