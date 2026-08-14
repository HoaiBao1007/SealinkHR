# Runbook backup va restore MariaDB

## Muc tieu

Bao ve database SEALINK va xac minh co the khoi phuc du lieu khi su co hoac truoc
moi lan phat hanh. Thu muc `backend/uploads` la du lieu nghiep vu va phai duoc
sao luu cung database.

## Pham vi

- Database: MariaDB/MySQL, gia tri lay tu `DATABASE_URL` trong `backend/.env`.
- Backup: file gzip `sealink_YYYYMMDD_HHMMSS.sql.gz` va file checksum `.sha256`.
- Upload: `backend/uploads/` hoac duong dan volume tuong ung tren server.

Khong dua database, uploads, file `.env` hoac backup vao Git.

## Backup hang ngay

Chay thu cong tu thu muc project:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\backup_db.ps1" -ProjectPath "D:\SEALINK\app"
```

Dang ky Scheduled Task luc 23:30:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\register_backup_task.ps1" -ScriptPath "D:\SEALINK\app\scripts\backup_db.ps1"
```

Sau khi backup, kiem tra file `.sql.gz` va `.sha256` deu ton tai. Backup hop le
phai bat dau bang gzip magic bytes `1F 8B`; script se bao loi neu khong tao duoc
gzip dung dinh dang.

Giu toi thieu 30 ban tren server va dong bo ban backup quan trong sang NAS hoac
cloud private. Dinh ky khoi phuc mot ban backup vao database staging de kiem tra.

## Restore an toan

Canh bao: restore co the ghi de du lieu. Khong restore truc tiep vao production
neu chua thu tren staging.

1. Tam dung ghi du lieu va tao them mot backup hien trang.
2. Khoi phuc file backup vao database staging rong.
3. Doi soat so luong `employees`, `attendance_daily`, `timesheets` va file uploads.
4. Chi khi staging dat ket qua moi thao tac production trong cua so bao tri.
5. Sau restore, chay `alembic upgrade head` neu release yeu cau migration moi va
   kiem tra `GET /health`.

## Truoc moi lan cap nhat code

1. Tao backup database va snapshot uploads.
2. Cap nhat code bang Git, khong ghi de `.env` hoac `uploads`.
3. Cai dependency, chay `alembic upgrade head`, build frontend va restart service.
4. Kiem tra health endpoint va cac chuc nang dang nhap/import chinh.
