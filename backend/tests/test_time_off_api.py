from datetime import date
from pathlib import Path

from app.api.deps import get_current_user
from app.main import app
from app.models.department import Department
from app.models.employee import Employee
from app.models.notification import Notification
from app.models.off_request import ApprovalAction, OffRequest, OffRequestAttachment
from app.models.system_audit_event import SystemAuditEvent
from app.models.user import User


def _seed_time_off_team(db_session):
    requester_user = User(username="timeoff.requester", password_hash="x", role="USER")
    manager_user = User(username="timeoff.manager", password_hash="x", role="USER")
    upper_user = User(username="timeoff.upper", password_hash="x", role="HR_ADMIN")
    outsider_user = User(username="timeoff.outsider", password_hash="x", role="USER")
    db_session.add_all([requester_user, manager_user, upper_user, outsider_user])
    db_session.flush()

    parent = Department(name="OPERATIONS")
    child = Department(name="DOC", parent=parent)
    db_session.add_all([parent, child])
    db_session.flush()

    requester = Employee(
        machine_employee_id="TO-REQ",
        employee_code="TO-REQ",
        full_name="Nguyễn Văn A",
        department_id=child.id,
        department_name=child.name,
        user_id=requester_user.id,
    )
    manager = Employee(
        machine_employee_id="TO-MGR",
        employee_code="TO-MGR",
        full_name="Trần Manager",
        department_id=child.id,
        department_name=child.name,
        user_id=manager_user.id,
    )
    upper = Employee(
        machine_employee_id="TO-UPPER",
        employee_code="TO-UPPER",
        full_name="Lê Upper Manager",
        department_id=parent.id,
        department_name=parent.name,
        user_id=upper_user.id,
    )
    outsider = Employee(
        machine_employee_id="TO-OUT",
        employee_code="TO-OUT",
        full_name="Phạm Outsider",
        department_id=parent.id,
        department_name=parent.name,
        user_id=outsider_user.id,
    )
    db_session.add_all([requester, manager, upper, outsider])
    db_session.flush()
    child.manager_id = manager.id
    parent.manager_id = upper.id
    db_session.commit()
    return {
        "requester_user": requester_user,
        "manager_user": manager_user,
        "upper_user": upper_user,
        "outsider_user": outsider_user,
        "requester": requester,
        "manager": manager,
        "upper": upper,
        "outsider": outsider,
        "child": child,
        "parent": parent,
    }


def _as_user(user):
    app.dependency_overrides[get_current_user] = lambda: user


def _request_payload(**overrides):
    payload = {
        "request_type": "ANNUAL_LEAVE",
        "start_date": "2026-08-17",
        "end_date": "2026-08-18",
        "day_part": "FULL_DAY",
        "reason": "Việc gia đình",
        "handover_notes": "Bàn giao hồ sơ đang xử lý",
    }
    payload.update(overrides)
    return payload


def _datetime_request_payload(**overrides):
    payload = {
        "request_type": "ANNUAL_LEAVE",
        "start_at": "2026-08-26T08:00:00",
        "end_at": "2026-08-26T12:00:00",
        "reason": "Việc gia đình theo giờ",
    }
    payload.update(overrides)
    return payload


def _website_request_payload(**overrides):
    payload = {
        "request_type": "LEAVE_REQUEST",
        "start_at": "2026-09-01T08:00:00",
        "end_at": "2026-09-01T17:00:00",
        "reason": "Việc gia đình",
    }
    payload.update(overrides)
    return payload


def test_time_off_submit_routes_to_department_manager_and_prevents_overlap(client, db_session):
    team = _seed_time_off_team(db_session)
    _as_user(team["requester_user"])

    bootstrap = client.get("/api/time-off/bootstrap")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["employee"]["id"] == team["requester"].id
    assert bootstrap.json()["manager"]["employee_id"] == team["manager"].id

    response = client.post(
        "/api/time-off/requests",
        json=_request_payload(handover_employee_id=team["outsider"].id),
    )
    assert response.status_code == 201
    request = response.json()
    assert request["status"] == "PENDING_MANAGER"
    assert request["manager"]["user_id"] == team["manager_user"].id
    assert request["total_days"] == 2

    persisted = db_session.get(OffRequest, request["id"])
    assert persisted.employee_id == team["requester"].id
    assert persisted.department_id == team["child"].id
    assert persisted.approver_user_id == team["manager_user"].id
    assert db_session.query(ApprovalAction).filter_by(request_id=request["id"], action="SUBMIT").count() == 1
    assert db_session.query(SystemAuditEvent).filter_by(resource_type="TIME_OFF_REQUEST", resource_id=str(request["id"])).count() == 1

    notification = db_session.query(Notification).filter_by(
        target_user_id=team["manager_user"].id,
        resource_type="TIME_OFF_REQUEST",
    ).one()
    assert "Nguyễn Văn A" in notification.message
    assert "DOC" in notification.message

    overlap = client.post(
        "/api/time-off/requests",
        json=_request_payload(start_date="2026-08-18", end_date="2026-08-19"),
    )
    assert overlap.status_code == 409
    assert "trùng" in overlap.json()["detail"].lower()

    spoofed = client.post(
        "/api/time-off/requests",
        json={**_request_payload(start_date="2026-08-20", end_date="2026-08-20"), "manager_id": team["upper"].id},
    )
    assert spoofed.status_code == 422


def test_employee_can_select_only_a_backend_approved_manager(client, db_session):
    team = _seed_time_off_team(db_session)
    _as_user(team["requester_user"])

    bootstrap = client.get("/api/time-off/bootstrap")
    assert bootstrap.status_code == 200
    options = bootstrap.json()["approver_options"]
    option_user_ids = {item["user_id"] for item in options}
    assert team["manager_user"].id in option_user_ids
    assert team["upper_user"].id in option_user_ids
    assert next(item for item in options if item["is_default"])["user_id"] == team["manager_user"].id

    selected = client.post(
        "/api/time-off/requests",
        json=_request_payload(
            start_date="2026-08-24",
            end_date="2026-08-24",
            approver_user_id=team["upper_user"].id,
        ),
    )
    assert selected.status_code == 201
    assert selected.json()["status"] == "PENDING_MANAGER"
    assert selected.json()["manager"]["user_id"] == team["upper_user"].id
    assert db_session.query(Notification).filter_by(
        target_user_id=team["upper_user"].id,
        resource_type="TIME_OFF_REQUEST",
        resource_id=str(selected.json()["id"]),
    ).count() == 1

    invalid = client.post(
        "/api/time-off/requests",
        json=_request_payload(
            start_date="2026-08-25",
            end_date="2026-08-25",
            approver_user_id=team["outsider_user"].id,
        ),
    )
    assert invalid.status_code == 422
    assert "không thuộc danh sách" in invalid.json()["detail"].lower()


def test_datetime_range_is_stored_calculated_and_checked_for_precise_overlap(client, db_session):
    team = _seed_time_off_team(db_session)
    _as_user(team["requester_user"])

    morning = client.post("/api/time-off/requests", json=_datetime_request_payload())
    assert morning.status_code == 201
    assert morning.json()["start_at"].startswith("2026-08-26T08:00:00")
    assert morning.json()["end_at"].startswith("2026-08-26T12:00:00")
    assert morning.json()["start_date"] == "2026-08-26"
    assert morning.json()["end_date"] == "2026-08-26"
    assert morning.json()["total_days"] == 0.5

    afternoon = client.post(
        "/api/time-off/requests",
        json=_datetime_request_payload(
            start_at="2026-08-26T13:00:00",
            end_at="2026-08-26T17:00:00",
        ),
    )
    assert afternoon.status_code == 201
    assert afternoon.json()["total_days"] == 0.5

    overlap = client.post(
        "/api/time-off/requests",
        json=_datetime_request_payload(
            start_at="2026-08-26T11:00:00",
            end_at="2026-08-26T14:00:00",
        ),
    )
    assert overlap.status_code == 409
    assert "trùng" in overlap.json()["detail"].lower()

    invalid = client.post(
        "/api/time-off/requests",
        json=_datetime_request_payload(
            start_at="2026-08-27T10:00:00",
            end_at="2026-08-27T09:00:00",
        ),
    )
    assert invalid.status_code == 422
    assert "kết thúc" in invalid.json()["detail"].lower()

    invalid_minute = client.post(
        "/api/time-off/requests",
        json=_datetime_request_payload(
            start_at="2026-08-27T10:15:00",
            end_at="2026-08-27T11:00:00",
        ),
    )
    assert invalid_minute.status_code == 422
    assert "00 hoặc 30" in invalid_minute.json()["detail"]


def test_manager_workflow_notifications_permissions_and_calendar_privacy(client, db_session):
    team = _seed_time_off_team(db_session)
    _as_user(team["requester_user"])
    created = client.post("/api/time-off/requests", json=_request_payload()).json()
    request_id = created["id"]

    _as_user(team["outsider_user"])
    private_calendar = client.get(
        "/api/time-off/calendar",
        params={"start_date": "2026-08-01", "end_date": "2026-08-31"},
    )
    assert private_calendar.status_code == 200
    pending_event = next(item for item in private_calendar.json()["events"] if item["id"] == request_id)
    assert pending_event["status"] == "PENDING_MANAGER"
    assert pending_event["reason"] is None
    assert pending_event["request_type"] is None
    public_pending_detail = client.get(f"/api/time-off/requests/{request_id}")
    assert public_pending_detail.status_code == 200
    assert public_pending_detail.json()["reason"] is None
    assert "actions" not in public_pending_detail.json()
    assert all(
        item["resource_type"] != "TIME_OFF_REQUEST"
        for item in client.get("/api/notifications").json()["items"]
    )

    unauthorized = client.post(
        f"/api/time-off/requests/{request_id}/actions",
        json={"action": "APPROVE"},
    )
    assert unauthorized.status_code == 404

    _as_user(team["manager_user"])
    pending = client.get("/api/time-off/requests/pending")
    assert pending.status_code == 200
    assert [item["id"] for item in pending.json()] == [request_id]

    missing_comment = client.post(
        f"/api/time-off/requests/{request_id}/actions",
        json={"action": "REQUEST_INFO"},
    )
    assert missing_comment.status_code == 422

    needs_info = client.post(
        f"/api/time-off/requests/{request_id}/actions",
        json={"action": "REQUEST_INFO", "comment": "Bổ sung người bàn giao."},
    )
    assert needs_info.status_code == 200
    assert needs_info.json()["status"] == "MORE_INFO_REQUIRED"

    _as_user(team["requester_user"])
    mine = client.get("/api/time-off/requests/mine")
    assert mine.status_code == 200
    assert mine.json()[0]["can_edit"] is True
    requester_notifications = client.get("/api/notifications").json()
    assert requester_notifications["unread_count"] >= 1
    assert requester_notifications["items"][0]["action_context"]["request_id"] == request_id

    resubmitted = client.put(
        f"/api/time-off/requests/{request_id}",
        json=_request_payload(handover_employee_id=team["outsider"].id),
    )
    assert resubmitted.status_code == 200
    assert resubmitted.json()["status"] == "PENDING_MANAGER"

    _as_user(team["manager_user"])
    approved = client.post(
        f"/api/time-off/requests/{request_id}/actions",
        json={"action": "APPROVE", "comment": "Đã sắp xếp công việc."},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert len(approved.json()["actions"]) == 4

    _as_user(team["outsider_user"])
    calendar = client.get(
        "/api/time-off/calendar",
        params={"start_date": "2026-08-01", "end_date": "2026-08-31"},
    )
    assert calendar.status_code == 200
    event = next(item for item in calendar.json()["events"] if item["id"] == request_id)
    assert event["status"] == "APPROVED"
    assert event["reason"] is None
    assert event["request_type"] is None
    public_detail = client.get(f"/api/time-off/requests/{request_id}")
    assert public_detail.status_code == 200
    assert public_detail.json()["reason"] is None
    assert "actions" not in public_detail.json()


def test_manager_cannot_self_approve_and_request_escalates_to_parent_manager(client, db_session):
    team = _seed_time_off_team(db_session)
    team["child"].manager_id = team["requester"].id
    db_session.commit()

    _as_user(team["requester_user"])
    bootstrap = client.get("/api/time-off/bootstrap").json()
    assert bootstrap["manager"]["employee_id"] == team["upper"].id
    assert bootstrap["manager"]["source"] == "PARENT_MANAGER"

    created = client.post("/api/time-off/requests", json=_request_payload()).json()
    assert created["manager"]["user_id"] == team["upper_user"].id

    self_action = client.post(
        f"/api/time-off/requests/{created['id']}/actions",
        json={"action": "APPROVE"},
    )
    assert self_action.status_code == 404

    _as_user(team["upper_user"])
    action = client.post(
        f"/api/time-off/requests/{created['id']}/actions",
        json={"action": "REJECT", "comment": "Không đủ nhân sự thay thế."},
    )
    assert action.status_code == 200
    assert action.json()["status"] == "REJECTED"


def test_it_admin_can_see_approver_and_update_only_leave_schedule(client, db_session):
    team = _seed_time_off_team(db_session)
    it_admin = User(username="timeoff.it-admin", password_hash="x", role="IT_ADMIN")
    db_session.add(it_admin)
    db_session.commit()

    _as_user(team["requester_user"])
    created = client.post("/api/time-off/requests", json=_request_payload()).json()
    request_id = created["id"]

    _as_user(team["manager_user"])
    approved = client.post(
        f"/api/time-off/requests/{request_id}/actions",
        json={"action": "APPROVE", "comment": "Approved by department Manager."},
    )
    assert approved.status_code == 200

    _as_user(it_admin)
    # Simulate an older row that has an approval history but no persisted
    # approver/approved_by fields. IT Admin must still see who approved it.
    legacy_row = db_session.get(OffRequest, request_id)
    legacy_row.approved_by_user_id = None
    legacy_row.approver_employee_id = None
    legacy_row.approver_user_id = None
    db_session.commit()

    calendar = client.get(
        "/api/time-off/calendar",
        params={"start_date": "2026-08-01", "end_date": "2026-08-31"},
    )
    assert calendar.status_code == 200
    event = next(item for item in calendar.json()["events"] if item["id"] == request_id)
    assert event["manager"]["full_name"] == team["manager"].full_name
    assert event["can_edit_schedule"] is True
    assert event["reason"] == "Việc gia đình"

    detail = client.get(f"/api/time-off/requests/{request_id}")
    assert detail.status_code == 200
    assert detail.json()["manager"]["full_name"] == team["manager"].full_name
    assert detail.json()["actions"][-1]["actor_name"] == team["manager"].full_name

    updated = client.put(
        f"/api/time-off/requests/{request_id}/schedule",
        json={"start_at": "2026-08-20T08:00:00", "end_at": "2026-08-21T17:00:00"},
    )
    assert updated.status_code == 200
    assert updated.json()["start_date"] == "2026-08-20"
    assert updated.json()["end_date"] == "2026-08-21"
    assert updated.json()["total_days"] == 2
    assert updated.json()["actions"][-1]["action"] == "IT_ADMIN_UPDATE_SCHEDULE"

    persisted = db_session.get(OffRequest, request_id)
    assert persisted.status == "APPROVED"
    assert persisted.start_date == date(2026, 8, 20)
    assert persisted.end_date == date(2026, 8, 21)
    assert db_session.query(SystemAuditEvent).filter_by(
        resource_type="TIME_OFF_REQUEST",
        resource_id=str(request_id),
        action="TIME_OFF_IT_ADMIN_UPDATE_SCHEDULE",
    ).count() == 1

    _as_user(team["outsider_user"])
    forbidden = client.put(
        f"/api/time-off/requests/{request_id}/schedule",
        json={"start_at": "2026-08-24T08:00:00", "end_at": "2026-08-24T17:00:00"},
    )
    assert forbidden.status_code == 403


def test_leave_request_reserves_remaining_annual_leave(client, db_session):
    team = _seed_time_off_team(db_session)
    team["requester"].annual_leave_quota = 1
    team["requester"].annual_leave_used = 0
    db_session.commit()
    _as_user(team["requester_user"])

    bootstrap = client.get("/api/time-off/bootstrap")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["leave_balance"]["available"] == 1
    assert [item["value"] for item in bootstrap.json()["request_types"]] == [
        "LEAVE_REQUEST",
        "WORK_FROM_HOME_REQUEST",
        "BUSINESS_TRAVEL_REQUEST",
    ]

    first = client.post("/api/time-off/requests", json=_website_request_payload())
    assert first.status_code == 201
    assert first.json()["request_type"] == "LEAVE_REQUEST"

    reserved = client.get("/api/time-off/bootstrap").json()["leave_balance"]
    assert reserved["reserved_request_days"] == 1
    assert reserved["available"] == 0

    second = client.post(
        "/api/time-off/requests",
        json=_website_request_payload(
            start_at="2026-09-02T08:00:00",
            end_at="2026-09-02T17:00:00",
        ),
    )
    assert second.status_code == 409
    assert "phép còn lại" in second.json()["detail"].lower()


def test_business_travel_requires_details_and_policy_confirmation(client, db_session):
    team = _seed_time_off_team(db_session)
    _as_user(team["requester_user"])

    base_payload = _website_request_payload(
        request_type="BUSINESS_TRAVEL_REQUEST",
        reason="Làm việc với khách hàng",
    )
    missing_location = client.post("/api/time-off/requests", json=base_payload)
    assert missing_location.status_code == 422

    missing_acknowledgement = client.post(
        "/api/time-off/requests",
        json={**base_payload, "business_travel_location": "Hà Nội"},
    )
    assert missing_acknowledgement.status_code == 422

    missing_attachment = client.post(
        "/api/time-off/requests",
        json={
            **base_payload,
            "business_travel_location": "Hà Nội",
            "business_travel_policy_acknowledged": True,
        },
    )
    assert missing_attachment.status_code == 422
    assert "quyết định" in missing_attachment.json()["detail"].lower()


def test_time_off_attachment_is_private_and_required_for_business_travel(client, db_session, tmp_path, monkeypatch):
    team = _seed_time_off_team(db_session)
    _as_user(team["requester_user"])
    monkeypatch.setattr("app.api.time_off.TIME_OFF_ATTACHMENT_DIRECTORY", tmp_path)

    staged = client.post(
        "/api/time-off/attachments",
        files=[("files", ("quyet-dinh.pdf", b"%PDF-1.7\nApproved business travel", "application/pdf"))],
    )
    assert staged.status_code == 200
    attachment = staged.json()["items"][0]
    assert attachment["file_name"] == "quyet-dinh.pdf"
    assert attachment["is_staged"] is True

    created = client.post(
        "/api/time-off/requests",
        json=_website_request_payload(
            request_type="BUSINESS_TRAVEL_REQUEST",
            business_travel_location="Hà Nội",
            business_travel_policy_acknowledged=True,
            attachment_ids=[attachment["id"]],
        ),
    )
    assert created.status_code == 201
    request = created.json()
    assert request["attachments"][0]["file_name"] == "quyet-dinh.pdf"
    persisted = db_session.get(OffRequestAttachment, attachment["id"])
    assert persisted.request_id == request["id"]

    _as_user(team["manager_user"])
    download = client.get(f"/api/time-off/requests/{request['id']}/attachments/{attachment['id']}/download")
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF-")

    _as_user(team["outsider_user"])
    forbidden = client.get(f"/api/time-off/requests/{request['id']}/attachments/{attachment['id']}/download")
    assert forbidden.status_code == 404
