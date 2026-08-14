"""Prepare one-time IT_ADMIN browser enrollment from the server console.

Run without ``--reset`` for initial provisioning.  If the registered browser is
lost, an operator with database/server access may run with ``--reset`` to revoke
old credentials and prepare a new one-time enrollment from the latest known IP.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.roles import IT_ADMIN  # noqa: E402
from app.core.settings import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.system_audit_event import SystemAuditEvent  # noqa: E402
from app.models.trusted_device import TrustedDevice  # noqa: E402
from app.models.user import User  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="admin_sealink")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        if not user:
            raise RuntimeError(f"Không tìm thấy tài khoản {args.username}.")
        if user.role != IT_ADMIN:
            raise RuntimeError(f"Tài khoản {args.username} không phải IT_ADMIN.")

        devices = db.query(TrustedDevice).filter(TrustedDevice.user_id == user.id).all()
        active_devices = [device for device in devices if device.is_active]
        if active_devices and not args.reset:
            print("Thiết bị IT_ADMIN đã được đăng ký; không thay đổi dữ liệu.")
            return 0
        if args.reset:
            for device in devices:
                device.is_active = False
                device.credential_hash = None

        latest_login = (
            db.query(SystemAuditEvent)
            .filter(
                SystemAuditEvent.actor_user_id == user.id,
                SystemAuditEvent.action == "AUTH_LOGIN",
                SystemAuditEvent.status == "SUCCESS",
                SystemAuditEvent.source_ip.is_not(None),
            )
            .order_by(SystemAuditEvent.id.desc())
            .first()
        )
        enrollment_ip = latest_login.source_ip if latest_login else None
        pending = next((device for device in devices if not device.is_active), None)
        if pending is None:
            pending = TrustedDevice(user_id=user.id, device_label=settings.it_admin_default_device_label)
            db.add(pending)
        pending.device_label = settings.it_admin_default_device_label
        pending.enrollment_ip = enrollment_ip
        pending.credential_hash = None
        pending.is_active = False
        db.commit()
        print(
            "Đã chuẩn bị ghép thiết bị IT_ADMIN: "
            f"label={pending.device_label}, enrollment_ip={pending.enrollment_ip or 'ANY'}."
        )
        print("Lần đăng nhập hợp lệ tiếp theo từ IP này sẽ ghép trình duyệt và khóa các thiết bị khác.")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
