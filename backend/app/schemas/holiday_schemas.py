from pydantic import BaseModel, Field
from datetime import date
from typing import Optional

class HolidaySettingBase(BaseModel):
    holiday_name: str = Field(..., max_length=255)
    holiday_date: date
    is_custom: bool = False

class HolidaySettingCreate(HolidaySettingBase):
    pass

class HolidaySettingUpdate(BaseModel):
    holiday_name: Optional[str] = None
    holiday_date: Optional[date] = None
    is_custom: Optional[bool] = None

class HolidaySettingResponse(HolidaySettingBase):
    id: int
    is_locked: bool = False

    model_config = {"from_attributes": True}

class HolidaySettingBulkCreate(BaseModel):
    holiday_name: str = Field(..., max_length=255)
    start_date: date
    end_date: date
    is_custom: bool = False
