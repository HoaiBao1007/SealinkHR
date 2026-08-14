import argparse
import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.services.organization_mapping import DOC_CHILD_UNIT_CODES, apply_organization_mapping


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="Map employees to organization units from the 01-Jul-2026 organization chart."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes. Without this flag the transaction is rolled back after showing a preview.",
    )
    parser.add_argument(
        "--doc-children-only",
        action="store_true",
        help="Only split employees assigned to the five DOC child branches.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        summary = apply_organization_mapping(
            db,
            include_unit_codes=DOC_CHILD_UNIT_CODES if args.doc_children_only else None,
        )
        if args.apply:
            db.commit()
            summary["mode"] = "applied"
        else:
            db.rollback()
            summary["mode"] = "dry-run"
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
