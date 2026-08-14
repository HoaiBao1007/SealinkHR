from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    manager = relationship("Employee", foreign_keys=[manager_id], backref="managed_departments")
    parent = relationship(
        "Department",
        remote_side=[id],
        foreign_keys=[parent_id],
        back_populates="children",
    )
    children = relationship(
        "Department",
        foreign_keys=[parent_id],
        back_populates="parent",
        order_by="Department.sort_order",
    )
    employees = relationship("Employee", foreign_keys="Employee.department_id", back_populates="department")
    bonus_configs = relationship("DepartmentBonusConfig", back_populates="department", cascade="all, delete-orphan")
