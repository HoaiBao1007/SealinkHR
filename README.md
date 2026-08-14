# Attendance Management Workspace

Full-stack workspace for internal attendance management with FastAPI + React + MariaDB/MySQL and a machine-workbook parser for Excel/CSV imports.

## Structure
- `frontend/`: React + Vite + TypeScript UI
- `backend/`: FastAPI parser and API services
- `docs/DEPLOY_WINDOWS_SERVER.md`: Windows Server deployment runbook (no Linux/WSL)
- `file.md`: architecture/database/backend/frontend plan

## Current capabilities

- Upload workbook and inspect available sheets/header rows before mapping columns
- Custom preview flow for flexible sheet/header/column selection
- Parse 5-sheet attendance workbooks directly to clean JSON by employee/day
- Employees, timesheets, dashboard, export, and override APIs scaffolded in backend
- Backup scripts for MariaDB/MySQL on Windows

## Quick Start

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

### Database

The development environment can use SQLite, but the operational database is
MariaDB/MySQL. Create `backend/.env` from `backend/.env.example`, configure a
dedicated database account, then run `alembic upgrade head`.

Local defaults are frontend `http://localhost:5174` and API
`http://localhost:8001`. To use a separately hosted API, copy
`frontend/.env.example` to `frontend/.env.local` and set `VITE_API_BASE`.

Before starting the backend, create `backend/.env` from the appropriate
template and replace `SECRET_KEY`, `INITIAL_ADMIN_PASSWORD`, and
`INITIAL_USER_PASSWORD` with strong values. `SECRET_KEY` must be a random
string of at least 32 characters; placeholder values are rejected at startup.

For the Windows Server deployment, database migration, IIS and update procedure,
read [`docs/DEPLOY_WINDOWS_SERVER.md`](docs/DEPLOY_WINDOWS_SERVER.md).

## Key import endpoints

- `POST /api/import/workbook-inspect`
- `POST /api/import/sheet-inspect`
- `POST /api/import/custom-preview`
- `POST /api/import/attendance-json`
