# Trien khai SEALINK tren Windows Server (khong dung Linux/WSL)

Tai lieu nay su dung IIS, Python va MariaDB chay native tren Windows Server.
Repository chi chua code; database, uploads va secrets duoc chuyen va luu tru
rieng.

## 1. Chuan bi server

- Cai IIS, URL Rewrite va Application Request Routing (ARR).
- Cai Python 3.12+, Node.js LTS va MariaDB/MySQL Service.
- Tao cac thu muc:

```text
D:\SEALINK\app       # repository Git
D:\SEALINK\data\uploads
D:\SEALINK\secrets
D:\SEALINK\backups
```

- Chi mo cong 80/443; khong public cong MariaDB 3306.
- Tao database `sealink_hr` va tai khoan `sealink_app` co quyen tren rieng
  database nay. Khong dung tai khoan `root` cua XAMPP trong production.

## 2. Lay code va tao cau hinh rieng

```powershell
git clone https://github.com/HoaiBao1007/SealinkHR.git D:\SEALINK\app
Copy-Item D:\SEALINK\app\backend\.env.example D:\SEALINK\secrets\backend.env
```

Tao `D:\SEALINK\app\backend\.env` tu file trong `D:\SEALINK\secrets` (hoac
tao symlink do IT quan ly). Dat `APP_ENV=production`, `DATABASE_URL`,
`SECRET_KEY`, mat khau khoi tao va `CORS_ORIGINS=https://ten-mien-cua-ban`.
Tuyet doi khong commit file nay.

## 3. Chuyen du lieu lan dau

1. Chot thoi diem import/ghi du lieu tren may cu.
2. Tao mot MariaDB dump moi, kiem tra restore duoc vao staging va tinh checksum.
3. Copy dump va toan bo `backend/uploads` sang server qua kenh noi bo an toan.
4. Restore dump vao `sealink_hr`; copy uploads vao `D:\SEALINK\data\uploads`.
5. Tao junction `D:\SEALINK\app\backend\uploads` tro den thu muc data, hoac
   cau hinh service de chay voi dung duong dan nay.

Database tren server se la nguon du lieu chinh sau khi cutover. Khong copy
database tu may ca nhan de ghi de database production o cac lan cap nhat sau.

## 4. Cai va chay backend

```powershell
Set-Location D:\SEALINK\app\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Sau khi kiem tra `http://127.0.0.1:8001/health`, dung WinSW hoac NSSM de chay
lenh Uvicorn nhu mot Windows Service, tu dong khoi dong lai khi server reboot.
IIS/ARR reverse proxy `/api` vao `http://127.0.0.1:8001`.

## 5. Build va phuc vu frontend

```powershell
Set-Location D:\SEALINK\app\frontend
npm ci
npm run build
```

Tao IIS site tro vao `D:\SEALINK\app\frontend\dist`, bat HTTPS cho domain va
chuyen cac request `/api` sang backend. Voi frontend va API cung mot domain,
khong can dat `VITE_API_BASE`.

## 6. Cap nhat release

1. Tao backup database va uploads.
2. `git pull --ff-only origin main`.
3. Cai dependency backend neu `requirements.txt` thay doi.
4. Chay `alembic upgrade head` (khong chay downgrade tren production).
5. `npm ci` va `npm run build` neu frontend thay doi.
6. Restart Windows Service, kiem tra `/health` va luong dang nhap/import.

Neu bat ky buoc nao loi, dung release va restore database/uploads tu backup da
kiem chung; khong tu y copy database tu may ca nhan de xu ly su co.
