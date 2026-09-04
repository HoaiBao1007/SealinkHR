import gzip

import pytest

from app.services import backup_service


def _backup(tmp_path, name: str = "sealink_20260814_101500.sql.gz"):
    path = tmp_path / name
    with gzip.open(path, "wb") as stream:
        stream.write(b"-- MySQL dump\nCREATE TABLE sample (id INT);\n")
    backup_service._write_checksum(path)
    return path


def test_only_verified_application_backup_can_be_resolved(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
    backup = _backup(tmp_path)

    resolved = backup_service.get_backup_file(backup.name, verify=True)

    assert resolved == backup
    assert backup_service.restore_confirmation_phrase(backup.name) == f"RESTORE {backup.name}"
    assert backup_service.list_backups()[0]["name"] == backup.name

    with pytest.raises(FileNotFoundError):
        backup_service.get_backup_file("..\\outside.sql.gz")


def test_corrupted_or_unchecked_backup_is_rejected_before_restore(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
    backup = _backup(tmp_path)
    with backup.open("ab") as stream:
        stream.write(b"tampered")

    with pytest.raises(backup_service.BackupValidationError, match="SHA-256"):
        backup_service.get_backup_file(backup.name, verify=True)


def test_it_admin_can_download_existing_backup_without_path_traversal(client, tmp_path, monkeypatch):
    from app.api.deps import get_it_admin_user
    from app.main import app
    from app.models.user import User

    monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
    backup = _backup(tmp_path)
    app.dependency_overrides[get_it_admin_user] = lambda: User(id=987, username="it.backup", role="IT_ADMIN")

    downloaded = client.get(f"/api/it/backups/{backup.name}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == backup.read_bytes()
    assert backup.name in downloaded.headers.get("content-disposition", "")

    traversal = client.get("/api/it/backups/..%2Foutside.sql.gz/download")
    assert traversal.status_code in {404, 422}
