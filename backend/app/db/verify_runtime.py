"""Read-only production data verification used by the Windows setup script."""

from sqlalchemy import text

from app.db.session import engine


EXPECTED_COUNTS = {
    "employees": 59,
    "attendance_daily": 1857,
    "timesheets": 121,
}


def main() -> None:
    with engine.connect() as connection:
        actual_counts = {
            table: connection.execute(
                text(f"SELECT COUNT(*) FROM `{table}`")
            ).scalar_one()
            for table in EXPECTED_COUNTS
        }
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    print(
        "DB_VERIFY"
        f"|employees={actual_counts['employees']}"
        f"|attendance_daily={actual_counts['attendance_daily']}"
        f"|timesheets={actual_counts['timesheets']}"
        f"|revision={revision}"
    )

    mismatches = {
        table: {"expected": expected, "actual": actual_counts[table]}
        for table, expected in EXPECTED_COUNTS.items()
        if actual_counts[table] != expected
    }
    if mismatches:
        raise SystemExit(f"Database row counts do not match: {mismatches}")


if __name__ == "__main__":
    main()
