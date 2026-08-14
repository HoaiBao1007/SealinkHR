# Ke hoach He thong Cham cong Noi bo

## Buoc 1 - Thiet ke Database Schema
- `timesheets`: tong hop theo ky 23 -> 22 va trang thai phe duyet.
- `timesheet_entries`: tung o ngay tren bang cong (original/final symbol).
- `off_requests`: quan ly nghi phep va cong tac.
- `attendance_overrides_audit`: lich su override bat buoc ly do.

### Rule du lieu
- Chu ky cong co dinh tu ngay 23 thang truoc den ngay 22 thang nay.
- Moi nhan vien moi ngay chi co 1 dong tong hop trong `attendance_daily`.
- Override phai co ly do va luu audit.

## Buoc 2 - Backend Parsing va Xu ly file

### Stack
- Python FastAPI
- Pandas + openpyxl de doc CSV/XLS/XLSX

### Thuat toan trong tam
1. Multi-check:
- Tach tat ca moc gio tu 1 o (vi du: 08:45, 10:54, 13:39, 18:03).
- Chon nho nhat lam check-in.
- `POST /api/import/abnormal-report`

6. Day.js: xu ly ngay cho ky 23 -> 22.

1. Tao migrations (Alembic) cho schema.
2. Tao API employees/timesheets/overrides/export.

### A. Nen tang va moi truong
 - [x] Khoi dong PostgreSQL bang Docker va xac nhan ket noi.
 - Da chay thanh cong container postgres:16 (sealinkweb-db-1) port 5432.
 [x] Them unique/index theo nghiep vu (employee + work_date, period, machine_employee_id).
 - Da them UniqueConstraint & Index vao cac model: attendance_daily, attendance_logs, timesheets, timesheet_entries.
### B. Co so du lieu
 [x] Tao model cho attendance_logs.
 - Da tao `backend/app/models/attendance_log.py`.
 [x] Tao model cho attendance_daily.
 - Da tao `backend/app/models/attendance_daily.py`.
 [x] Tao model cho timesheets.
 - Da tao `backend/app/models/timesheet.py`.
 [x] Tao model cho timesheet_entries.
 - Da tao `backend/app/models/timesheet_entry.py`.
 [x] Tao model cho off_requests.
 - Da tao `backend/app/models/off_request.py`.
 [x] Tao model cho attendance_overrides_audit.
 - Da tao `backend/app/models/attendance_override_audit.py`.
 [x] Tao migration Alembic dau tien.
 - Da tao folder `backend/migrations` va file cau hinh Alembic.

### C. Import va parser du lieu
 [x] Mapping cot dau vao cho abnormal report.
 - Da tao API POST /api/import/abnormal-report, mapping cot: Mã NV, Họ tên, Ngày, Ghi chú, Trạng thái, Phòng ban. Parser phát hiện 'Bỏ lỡ' để đánh dấu missing punch.
 [x] Lay min lam check-in, max lam check-out.
 [x] Danh dau missing punch khi gap "Bo lo".

[x] Tinh period_start/period_end theo chu ky 23 -> 22.
 - Parser checkin profile đã trả về period_start, period_end đúng quy tắc nghiệp vụ.

[x] Tao du lieu preview truoc khi luu chinh thuc.
 - API upload checkin profile trả về preview dữ liệu.
[x] Luu lich su upload theo batch de truy vet.
 - API commit lưu dữ liệu vào DB và ghi lịch sử upload vào upload_batches.

[x] Mapping employee_id tu dong khi commit.
 - Khi lưu attendance_logs, tự động tra cứu employee_id từ machine_employee_id, ghi chú lỗi nếu không tìm thấy.

### D. API backend
 [x] Hoan thien GET /health.
 [x] Hoan thien POST /api/import/checkin-profile.
 [x] Hoan thien POST /api/import/abnormal-report.
 [x] Tao API employees (danh sach/tao-cap nhat).
 [x] Tao API timesheets theo ky cong 23 -> 22.
 [x] Tao API override ngay cong (bat buoc ly do).
 [x] Tao API phe duyet bang cong.
 [x] Tao API export bang cong ra Excel.

 - GET /health: [backend/app/main.py](backend/app/main.py)
 - POST /api/import/checkin-profile, POST /api/import/abnormal-report: [backend/app/api/importer.py](backend/app/api/importer.py)
 - POST /api/import/checkin-profile/commit: [backend/app/api/import_checkin_commit.py](backend/app/api/import_checkin_commit.py)
 - GET/POST/PUT /api/employees: [backend/app/api/employees.py](backend/app/api/employees.py)
 - GET /api/timesheets, POST /api/timesheets/{id}/approval: [backend/app/api/timesheet.py](backend/app/api/timesheet.py)
 - POST /api/attendance/override: [backend/app/api/override.py](backend/app/api/override.py)
 - GET /api/export/timesheet: [backend/app/api/export.py](backend/app/api/export.py)

### E. Frontend
- [x] Tao layout app va menu module (Dashboard, Import, Employee Directory, Timesheet, Export).
 - Dashboard da co tab KPI tong hop va trend theo ngay (API /api/dashboard/kpi).
- [x] Man hinh Import: drag-drop + preview + thong bao loi.
 - Da them drag-drop va validate cot CSV/XLS/XLSX truoc khi goi API preview.
- [x] Man hinh Employee Directory: tim kiem, cap nhat thong tin, map machine ID.
 - Da co tim kiem theo ID/ten va inline update machine ID + thong tin nhan vien.
- [x] Man hinh Timesheet: grid ngang ngay 23 -> 22.
 - Da them API /api/timesheets/grid va frontend grid theo tung ngay trong chu ky cong.
- [x] Them bo loc theo phong ban, ID, trang thai bat thuong.
 - Da co loc theo ID/ten, phong ban va abnormal (all/abnormal/normal).
- [x] Popup override: bat buoc nhap ly do, nguoi sua, thoi gian sua.
 - Da co popup override bat buoc ly do va bang log thao tac tren frontend.
- [x] Man hinh Approval: submit/approve/reject theo vai tro.
- [x] Man hinh Export: chon ky cong va tai file mau ke toan.

### F. Nghiep vu va doi soat
- [x] Dong bo cong-thuc tinh ngay cong (X, P, V, CT).
 - Da hien thi tong hop ky hieu X/P/V/CT theo tung nhan vien tren grid.
- [x] Tich hop quy tac phep nam va nghi co/khong luong.
 - Da them API /api/timesheets/policy-summary de tong hop paid/unpaid leave va so du phep theo ky.
- [x] Doi soat tong phut di muon, ve som, ngay vang voi file tom tat.
 - Grid tra ve va hien thi chi so tong late/early/absent de doi soat nhanh.
- [x] Xu ly conflict du lieu theo uu tien: override > abnormal > checkin profile.
 - Da them API /api/timesheets/conflict-audit de audit nguon du lieu theo thu tu uu tien.

### G. Kiem thu va van hanh
 [x] Tao bo test parser voi du lieu mau thuc te.
 - Da tao test pytest + TestClient tai backend/tests cho health, import, employees, commit, timesheet/approval, override, export.
 [x] Test case thieu cot, sai dinh dang, file trong, ID khong ton tai.
 - Da cover trong test import/commit va logic skip employee_not_found.
 [x] Test hieu nang import file lon.
 - Da bo sung test backend/tests/test_import_performance.py voi file 10,000 dong.
 [x] Kiem tra audit log day du cho moi override.
 - Da co test override va luu audit trong attendance_overrides_audit.
 [x] Viet huong dan su dung cho HR/Manager.
 - Da tao tai lieu: docs/HR_MANAGER_GUIDE.md.
 [x] Chot quy trinh backup database va phuc hoi.
 - Da tao tai lieu: docs/BACKUP_RESTORE.md.
 [x] Tu dong hoa backup tren Windows theo lich.
 - Da tao scripts/backup_db.ps1 va scripts/register_backup_task.ps1.
 [x] Man hinh hien thi lich su override tu audit backend.
 - Da bo sung API GET /api/attendance/override/history va frontend filter theo employee/limit.
 [x] Smoke test luong API Import -> Commit -> Timesheet -> Export KPI.
 - Da bo sung backend/tests/test_smoke_pipeline_api.py.
