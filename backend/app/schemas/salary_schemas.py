from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field

class EmployeeSalaryUpdate(BaseModel):
    employee_code: Optional[str] = Field(default=None, max_length=50)
    fullname: Optional[str] = Field(default=None, max_length=150)
    position: Optional[str] = Field(default=None, max_length=150)
    contract_salary: Optional[int] = Field(default=None, ge=0)
    employee_type: Optional[Literal["FULLTIME", "PROBATION", "INTERN", "TRAINEE"]] = None
    dependents_count: Optional[int] = Field(default=None, ge=0)
    account_number: Optional[str] = Field(default=None, max_length=50)
    bank_name: Optional[str] = Field(default=None, max_length=150)

class EmployeeSalaryResponse(BaseModel):
    id: int
    machine_employee_id: str
    employee_code: Optional[str]
    fullname: str
    position: Optional[str]
    contract_salary: int
    employee_type: str
    dependents_count: int
    account_number: Optional[str]
    bank_name: Optional[str]
    is_mid_month_change: bool = False
    prorated_old_salary: Optional[int] = None
    prorated_new_salary: Optional[int] = None
    prorated_days_old: Optional[float] = None
    prorated_days_new: Optional[float] = None
    mid_month_effective_date: Optional[str] = None

    class Config:
        from_attributes = True

class MonthlySalaryInputCreate(BaseModel):
    employee_id: int
    salary_period: str = Field(pattern=r"^\d{4}-\d{2}$")  # e.g., '2026-05'
    actual_working_days: float = Field(default=0.0, ge=0.0)
    meal_allowance_free: int = Field(default=0, ge=0)
    meal_allowance_tax: int = Field(default=0, ge=0)
    phone_allowance_free: int = Field(default=0, ge=0)
    trans_allowance_tax: int = Field(default=0, ge=0)
    perf_allowance_tax: int = Field(default=0, ge=0)
    other_income: int = Field(default=0, ge=0)
    bonus: int = Field(default=0, ge=0)
    advance_payment: int = Field(default=0, ge=0)
    pit_refund: int = Field(default=0, ge=0)
    other_deductions: int = Field(default=0, ge=0)
    bonus_14: int = Field(default=0, ge=0)

class MonthlySalaryInputUpdate(BaseModel):
    actual_working_days: Optional[float] = Field(default=None, ge=0.0)
    meal_allowance_free: Optional[int] = Field(default=None, ge=0)
    meal_allowance_tax: Optional[int] = Field(default=None, ge=0)
    phone_allowance_free: Optional[int] = Field(default=None, ge=0)
    trans_allowance_tax: Optional[int] = Field(default=None, ge=0)
    perf_allowance_tax: Optional[int] = Field(default=None, ge=0)
    other_income: Optional[int] = Field(default=None, ge=0)
    bonus: Optional[int] = Field(default=None, ge=0)
    advance_payment: Optional[int] = Field(default=None, ge=0)
    pit_refund: Optional[int] = Field(default=None, ge=0)
    other_deductions: Optional[int] = Field(default=None, ge=0)
    bonus_14: Optional[int] = Field(default=None, ge=0)

class MonthlySalaryInputResponse(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    salary_period: str
    actual_working_days: float
    meal_allowance_free: int
    meal_allowance_tax: int
    phone_allowance_free: int
    trans_allowance_tax: int
    perf_allowance_tax: int
    other_income: int
    other_income_note: Optional[str] = None
    other_income_document_name: Optional[str] = None
    other_income_document_content_type: Optional[str] = None
    other_income_document_size: Optional[int] = None
    other_income_document_uploaded_at: Optional[datetime] = None
    bonus: int
    advance_payment: int
    pit_refund: int
    other_deductions: int
    bonus_14: int
    is_published: bool = False
    # Commission wallet entries may retain a fractional VND remainder after
    # proportional JOB allocation. Keep two decimals end-to-end; truncating at
    # this response layer creates a mismatch with the immutable ledger.
    sales_bonus: Optional[float] = 0
    is_mid_month_change: bool = False
    prorated_old_salary: Optional[int] = None
    prorated_new_salary: Optional[int] = None
    prorated_days_old: Optional[float] = None
    prorated_days_new: Optional[float] = None
    mid_month_effective_date: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
