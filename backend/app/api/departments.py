from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_admin_user
from app.models.department import Department
from app.models.employee import Employee
from app.api.employees import EmployeeResponse
from app.services.access_role_service import sync_all_employee_access_roles
from app.services.salary import FIXED_NON_SALES_BONUS_RULES, is_sales_bonus_department
from app.services.employee_visibility import is_current_employee

router = APIRouter(tags=["departments"], dependencies=[Depends(get_admin_user)])

class DepartmentCreate(BaseModel):
    name: str
    manager_id: Optional[int] = None
    parent_id: Optional[int] = None
    sort_order: int = 0

class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    manager_id: Optional[int] = None
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None

class EmployeeMinimal(BaseModel):
    id: int
    full_name: str
    notion_name: Optional[str] = None
    position: Optional[str] = None

class DepartmentResponse(BaseModel):
    id: int
    name: str
    manager_id: Optional[int] = None
    parent_id: Optional[int] = None
    sort_order: int = 0
    manager: Optional[EmployeeMinimal] = None
    employees: List[EmployeeMinimal] = []
    current_bonus_rules: List[dict] = []

    model_config = {"from_attributes": True}

class SetDepartmentEmployeesRequest(BaseModel):
    employee_ids: List[int]

@router.get("/api/departments", response_model=List[DepartmentResponse])
def get_departments(db: Session = Depends(get_db)):
    departments = db.query(Department).options(
        joinedload(Department.manager),
        joinedload(Department.employees)
    ).all()
    
    from app.services.salary import get_active_department_rules
    from datetime import datetime
    
    current_period = datetime.now().strftime("%Y-%m")
    
    result = []
    for dept in departments:
        rules = get_active_department_rules(db, dept.id, current_period)
        current_manager = dept.manager if dept.manager and is_current_employee(dept.manager) else None
        dept_dict = {
            "id": dept.id,
            "name": dept.name,
            "manager_id": dept.manager_id,
            "parent_id": dept.parent_id,
            "sort_order": dept.sort_order,
            "manager": current_manager,
            "employees": [employee for employee in dept.employees if is_current_employee(employee)],
            "current_bonus_rules": rules
        }
        result.append(dept_dict)
    return result

@router.post("/api/departments", response_model=DepartmentResponse)
def create_department(data: DepartmentCreate, db: Session = Depends(get_db)):
    db_dept = db.query(Department).filter(Department.name == data.name).first()
    if db_dept:
        raise HTTPException(status_code=400, detail="Department with this name already exists")
    
    if data.parent_id is not None:
        parent = db.query(Department).filter(Department.id == data.parent_id).first()
        if parent is None:
            raise HTTPException(status_code=400, detail="Parent department not found")

    new_dept = Department(
        name=data.name,
        manager_id=data.manager_id,
        parent_id=data.parent_id,
        sort_order=data.sort_order,
    )
    db.add(new_dept)
    db.commit()
    db.refresh(new_dept)
    return new_dept

@router.put("/api/departments/{dept_id}", response_model=DepartmentResponse)
def update_department(dept_id: int, data: DepartmentUpdate, db: Session = Depends(get_db)):
    db_dept = db.query(Department).filter(Department.id == dept_id).first()
    if not db_dept:
        raise HTTPException(status_code=404, detail="Department not found")
    
    if data.name is not None:
        existing = db.query(Department).filter(Department.name == data.name, Department.id != dept_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Another department with this name already exists")
        db_dept.name = data.name
        
    if data.manager_id is not None:
        db_dept.manager_id = data.manager_id
    if "parent_id" in data.model_fields_set:
        if data.parent_id == dept_id:
            raise HTTPException(status_code=400, detail="Department cannot be its own parent")
        if data.parent_id is not None:
            parent = db.query(Department).filter(Department.id == data.parent_id).first()
            if parent is None:
                raise HTTPException(status_code=400, detail="Parent department not found")
            ancestor = parent
            while ancestor is not None:
                if ancestor.id == dept_id:
                    raise HTTPException(status_code=400, detail="Department hierarchy cannot contain a cycle")
                ancestor = ancestor.parent
        db_dept.parent_id = data.parent_id
    if data.sort_order is not None:
        db_dept.sort_order = data.sort_order

    db.commit()
    db.refresh(db_dept)
    return db_dept

@router.delete("/api/departments/{dept_id}")
def delete_department(dept_id: int, db: Session = Depends(get_db)):
    db_dept = db.query(Department).filter(Department.id == dept_id).first()
    if not db_dept:
        raise HTTPException(status_code=404, detail="Department not found")
    
    # Detach employees from this department before deleting or let SET NULL handle it
    # Because of `ondelete="SET NULL"`, the DB will handle it.
    db.delete(db_dept)
    db.commit()
    return {"message": "Department deleted"}

@router.put("/api/departments/{dept_id}/employees")
def set_department_employees(dept_id: int, data: SetDepartmentEmployeesRequest, db: Session = Depends(get_db)):
    db_dept = db.query(Department).filter(Department.id == dept_id).first()
    if not db_dept:
        raise HTTPException(status_code=404, detail="Department not found")
    
    # Unassign all employees currently in this department
    db.query(Employee).filter(Employee.department_id == dept_id).update({Employee.department_id: None})
    
    # Assign the new employees
    if data.employee_ids:
        db.query(Employee).filter(Employee.id.in_(data.employee_ids)).update({Employee.department_id: dept_id}, synchronize_session=False)

    db.flush()
    db.expire_all()
    sync_all_employee_access_roles(db)
    db.commit()
    return {"message": "Employees assigned successfully"}


from app.models.department_bonus_config import DepartmentBonusConfig

class BonusRule(BaseModel):
    min: float
    max: float
    rate: float

class DepartmentBonusConfigRequest(BaseModel):
    period: str  # YYYY-MM
    end_period: Optional[str] = None # YYYY-MM
    rules: List[BonusRule]

class DepartmentBonusConfigResponse(BaseModel):
    id: Optional[int] = None
    department_id: int
    period: str
    end_period: Optional[str] = None
    rules: List[BonusRule]

    class Config:
        orm_mode = True

DEFAULT_BONUS_RULES = [
    {"min": 0, "max": 2.0, "rate": 0.0},
    {"min": 2.01, "max": 4.0, "rate": 0.20},
    {"min": 4.01, "max": 6.0, "rate": 0.25},
    {"min": 6.01, "max": 8.0, "rate": 0.30},
    {"min": 8.01, "max": 999.0, "rate": 0.35}
]

@router.get("/api/departments/all-bonus-configs")
def get_all_bonus_configs(period: str, db: Session = Depends(get_db)):
    """
    Fetch active bonus rules for ALL departments for a specific period (YYYY-MM).
    """
    departments = db.query(Department).all()
    results = []
    
    from app.services.salary import get_active_department_rules
    for dept in departments:
        rules = get_active_department_rules(db, dept.id, period)
        results.append({
            "department_id": dept.id,
            "department_name": dept.name,
            "rules": rules
        })
    return results

@router.get("/api/departments/{dept_id}/bonus-config", response_model=DepartmentBonusConfigResponse)
def get_department_bonus_config(
    dept_id: int,
    period: str,  # YYYY-MM
    db: Session = Depends(get_db)
):
    db_dept = db.query(Department).filter(Department.id == dept_id).first()
    if not db_dept:
        raise HTTPException(status_code=404, detail="Department not found")

    if not is_sales_bonus_department(db_dept.name):
        return {
            "department_id": dept_id,
            "period": period,
            "end_period": None,
            "rules": [dict(rule) for rule in FIXED_NON_SALES_BONUS_RULES],
        }
        
    # Get config for the matching period or closest past period
    config = (
        db.query(DepartmentBonusConfig)
        .filter(
            DepartmentBonusConfig.department_id == dept_id,
            DepartmentBonusConfig.period <= period
        )
        .order_by(DepartmentBonusConfig.period.desc())
        .first()
    )
    
    if not config:
        # Return default config mapped to the requested period
        return {
            "department_id": dept_id,
            "period": period,
            "end_period": None,
            "rules": DEFAULT_BONUS_RULES
        }
        
    return {
        "id": config.id,
        "department_id": config.department_id,
        "period": period,  # Return the requested period
        "rules": config.rules
    }

@router.post("/api/departments/{dept_id}/bonus-config", response_model=DepartmentBonusConfigResponse)
def save_department_bonus_config(
    dept_id: int,
    data: DepartmentBonusConfigRequest,
    db: Session = Depends(get_db)
):
    db_dept = db.query(Department).filter(Department.id == dept_id).first()
    if not db_dept:
        raise HTTPException(status_code=404, detail="Department not found")

    rules_to_save = (
        [rule.model_dump() for rule in data.rules]
        if is_sales_bonus_department(db_dept.name)
        else [dict(rule) for rule in FIXED_NON_SALES_BONUS_RULES]
    )
        
    # Check if a config already exists for this exact period
    existing = db.query(DepartmentBonusConfig).filter(
        DepartmentBonusConfig.department_id == dept_id,
        DepartmentBonusConfig.period == data.period
    ).first()
    
    if existing:
        existing.rules = rules_to_save
        existing.end_period = data.end_period
        db.commit()
        db.refresh(existing)
        return existing
        
    new_config = DepartmentBonusConfig(
        department_id=dept_id,
        period=data.period,
        end_period=data.end_period,
        rules=rules_to_save
    )
    db.add(new_config)
    db.commit()
    db.refresh(new_config)
    return new_config
