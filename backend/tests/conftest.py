from collections.abc import Generator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import (
    get_admin_employee_actor,
    get_admin_user,
    get_attendance_employee_actor,
    get_current_user,
    get_db,
)
from app.main import app
from app.db.base import Base
from app.models import (
    AttendanceDaily,
    AttendanceLog,
    AttendanceOverrideAudit,
    Employee,
    OffRequest,
    OffRequestAttachment,
    Timesheet,
    TimesheetEntry,
    TimesheetPeriod,
    UploadBatch,
    User,
    SystemAuditEvent,
    TrustedDevice,
    MonthlySalaryInput,
    Notification,
    NotificationRead,
    OnboardingAttachment,
    OnboardingFormVersion,
    OnboardingSubmission,
    OffboardingAction,
    OffboardingAttachment,
    OffboardingFormVersion,
    OffboardingRequest,
    SalaryApprovalWorkflow,
)


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_database() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    db = TestingSessionLocal()
    try:
        # Commission tables have RESTRICT foreign keys and must be cleared in
        # dependency order. Keeping this isolation here prevents a wallet test
        # from leaking its financial rows into salary tests (and vice versa).
        from app.models.commission import (
            CommissionBonusLock,
            CommissionBonusEntitlement,
            CommissionCalculationSnapshot,
            CommissionJob,
            CommissionJobReceivableAttachment,
            CommissionJobReceivableLink,
            CommissionPayoutPolicy,
            CommissionPayoutSchedule,
            CommissionPayoutScheduleAllocation,
            CommissionPaymentVerification,
            CommissionPeriod,
            CommissionRepOverride,
            CommissionWalletLedger,
        )
        from app.models.off_request import ApprovalAction
        db.execute(delete(CommissionPayoutScheduleAllocation))
        db.execute(delete(CommissionWalletLedger))
        db.execute(delete(CommissionPaymentVerification))
        db.execute(delete(CommissionBonusLock))
        db.execute(delete(CommissionJobReceivableLink))
        db.execute(delete(CommissionJobReceivableAttachment))
        db.execute(delete(CommissionPayoutSchedule))
        db.execute(delete(CommissionBonusEntitlement))
        db.execute(delete(CommissionCalculationSnapshot))
        db.execute(delete(CommissionRepOverride))
        db.execute(delete(CommissionJob))
        db.execute(delete(CommissionPeriod))
        db.execute(delete(CommissionPayoutPolicy))
        db.execute(delete(NotificationRead))
        db.execute(delete(Notification))
        db.execute(delete(OnboardingAttachment))
        db.execute(delete(OnboardingSubmission))
        db.execute(delete(OnboardingFormVersion))
        db.execute(delete(OffboardingAttachment))
        db.execute(delete(OffboardingAction))
        db.execute(delete(OffboardingRequest))
        db.execute(delete(OffboardingFormVersion))
        db.execute(delete(SystemAuditEvent))
        db.execute(delete(TrustedDevice))
        db.execute(delete(AttendanceOverrideAudit))
        db.execute(delete(TimesheetEntry))
        db.execute(delete(Timesheet))
        db.execute(delete(TimesheetPeriod))
        db.execute(delete(AttendanceDaily))
        db.execute(delete(AttendanceLog))
        db.execute(delete(UploadBatch))
        db.execute(delete(ApprovalAction))
        db.execute(delete(OffRequestAttachment))
        db.execute(delete(OffRequest))
        from app.models.salary_decision import SalaryDecision
        from app.models.department import Department
        from app.models.department_bonus_config import DepartmentBonusConfig
        from app.models.organization import OrganizationAssignment, OrganizationUnit
        db.execute(delete(OrganizationAssignment))
        db.execute(delete(OrganizationUnit))
        db.execute(delete(DepartmentBonusConfig))
        db.execute(delete(Department))
        db.execute(delete(SalaryApprovalWorkflow))
        db.execute(delete(MonthlySalaryInput))
        db.execute(delete(SalaryDecision))
        db.execute(delete(Employee))
        db.execute(delete(User))
        db.commit()
        yield
    finally:
        db.close()


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    def _override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    
    # Mock authentication for existing test suites
    mock_admin = User(id=9999, username="test_mock_admin", role="ADMIN")
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    app.dependency_overrides[get_admin_user] = lambda: mock_admin

    def _mock_admin_actor() -> Employee:
        db = TestingSessionLocal()
        try:
            return (
                db.query(Employee).filter(Employee.machine_employee_id == "M001").first()
                or db.query(Employee).first()
                or Employee(id=9999, machine_employee_id="TEST_ADMIN", full_name="Test Admin")
            )
        finally:
            db.close()

    app.dependency_overrides[get_admin_employee_actor] = _mock_admin_actor
    app.dependency_overrides[get_attendance_employee_actor] = _mock_admin_actor

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seed_basic_employees(db_session: Session) -> dict[str, Employee]:
    uploader = Employee(
        machine_employee_id="U001",
        full_name="Uploader User",
        department_code="HR",
        department_name="Human Resource",
        annual_leave_quota=12,
        annual_leave_used=0,
        paid_leave_balance=0,
        unpaid_leave_balance=0,
        is_active=True,
    )
    worker = Employee(
        machine_employee_id="E001",
        full_name="Nguyen Van A",
        department_code="OPS",
        department_name="Operations",
        annual_leave_quota=12,
        annual_leave_used=0,
        paid_leave_balance=0,
        unpaid_leave_balance=0,
        is_active=True,
    )
    approver = Employee(
        machine_employee_id="M001",
        full_name="Manager B",
        department_code="MGT",
        department_name="Management",
        annual_leave_quota=12,
        annual_leave_used=0,
        paid_leave_balance=0,
        unpaid_leave_balance=0,
        is_active=True,
    )
    db_session.add_all([uploader, worker, approver])
    db_session.commit()
    db_session.refresh(uploader)
    db_session.refresh(worker)
    db_session.refresh(approver)
    return {"uploader": uploader, "worker": worker, "approver": approver}


@pytest.fixture
def seed_timesheet_data(db_session: Session, seed_basic_employees: dict[str, Employee]) -> dict[str, object]:
    worker = seed_basic_employees["worker"]
    period_start = date(2026, 4, 23)
    period_end = date(2026, 5, 22)
    timesheet = Timesheet(
        period_start=period_start,
        period_end=period_end,
        employee_id=worker.id,
        total_work_days=20,
        total_late_minutes=30,
        total_absent_days=1,
        total_paid_leave_days=1,
        total_unpaid_leave_days=0,
        total_business_trip_days=0,
        approval_status="draft",
    )
    db_session.add(timesheet)
    db_session.commit()
    db_session.refresh(timesheet)
    return {"timesheet": timesheet, "period_start": period_start, "period_end": period_end}
