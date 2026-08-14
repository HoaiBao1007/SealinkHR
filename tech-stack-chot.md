# Chot Cong Nghe Toi Uu - Attendance Management

## 1. Frontend (Chot)
- Framework: React + TypeScript + Vite
- Grid chinh: AG Grid
- State server: TanStack Query
- State UI: Zustand
- Form + validate: React Hook Form + Zod
- Date handling: Day.js
- Upload UI: react-dropzone
- Excel preview client-side (tuy chon): SheetJS

### Ly do chon
- AG Grid phu hop du lieu lon (nhieu nhan su x nhieu ngay), virtual scroll muot, filter/pin column manh.
- React ecosystem manh, de mo rong va de tim nguon luc dev.

## 2. Backend (Chot)
- Framework API: FastAPI
- Xu ly du lieu chinh: Polars
- Tuong thich Excel dinh dang va ghi file: openpyxl
- Fallback/compat layer: pandas (chi dung khi can)
- Validate schema: Pydantic v2
- ORM: SQLAlchemy 2.0
- Migration: Alembic

### Ly do chon
- FastAPI co hieu nang tot, API-first, de tach module import/timesheet/approval/export.
- Polars thuong nhanh hon pandas cho parse, group, aggregate du lieu lon.
- openpyxl phu hop bai toan doc/ghi file Excel theo mau ke toan.

## 3. Database (Chot)
- PostgreSQL 16
- Redis (cho queue/cache tac vu nen)

### Ly do chon
- PostgreSQL manh ve transaction, index, query tong hop, audit trail.
- Redis giup tach job nang (import/export) khoi request HTTP.

## 4. Background Jobs (Chot)
- Queue: RQ (Redis Queue) hoac Celery
- Khuyen nghi thuc dung: RQ cho giai doan dau (nhe, de van hanh)

## 5. Kien truc trien khai (Chot)
- Monorepo:
  - frontend/
  - backend/
- Docker Compose cho local dev (db + redis)
- Nginx reverse proxy (production)
- Logging: structlog hoac loguru + JSON logs
- Monitoring can ban: Prometheus + Grafana (phase 2)

## 6. Quy tac nghiep vu bat buoc
- Chu ky cong co dinh: ngay 23 thang truoc -> ngay 22 thang nay.
- Multi-check: lay min time = check-in, max time = check-out.
- Gap "Bo lo" => missing punch, canh bao do.
- Override bat buoc ly do + luu audit (ai sua, sua luc nao, gia tri truoc/sau).

## 7. Muc tieu hieu nang
- Preview parser file thong thuong: <= 2 giay (muc tieu)
- Import + normalize full batch: xu ly nen, co tien trinh va thong bao trang thai.

## 8. Danh sach cong nghe cuoi cung
- Frontend: React + TypeScript + Vite + AG Grid + TanStack Query + Zustand + Day.js
- Backend: FastAPI + Polars + openpyxl + Pydantic v2 + SQLAlchemy + Alembic
- Data/Infra: PostgreSQL + Redis + RQ (hoac Celery) + Docker Compose

## 9. Lo trinh ap dung
1. Phase MVP: FastAPI + pandas/openpyxl + React + AG Grid + PostgreSQL.
2. Phase Scale: thay parser chinh sang Polars, bo sung Redis + RQ, them monitoring.
