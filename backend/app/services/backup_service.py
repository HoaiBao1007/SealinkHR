import gzip
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.settings import settings


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKUP_DIR = PROJECT_ROOT / "backups"


def _mysqldump_path() -> str | None:
    candidates = [
        shutil.which("mysqldump"),
        r"C:\xampp\mysql\bin\mysqldump.exe",
        r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def backup_capability() -> dict:
    driver = make_url(settings.database_url).drivername
    executable = _mysqldump_path() if settings.is_mysql else None
    return {
        "driver": driver,
        "ready": bool(executable) if settings.is_mysql else settings.is_sqlite,
        "tool": executable or ("safe file copy" if settings.is_sqlite else None),
        "backup_directory": str(BACKUP_DIR),
    }


def list_backups() -> list[dict]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for path in sorted(BACKUP_DIR.glob("sealink_*.gz"), key=lambda item: item.stat().st_mtime, reverse=True):
        stat = path.stat()
        checksum_path = path.with_suffix(path.suffix + ".sha256")
        result.append(
            {
                "name": path.name,
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "sha256": checksum_path.read_text(encoding="ascii").strip() if checksum_path.exists() else None,
            }
        )
    return result


def _write_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(value, encoding="ascii")
    return value


def create_backup(*, keep_last: int = 30) -> dict:
    """Create a compressed, checksummed backup without exposing credentials."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = BACKUP_DIR / f"sealink_{timestamp}.sql.gz"
    url = make_url(settings.database_url)

    if settings.is_mysql:
        executable = _mysqldump_path()
        if not executable:
            raise RuntimeError("Không tìm thấy mysqldump trong XAMPP hoặc PATH.")
        command = [
            executable,
            "--single-transaction",
            "--routines",
            "--triggers",
            "--events",
            "--hex-blob",
            "--default-character-set=utf8mb4",
            "-h",
            url.host or "localhost",
            "-P",
            str(url.port or 3306),
            "-u",
            url.username or "",
            url.database or "",
        ]
        environment = dict(__import__("os").environ)
        if url.password:
            environment["MYSQL_PWD"] = url.password
        with gzip.open(destination, "wb", compresslevel=6) as output:
            completed = subprocess.run(
                command,
                stdout=output,
                stderr=subprocess.PIPE,
                env=environment,
                check=False,
                timeout=900,
            )
        if completed.returncode != 0:
            destination.unlink(missing_ok=True)
            error = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"mysqldump thất bại: {error[:500]}")
    elif settings.is_sqlite:
        database_path = Path(url.database or "")
        if not database_path.exists():
            raise RuntimeError("Không tìm thấy tệp cơ sở dữ liệu SQLite.")
        with database_path.open("rb") as source, gzip.open(destination, "wb", compresslevel=6) as output:
            shutil.copyfileobj(source, output)
    else:
        raise RuntimeError("Cơ chế backup hiện chỉ hỗ trợ MySQL/XAMPP và SQLite.")

    if not destination.exists() or destination.stat().st_size < 128:
        destination.unlink(missing_ok=True)
        raise RuntimeError("Backup không hợp lệ hoặc tệp rỗng.")
    # The extension promises a gzip stream. Refuse to publish a misleading
    # backup file so restore tooling can safely select the correct reader.
    with destination.open("rb") as stream:
        if stream.read(2) != b"\x1f\x8b":
            destination.unlink(missing_ok=True)
            raise RuntimeError("Backup file is not a valid gzip stream.")

    checksum = _write_checksum(destination)

    if keep_last > 0:
        backups = sorted(BACKUP_DIR.glob("sealink_*.gz"), key=lambda item: item.stat().st_mtime, reverse=True)
        for old in backups[keep_last:]:
            old.unlink(missing_ok=True)
            old.with_suffix(old.suffix + ".sha256").unlink(missing_ok=True)

    return {
        "name": destination.name,
        "size_bytes": destination.stat().st_size,
        "created_at": datetime.fromtimestamp(destination.stat().st_mtime, tz=timezone.utc).isoformat(),
        "sha256": checksum,
    }


if __name__ == "__main__":
    print(json.dumps(create_backup(), ensure_ascii=False))
