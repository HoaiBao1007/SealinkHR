"""Transfer business ADMIN to Nguyễn Lý Tưởng and IT access to admin_sealink.

The script is idempotent. It creates the chief-accountant login only when the
employee does not yet have one, and prints the generated temporary password
only on that first run.
"""

from __future__ import annotations

from pathlib import Path
import secrets
import string
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.auth import get_password_hash
from app.core.roles import ADMIN, IT_ADMIN
from app.db.session import SessionLocal
from app.models.employee import Employee
from app.models.user import User
from app.services.access_role_service import sync_all_employee_access_roles


CHIEF_EMPLOYEE_CODE = "SL016"
CHIEF_MACHINE_ID = "14"
CHIEF_USERNAME = "tuong.nguyen@sea-link.com"
SHARED_IT_USERNAME = "admin_sealink"


def _temporary_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%*-_"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(char.islower() for char in password)
            and any(char.isupper() for char in password)
            and any(char.isdigit() for char in password)
            and any(char in "!@#$%*-_" for char in password)
        ):
            return password


def main() -> None:
    db = SessionLocal()
    generated_password: str | None = None
    try:
        chief = (
            db.query(Employee)
            .filter(
                (Employee.employee_code == CHIEF_EMPLOYEE_CODE)
                | (Employee.machine_employee_id == CHIEF_MACHINE_ID)
            )
            .first()
        )
        if not chief:
            raise RuntimeError("Không tìm thấy hồ sơ Nguyễn Lý Tưởng (SL016 / máy 14).")

        if chief.user_id:
            chief_user = db.get(User, chief.user_id)
            if not chief_user:
                raise RuntimeError("Hồ sơ Kế toán trưởng liên kết tài khoản không tồn tại.")
        else:
            duplicate = db.query(User).filter(User.username == CHIEF_USERNAME).first()
            if duplicate:
                raise RuntimeError(
                    f"Tên đăng nhập {CHIEF_USERNAME} đã tồn tại nhưng chưa liên kết đúng hồ sơ."
                )
            generated_password = _temporary_password()
            chief_user = User(
                username=CHIEF_USERNAME,
                password_hash=get_password_hash(generated_password),
                role=ADMIN,
            )
            db.add(chief_user)
            db.flush()
            chief.user_id = chief_user.id

        chief_user.role = ADMIN
        db.add(chief_user)

        shared_it = db.query(User).filter(User.username == SHARED_IT_USERNAME).first()
        if not shared_it:
            raise RuntimeError("Không tìm thấy tài khoản admin_sealink.")
        shared_it.role = IT_ADMIN
        db.add(shared_it)
        db.flush()

        rows = sync_all_employee_access_roles(db)
        db.commit()

        print(f"CHIEF_USERNAME={chief_user.username}")
        print(f"CHIEF_ROLE={chief_user.role}")
        if generated_password:
            print(f"CHIEF_TEMPORARY_PASSWORD={generated_password}")
        else:
            print("CHIEF_TEMPORARY_PASSWORD=UNCHANGED")
        print(f"SHARED_IT_USERNAME={shared_it.username}")
        print(f"SHARED_IT_ROLE={shared_it.role}")
        for row in rows:
            if row["user_id"]:
                marker = "UPDATED" if row["changed"] else "OK"
                print(
                    f"[{marker}] #{row['employee_id']} {row['employee_name']}: "
                    f"{row['role']} - {row['reason']}"
                )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
