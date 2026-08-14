from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.notification import Notification
from app.models.user import User


HR = "HR"
PAYROLL = "PAYROLL"
ATTENDANCE = "ATTENDANCE"
BONUS = "BONUS"
TIME_OFF = "TIME_OFF"

IN_APP_CHANNEL = "IN_APP"
DEFAULT_NOTIFICATION_CHANNELS = (IN_APP_CHANNEL,)


def add_notification(
    db: Session,
    *,
    category: str,
    event_type: str,
    title: str,
    message: str,
    target_user_id: int | None = None,
    actor_user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    action_url: str | None = None,
) -> Notification:
    item = Notification(
        category=category,
        event_type=event_type,
        title=title,
        message=message,
        target_user_id=target_user_id,
        actor_user_id=actor_user_id,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        action_url=action_url,
    )
    db.add(item)
    return item


def dispatch_notification(
    db: Session,
    *,
    category: str,
    event_type: str,
    title: str,
    message: str,
    target_user_id: int,
    actor_user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    action_url: str | None = None,
    channels: tuple[str, ...] | None = None,
) -> list[Notification]:
    """Dispatch a business notification without coupling callers to a channel.

    Time Off submit/approval code calls this boundary once. An EMAIL delivery
    adapter can be registered here later without changing the workflow logic.
    Only the existing in-app channel is enabled today.
    """
    delivered: list[Notification] = []
    for channel in channels or DEFAULT_NOTIFICATION_CHANNELS:
        if channel != IN_APP_CHANNEL:
            raise ValueError(f"Unsupported notification channel: {channel}")
        delivered.append(
            add_notification(
                db,
                category=category,
                event_type=event_type,
                title=title,
                message=message,
                target_user_id=target_user_id,
                actor_user_id=actor_user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                action_url=action_url,
            )
        )
    return delivered


def add_employee_notification(
    db: Session,
    employee: Employee,
    **kwargs,
) -> Notification | None:
    if employee.user_id is None:
        return None
    return add_notification(db, target_user_id=employee.user_id, **kwargs)


def add_employee_notifications(
    db: Session,
    employees: Iterable[Employee],
    **kwargs,
) -> int:
    count = 0
    seen_user_ids: set[int] = set()
    for employee in employees:
        if employee.user_id is None or employee.user_id in seen_user_ids:
            continue
        seen_user_ids.add(employee.user_id)
        add_notification(db, target_user_id=employee.user_id, **kwargs)
        count += 1
    return count


def actor_id(user: User | None) -> int | None:
    return user.id if user and user.id else None
