# Backend (FastAPI)

## Run locally

1. Create venv
2. Install dependencies from `requirements.txt`
3. Create `.env` from `.env.example`
4. Start API:

```bash
uvicorn app.main:app --reload --port 8000
```

Windows (PowerShell) khuyen nghi:

```bash
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

## Environment

- Copy `backend/.env.example` to `backend/.env`
- Adjust `DATABASE_URL` and `CORS_ORIGINS` for your local setup
- Run `alembic upgrade head` after pulling new schema changes

## Endpoints

- `GET /health`
- `POST /api/import/workbook-inspect`
- `POST /api/import/sheet-inspect`
- `POST /api/import/custom-preview`
- `POST /api/import/checkin-profile`
- `POST /api/import/abnormal-report`
- `POST /api/import/attendance-json`
- `POST /api/import/checkin-profile/commit`
- `GET /api/employees`
- `POST /api/employees`
- `PUT /api/employees/{employee_id}`
- `DELETE /api/employees/{employee_id}`
- `GET /api/timesheets`
- `GET /api/timesheets/grid`
- `POST /api/timesheets/{timesheet_id}/approval`
- `GET /api/timesheets/policy-summary`
- `GET /api/timesheets/conflict-audit`
- `GET /api/dashboard/kpi`
- `POST /api/attendance/override`
- `GET /api/attendance/override/history`
- `GET /api/export/timesheet`
- `POST /api/export/attendance-json-report`
- `GET /api/export/kpi`

## Employee mapping for Notion leave

- Store machine ID in `machine_employee_id`
- Store Vietnamese employee name in `full_name`
- Store Notion identifier in `notion_name` (for example `DOCS - PARADO QUANG`)
- When a Notion CSV is uploaded, the export flow maps `notion_name -> machine_employee_id` before filling paid leave `P` into the machine timesheet

## Test

```bash
.\.venv\Scripts\python.exe -m pytest -q
```

## Attendance parser CLI

Phan parser 5 sheet co the chay truc tiep de doc workbook may cham cong `.xlsx/.xls`:

```bash
.\.venv\Scripts\python.exe -m app.services.attendance_parser "C:\path\to\attendance-workbook.xls"
```

Lenh tren se tra JSON hop nhat theo nhan vien/ngay, ap dung logic:

- chu ky cong 23 -> 22
- `Ho so check-in`: lay min gio lam `check_in`, max gio lam `check_out`
- `Bao cao bat thuong`: `Bo lo` => `Missing_Punch`, bo lo toan bo trong ngay co lich => `Absent`

## Backup automation (Windows)

- Script backup: `..\\scripts\\backup_db.ps1`
- Script tao lich backup hang ngay: `..\\scripts\\register_backup_task.ps1`
