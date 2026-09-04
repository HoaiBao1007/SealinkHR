import gzip
import glob
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.settings import settings


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKUP_DIR = PROJECT_ROOT / "backups"
BACKUP_FILE_PATTERN = re.compile(r"sealink_[0-9]{8}_[0-9]{6}(?:_[0-9]+)?\.sql\.gz")
_backup_operation_lock = threading.RLock()


class BackupValidationError(RuntimeError):
    """Raised when a requested backup is unsafe or cannot be restored."""


def _mysqldump_path() -> str | None:
    candidates = [
        shutil.which("mariadb-dump"),
        shutil.which("mysqldump"),
    ]
    for pattern in (
        r"C:\Program Files\MariaDB *\bin\mariadb-dump.exe",
        r"C:\Program Files\MariaDB *\bin\mysqldump.exe",
        r"C:\Program Files\MySQL\MySQL Server *\bin\mysqldump.exe",
    ):
        candidates.extend(sorted(glob.glob(pattern), reverse=True))
    candidates.extend([
        r"D:\xampp\mysql\bin\mysqldump.exe",
        r"C:\xampp\mysql\bin\mysqldump.exe",
    ])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def _mysql_client_path() -> str | None:
    candidates = [
        shutil.which("mariadb"),
        shutil.which("mysql"),
    ]
    for pattern in (
        r"C:\Program Files\MariaDB *\bin\mariadb.exe",
        r"C:\Program Files\MariaDB *\bin\mysql.exe",
        r"C:\Program Files\MySQL\MySQL Server *\bin\mysql.exe",
    ):
        candidates.extend(sorted(glob.glob(pattern), reverse=True))
    candidates.extend([
        r"D:\xampp\mysql\bin\mysql.exe",
        r"C:\xampp\mysql\bin\mysql.exe",
    ])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_path(backup_name: str) -> Path:
    """Resolve only application-created backup names inside BACKUP_DIR."""
    if not BACKUP_FILE_PATTERN.fullmatch(backup_name):
        raise FileNotFoundError("Không tìm thấy bản backup hợp lệ.")
    root = BACKUP_DIR.resolve()
    candidate = (root / backup_name).resolve()
    if candidate.parent != root or not candidate.is_file():
        raise FileNotFoundError("Không tìm thấy bản backup.")
    return candidate


def _verify_backup(path: Path) -> dict:
    """Fully verify checksum and gzip integrity before a destructive restore."""
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    if not checksum_path.is_file():
        raise BackupValidationError("Bản backup thiếu tệp SHA-256 nên không thể khôi phục an toàn.")
    expected_checksum = checksum_path.read_text(encoding="ascii").strip().lower()
    actual_checksum = _sha256(path)
    if not expected_checksum or actual_checksum != expected_checksum:
        raise BackupValidationError("SHA-256 của bản backup không khớp. Không thực hiện khôi phục.")

    uncompressed_bytes = 0
    try:
        with gzip.open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                uncompressed_bytes += len(chunk)
    except (OSError, EOFError) as exc:
        raise BackupValidationError("Bản backup gzip không hợp lệ hoặc bị hỏng.") from exc
    if uncompressed_bytes < 32:
        raise BackupValidationError("Bản backup không có nội dung SQL hợp lệ.")
    return {
        "name": path.name,
        "sha256": actual_checksum,
        "size_bytes": path.stat().st_size,
        "uncompressed_bytes": uncompressed_bytes,
    }


def get_backup_file(backup_name: str, *, verify: bool = False) -> Path:
    path = _backup_path(backup_name)
    if verify:
        _verify_backup(path)
    return path


def restore_confirmation_phrase(backup_name: str) -> str:
    _backup_path(backup_name)
    return f"RESTORE {backup_name}"


def _new_backup_destination() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sequence = 0
    while True:
        suffix = "" if sequence == 0 else f"_{sequence}"
        candidate = BACKUP_DIR / f"sealink_{timestamp}{suffix}.sql.gz"
        if not candidate.exists():
            return candidate
        sequence += 1


def backup_capability() -> dict:
    driver = make_url(settings.database_url).drivername
    executable = _mysqldump_path() if settings.is_mysql else None
    restore_executable = _mysql_client_path() if settings.is_mysql else None
    return {
        "driver": driver,
        "ready": bool(executable) if settings.is_mysql else settings.is_sqlite,
        "tool": executable or ("safe file copy" if settings.is_sqlite else None),
        "restore_ready": bool(restore_executable) if settings.is_mysql else False,
        "restore_tool": restore_executable,
        "backup_directory": str(BACKUP_DIR),
    }


def list_backups() -> list[dict]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    backup_paths = (
        path for path in BACKUP_DIR.glob("sealink_*.gz")
        if BACKUP_FILE_PATTERN.fullmatch(path.name)
    )
    for path in sorted(backup_paths, key=lambda item: item.stat().st_mtime, reverse=True):
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
    value = _sha256(path)
    path.with_suffix(path.suffix + ".sha256").write_text(value, encoding="ascii")
    return value


def create_backup(*, keep_last: int = 30) -> dict:
    """Create a compressed, checksummed backup without exposing credentials."""
    with _backup_operation_lock:
        return _create_backup(keep_last=keep_last)


def _create_backup(*, keep_last: int) -> dict:
    destination = _new_backup_destination()
    url = make_url(settings.database_url)

    if settings.is_mysql:
        executable = _mysqldump_path()
        if not executable:
            raise RuntimeError("Không tìm thấy mariadb-dump/mysqldump trong MariaDB, MySQL, XAMPP hoặc PATH.")
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
        # subprocess writes directly to a file descriptor. Passing a GzipFile
        # as stdout bypasses its compressor and creates plain SQL with a
        # misleading .gz extension. Stream stdout through Python instead.
        with tempfile.TemporaryFile() as error_output:
            completed = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=error_output,
                env=environment,
            )
            try:
                if completed.stdout is None:
                    raise RuntimeError("Unable to capture mysqldump output.")
                with gzip.open(destination, "wb", compresslevel=6) as output:
                    shutil.copyfileobj(completed.stdout, output, length=1024 * 1024)
                completed.stdout.close()
                return_code = completed.wait(timeout=900)
            except BaseException:
                if completed.poll() is None:
                    completed.kill()
                    completed.wait()
                raise
            error_output.seek(0)
            error_bytes = error_output.read()

        if return_code != 0:
            destination.unlink(missing_ok=True)
            error = error_bytes.decode("utf-8", errors="replace").strip()
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
        is_gzip = stream.read(2) == b"\x1f\x8b"
    if not is_gzip:
        destination.unlink(missing_ok=True)
        raise RuntimeError("Backup file is not a valid gzip stream.")

    checksum = _write_checksum(destination)

    if keep_last > 0:
        backups = sorted(
            (path for path in BACKUP_DIR.glob("sealink_*.gz") if BACKUP_FILE_PATTERN.fullmatch(path.name)),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for old in backups[keep_last:]:
            old.unlink(missing_ok=True)
            old.with_suffix(old.suffix + ".sha256").unlink(missing_ok=True)

    return {
        "name": destination.name,
        "size_bytes": destination.stat().st_size,
        "created_at": datetime.fromtimestamp(destination.stat().st_mtime, tz=timezone.utc).isoformat(),
        "sha256": checksum,
    }


def _write_restore_manifest(payload: dict) -> None:
    """Persist an operational trace outside the restored database itself."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = BACKUP_DIR / f"restore_{timestamp}.json"
    destination.write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2), encoding="utf-8")


def _upgrade_schema_to_head() -> None:
    """Bring a restored historical backup forward to this deployed code version."""
    from alembic import command
    from alembic.config import Config

    config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "backend" / "migrations"))
    command.upgrade(config, "head")


def restore_backup(backup_name: str, *, actor: dict | None = None) -> dict:
    """Restore a verified, application-created MySQL backup.

    A fresh recovery-point backup is created before changing the database.
    This function intentionally never accepts an arbitrary path or SQL upload.
    """
    if not settings.is_mysql:
        raise RuntimeError("Khôi phục trên giao diện hiện chỉ hỗ trợ MySQL/MariaDB.")
    mysql_client = _mysql_client_path()
    if not mysql_client:
        raise RuntimeError("Không tìm thấy công cụ mysql để khôi phục database.")

    with _backup_operation_lock:
        selected_path = _backup_path(backup_name)
        selected = _verify_backup(selected_path)
        recovery_point = _create_backup(keep_last=0)
        url = make_url(settings.database_url)
        command = [
            mysql_client,
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

        manifest = {
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "action": "DATABASE_RESTORE",
            "actor": actor,
            "selected_backup": selected,
            "recovery_point": recovery_point,
            "status": "STARTED",
        }
        _write_restore_manifest(manifest)
        try:
            with tempfile.TemporaryFile() as error_output, gzip.open(selected_path, "rb") as source:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=error_output,
                    env=environment,
                )
                try:
                    if process.stdin is None:
                        raise RuntimeError("Không thể gửi dữ liệu backup đến MySQL.")
                    shutil.copyfileobj(source, process.stdin, length=1024 * 1024)
                    process.stdin.close()
                    return_code = process.wait(timeout=900)
                except BaseException:
                    if process.poll() is None:
                        process.kill()
                        process.wait()
                    raise
                error_output.seek(0)
                error_bytes = error_output.read()

            if return_code != 0:
                error = error_bytes.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"MySQL khôi phục thất bại: {error[:500]}")

            _upgrade_schema_to_head()
        except Exception as exc:
            manifest["status"] = "FAILED"
            manifest["error"] = str(exc)[:1000]
            _write_restore_manifest(manifest)
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(f"Khôi phục database thất bại: {str(exc)[:500]}") from exc

        manifest["status"] = "SUCCESS"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_restore_manifest(manifest)
        return {
            "restored_backup": selected,
            "recovery_point": recovery_point,
            "schema_upgraded_to_head": True,
        }


if __name__ == "__main__":
    print(json.dumps(create_backup(), ensure_ascii=False))
