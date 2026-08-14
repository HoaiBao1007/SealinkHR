from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.settings import settings

if settings.is_sqlite:
    # SQLite: portable mode — no server needed
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},  # required for FastAPI multi-thread
    )
elif settings.is_mysql:
    # MySQL/MariaDB: XAMPP mode — charset utf8mb4 required for Vietnamese text
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=3600,  # recycle connections every hour to avoid MySQL timeout
    )
else:
    # PostgreSQL: production mode
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
