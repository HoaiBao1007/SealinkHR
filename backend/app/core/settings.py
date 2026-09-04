from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "SEALINK Attendance API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    # Must be supplied through .env or the deployment secret manager.
    secret_key: str
    token_expire_seconds: int = 3600
    it_admin_default_device_label: str = "70-A8-D3-1E-B5-4F"
    # Emergency/temporary bypass. Keep enabled by default and override only in
    # the deployment environment when IT_ADMIN must log in from any device.
    it_admin_trusted_device_required: bool = True
    trusted_device_cookie_secure: bool = False
    # Browsers cannot expose a client's physical MAC address to a web server.
    # When an IT administrator clears cookies or uses a private window, allow
    # the browser credential to be re-issued only from the already enrolled IP.
    trusted_device_allow_same_ip_recovery: bool = True
    initial_admin_password: str | None = None
    initial_user_password: str | None = None

    # Database — mặc định SQLite (portable, không cần Docker).
    # Để dùng PostgreSQL: set DATABASE_URL trong file .env
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "attendance"
    db_user: str = "attendance"
    db_password: str = "attendance"
    db_connect_timeout_seconds: int = 5
    database_url: str = "sqlite:///./sealink_attendance.db"

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
    cors_origin_regex: str = ""

    # Resolve the env file from the backend package instead of the process
    # working directory.  The API can be started from the repository root,
    # backend directory, VS Code, or a Windows service and must always read the
    # same configuration.
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        if len(value) < 32 or value.lower().startswith("replace-"):
            raise ValueError("SECRET_KEY phải là một chuỗi ngẫu nhiên có ít nhất 32 ký tự.")
        return value

    @property
    def is_sqlite(self) -> bool:
        """True when using SQLite (portable mode)."""
        return self.database_url.startswith("sqlite")

    @property
    def is_mysql(self) -> bool:
        """True when using MySQL/MariaDB (XAMPP mode)."""
        return "mysql" in self.database_url


settings = Settings()
