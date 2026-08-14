from sqlalchemy import String, ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class DepartmentBonusConfig(Base):
    __tablename__ = "department_bonus_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # YYYY-MM
    end_period: Mapped[str] = mapped_column(String(7), nullable=True, index=True)  # YYYY-MM
    rules: Mapped[list] = mapped_column(JSON, nullable=False)  # JSON array of tiers

    department = relationship("Department", back_populates="bonus_configs")
