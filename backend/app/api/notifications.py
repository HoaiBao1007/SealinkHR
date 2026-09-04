from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.roles import BUSINESS_ADMIN_ROLES, HR_ADMIN
from app.models.employee import Employee
from app.models.notification import Notification, NotificationRead
from app.models.user import User


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _action_context(db: Session, item: Notification) -> dict:
    """Resolve an immutable notification resource into an exact UI target.

    The notification table deliberately stores a generic resource type/id.
    Resolving the current display context here keeps notification navigation
    stable even when a Sales name or a period label contains spaces/Unicode.
    """
    context: dict = {
        "resource_type": item.resource_type,
        "resource_id": item.resource_id,
    }
    if item.target_user_id is not None:
        context["target_user_id"] = item.target_user_id
        target_employee = (
            db.query(Employee).filter(Employee.user_id == item.target_user_id).first()
        )
        if target_employee:
            context.update(
                {
                    "target_employee_id": target_employee.id,
                    "target_employee_name": target_employee.full_name,
                }
            )
    if not item.resource_type or not item.resource_id:
        return context

    if item.resource_type == "COMMISSION_JOB":
        from app.models.commission import CommissionJob, CommissionWalletLedger

        try:
            job = db.get(CommissionJob, int(item.resource_id))
        except (TypeError, ValueError):
            job = None
        if job:
            payout_periods = [
                value[0]
                for value in (
                    db.query(CommissionWalletLedger.payout_period)
                    .filter(
                        CommissionWalletLedger.job_id == job.id,
                        CommissionWalletLedger.entry_type == "SCHEDULED",
                        CommissionWalletLedger.payout_period.isnot(None),
                    )
                    .distinct()
                    .order_by(CommissionWalletLedger.payout_period.asc())
                    .all()
                )
                if value[0]
            ]
            context.update(
                {
                    "job_id": job.id,
                    "job_no": job.job_no,
                    "period_id": job.period_id,
                    "period_label": job.period.period_label if job.period else None,
                    "sales_rep": job.sales_rep,
                    "payout_periods": payout_periods,
                }
            )
    elif item.resource_type == "EMPLOYEE":
        try:
            employee_id = int(item.resource_id)
        except (TypeError, ValueError):
            employee_id = None
        if employee_id is not None:
            employee = db.get(Employee, employee_id)
            context.update(
                {
                    "employee_id": employee_id,
                    "employee_name": employee.full_name if employee else None,
                    "resource_exists": employee is not None,
                }
            )
    elif item.resource_type == "SALARY_PERIOD":
        context["salary_period"] = item.resource_id
    elif item.resource_type == "TIMESHEET_PERIOD":
        start, separator, end = item.resource_id.partition(":")
        context.update(
            {
                "period_start": start or None,
                "period_end": end if separator else None,
                "attendance_month": (end if separator else start)[:7] or None,
            }
        )
    elif item.resource_type == "TIME_OFF_REQUEST":
        from app.models.off_request import OffRequest

        try:
            request_id = int(item.resource_id)
        except (TypeError, ValueError):
            request_id = None
        request = db.get(OffRequest, request_id) if request_id is not None else None
        context.update(
            {
                "request_id": request_id,
                "request_status": request.status if request else None,
                "resource_exists": request is not None,
            }
        )
    return context


def _visible_query(db: Session, user: User):
    query = db.query(Notification)
    if user.role in BUSINESS_ADMIN_ROLES:
        # Explicitly targeted notifications are private to their recipient.
        # Untargeted operational notifications remain visible to business admins.
        return query.filter(
            or_(
                Notification.target_user_id == user.id,
                and_(
                    Notification.target_user_id.is_(None),
                    Notification.category != "TIME_OFF",
                ),
            )
        )
    if user.role == HR_ADMIN:
        return query.filter(
            or_(
                Notification.target_user_id == user.id,
                and_(
                    Notification.target_user_id.is_(None),
                    Notification.category == "HR",
                ),
            )
        )
    return query.filter(Notification.target_user_id == user.id)


def _is_visible(db: Session, user: User, notification_id: int) -> Notification | None:
    return _visible_query(db, user).filter(Notification.id == notification_id).first()


@router.get("")
def list_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    visible = _visible_query(db, current_user)
    unread_condition = ~exists().where(
        and_(
            NotificationRead.notification_id == Notification.id,
            NotificationRead.user_id == current_user.id,
        )
    )
    unread_count = visible.filter(unread_condition).count()
    items = visible.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).all()
    item_ids = [item.id for item in items]
    target_user_ids = {item.target_user_id for item in items if item.target_user_id is not None}
    actor_user_ids = {item.actor_user_id for item in items if item.actor_user_id is not None}
    related_user_ids = target_user_ids | actor_user_ids
    account_labels: dict[int, str] = {}
    if related_user_ids:
        account_labels.update(
            {
                user.id: user.username
                for user in db.query(User).filter(User.id.in_(related_user_ids)).all()
            }
        )
        account_labels.update(
            {
                employee.user_id: employee.full_name
                for employee in db.query(Employee)
                .filter(Employee.user_id.in_(related_user_ids))
                .all()
                if employee.user_id is not None
            }
        )
    read_ids = set()
    if item_ids:
        read_ids = {
            row.notification_id
            for row in db.query(NotificationRead)
            .filter(
                NotificationRead.user_id == current_user.id,
                NotificationRead.notification_id.in_(item_ids),
            )
            .all()
        }
    return {
        "unread_count": unread_count,
        "items": [
            {
                "id": item.id,
                "category": item.category,
                "event_type": item.event_type,
                "title": item.title,
                "message": item.message,
                "resource_type": item.resource_type,
                "resource_id": item.resource_id,
                "action_url": item.action_url,
                "action_context": _action_context(db, item),
                "target_name": account_labels.get(item.target_user_id) if item.target_user_id else None,
                "sender_name": account_labels.get(item.actor_user_id) if item.actor_user_id else None,
                "created_at": item.created_at,
                "is_read": item.id in read_ids,
            }
            for item in items
        ],
    }


@router.post("/items/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _is_visible(db, current_user, notification_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy thông báo.")
    existing = (
        db.query(NotificationRead)
        .filter(
            NotificationRead.notification_id == notification_id,
            NotificationRead.user_id == current_user.id,
        )
        .first()
    )
    if not existing:
        db.add(
            NotificationRead(
                notification_id=notification_id,
                user_id=current_user.id,
                read_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    return {"ok": True}


@router.post("/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    visible_ids = [item.id for item in _visible_query(db, current_user).all()]
    if not visible_ids:
        return {"ok": True, "marked_count": 0}
    existing_ids = {
        row.notification_id
        for row in db.query(NotificationRead)
        .filter(
            NotificationRead.user_id == current_user.id,
            NotificationRead.notification_id.in_(visible_ids),
        )
        .all()
    }
    now = datetime.now(timezone.utc)
    missing = [
        NotificationRead(notification_id=notification_id, user_id=current_user.id, read_at=now)
        for notification_id in visible_ids
        if notification_id not in existing_ids
    ]
    db.add_all(missing)
    db.commit()
    return {"ok": True, "marked_count": len(missing)}
