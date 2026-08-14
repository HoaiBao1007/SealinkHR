"""Synchronize account roles from the current organization chart."""

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.services.access_role_service import sync_all_employee_access_roles


def main() -> None:
    db = SessionLocal()
    try:
        rows = sync_all_employee_access_roles(db)
        db.commit()
        for row in rows:
            if row["user_id"] or row["role"] != "USER":
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
