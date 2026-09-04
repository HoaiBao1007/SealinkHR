"""Safely reset published payroll periods for a selected year.

The command is dry-run by default. Pass ``--apply`` to create a JSON backup and
atomically reset publication/approval state. Salary input rows (including
allowances) are preserved so the periods can be tested and published again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.settings import settings


PAYROLL_EVENT_TYPES = (
    "PAYSLIP_PUBLISHED",
    "PAYROLL_APPROVAL_REQUESTED",
    "PAYROLL_APPROVED",
)


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def _rows(result: Any) -> list[dict[str, Any]]:
    return [
        {key: _json_value(value) for key, value in row.items()}
        for row in result.mappings().all()
    ]


def _period_filter(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f"{prefix}salary_period >= :period_start AND {prefix}salary_period <= :period_end"


def _notification_filter(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    events = ", ".join(f"'{event}'" for event in PAYROLL_EVENT_TYPES)
    return (
        f"{prefix}category = 'PAYROLL' "
        f"AND {prefix}resource_type = 'SALARY_PERIOD' "
        f"AND {prefix}resource_id >= :period_start "
        f"AND {prefix}resource_id <= :period_end "
        f"AND {prefix}event_type IN ({events})"
    )


def _salary_preservation_snapshot(connection: Any, params: dict[str, str]) -> dict[str, Any]:
    row = connection.execute(
        text(
            "SELECT COUNT(*) AS row_count, "
            "COALESCE(SUM(meal_allowance_free), 0) AS meal_allowance_free, "
            "COALESCE(SUM(meal_allowance_tax), 0) AS meal_allowance_tax, "
            "COALESCE(SUM(phone_allowance_free), 0) AS phone_allowance_free, "
            "COALESCE(SUM(trans_allowance_tax), 0) AS trans_allowance_tax, "
            "COALESCE(SUM(perf_allowance_tax), 0) AS perf_allowance_tax, "
            "COALESCE(SUM(other_income), 0) AS other_income, "
            "COALESCE(SUM(bonus), 0) AS bonus, "
            "COALESCE(SUM(bonus_14), 0) AS bonus_14 "
            "FROM monthly_salary_inputs "
            f"WHERE {_period_filter()}"
        ),
        params,
    ).mappings().one()
    return {key: _json_value(value) for key, value in row.items()}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backup and reset published payroll state without deleting salary inputs."
    )
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the reset. Without this flag the command is read-only.",
    )
    args = parser.parse_args()

    if args.year < 2000 or args.year > 2100:
        raise SystemExit("Year must be between 2000 and 2100.")

    params = {
        "period_start": f"{args.year:04d}-01",
        "period_end": f"{args.year:04d}-12",
    }
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    safe_database_url = make_url(settings.database_url).render_as_string(hide_password=True)

    with engine.begin() as connection:
        preservation_before = _salary_preservation_snapshot(connection, params)
        published_inputs = _rows(
            connection.execute(
                text(
                    "SELECT * FROM monthly_salary_inputs "
                    f"WHERE {_period_filter()} AND is_published = 1 "
                    "ORDER BY salary_period, employee_id, id"
                ),
                params,
            )
        )
        workflows = _rows(
            connection.execute(
                text(
                    "SELECT * FROM salary_approval_workflows "
                    f"WHERE {_period_filter()} ORDER BY salary_period, id"
                ),
                params,
            )
        )
        notifications = _rows(
            connection.execute(
                text(
                    "SELECT * FROM notifications "
                    f"WHERE {_notification_filter()} ORDER BY id"
                ),
                params,
            )
        )
        notification_reads = _rows(
            connection.execute(
                text(
                    "SELECT nr.* FROM notification_reads AS nr "
                    "INNER JOIN notifications AS n ON n.id = nr.notification_id "
                    f"WHERE {_notification_filter('n')} ORDER BY nr.id"
                ),
                params,
            )
        )

        published_periods = sorted({row["salary_period"] for row in published_inputs})
        workflow_periods = sorted({row["salary_period"] for row in workflows})
        print(f"Database: {safe_database_url}")
        print(f"Year: {args.year}")
        print(f"Salary input rows preserved: {preservation_before['row_count']}")
        print(f"Published salary rows to reset: {len(published_inputs)}")
        print(f"Published periods: {', '.join(published_periods) or '(none)'}")
        print(f"Approval workflows to delete: {len(workflows)}")
        print(f"Workflow periods: {', '.join(workflow_periods) or '(none)'}")
        print(f"Payroll notifications to delete: {len(notifications)}")
        print(f"Notification read markers covered: {len(notification_reads)}")

        if not args.apply:
            print("DRY RUN ONLY - no database data was changed.")
            return 0

        backup_root = Path(__file__).resolve().parents[2] / "backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_root / f"payroll_publication_reset_{args.year}_{timestamp}.json"
        temporary_path = backup_path.with_suffix(backup_path.suffix + ".tmp")
        payload = {
            "schema_version": 1,
            "operation": "reset_published_payroll",
            "created_at": datetime.now().astimezone().isoformat(),
            "year": args.year,
            "database": safe_database_url,
            "scope": {
                "monthly_salary_inputs": "is_published changed from true to false; rows preserved",
                "salary_approval_workflows": "rows deleted for selected year",
                "notifications": list(PAYROLL_EVENT_TYPES),
            },
            "salary_data_preservation_snapshot": preservation_before,
            "monthly_salary_inputs": published_inputs,
            "salary_approval_workflows": workflows,
            "notifications": notifications,
            "notification_reads": notification_reads,
        }
        backup_bytes = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        temporary_path.write_bytes(backup_bytes)
        os.replace(temporary_path, backup_path)
        backup_sha256 = hashlib.sha256(backup_bytes).hexdigest()

        connection.execute(
            text(
                "UPDATE monthly_salary_inputs SET is_published = 0 "
                f"WHERE {_period_filter()} AND is_published = 1"
            ),
            params,
        )
        connection.execute(
            text(
                "DELETE nr FROM notification_reads AS nr "
                "INNER JOIN notifications AS n ON n.id = nr.notification_id "
                f"WHERE {_notification_filter('n')}"
            ),
            params,
        )
        connection.execute(
            text(f"DELETE FROM notifications WHERE {_notification_filter()}"),
            params,
        )
        connection.execute(
            text(f"DELETE FROM salary_approval_workflows WHERE {_period_filter()}"),
            params,
        )

        remaining_published = connection.execute(
            text(
                "SELECT COUNT(*) FROM monthly_salary_inputs "
                f"WHERE {_period_filter()} AND is_published = 1"
            ),
            params,
        ).scalar_one()
        remaining_workflows = connection.execute(
            text(
                "SELECT COUNT(*) FROM salary_approval_workflows "
                f"WHERE {_period_filter()}"
            ),
            params,
        ).scalar_one()
        remaining_notifications = connection.execute(
            text(
                "SELECT COUNT(*) FROM notifications "
                f"WHERE {_notification_filter()}"
            ),
            params,
        ).scalar_one()
        preservation_after = _salary_preservation_snapshot(connection, params)

        if any((remaining_published, remaining_workflows, remaining_notifications)):
            raise RuntimeError(
                "Post-reset verification failed: "
                f"published={remaining_published}, workflows={remaining_workflows}, "
                f"notifications={remaining_notifications}"
            )
        if preservation_after != preservation_before:
            raise RuntimeError(
                "Salary input or allowance preservation check failed; transaction will roll back."
            )

        print(f"Backup: {backup_path}")
        print(f"Backup SHA256: {backup_sha256}")
        print("RESET COMPLETE - salary inputs and allowance values were preserved.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
