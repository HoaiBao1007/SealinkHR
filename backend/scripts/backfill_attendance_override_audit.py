"""One-time, idempotent mirror of historical attendance overrides into IT audit."""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal
from app.services.attendance_audit_sync import sync_attendance_override_audit_events


def main() -> None:
    db = SessionLocal()
    try:
        result = sync_attendance_override_audit_events(db)
        db.commit()
        print(f"Attendance audit mirror complete: created={result['created']}, existing={result['already_synced']}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
