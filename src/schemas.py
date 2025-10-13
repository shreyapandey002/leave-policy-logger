from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime

class LeaveDraft(BaseModel):
    email: str
    name: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    days: Optional[int] = None
    description: Optional[str] = None

    @validator("start_date", "end_date", pre=True)
    def parse_date(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
                try:
                    return datetime.strptime(v, fmt)
                except ValueError:
                    continue
            raise ValueError("Invalid date format")
        return v

class LeaveRequest(BaseModel):
    email: str
    name: str
    start_date: datetime
    end_date: datetime
    days: int
    description: str
