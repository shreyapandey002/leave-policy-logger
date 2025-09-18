from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional

class LeaveRequest(BaseModel):
    email: str
    name: str
    start_date: datetime
    end_date: datetime
    days: int
    description: str
    connected_account_id: Optional[str] = None

    @field_validator("start_date", "end_date", mode="before")
    def parse_date(cls, value):
        if isinstance(value, str):
            for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
            raise ValueError("Date must be in format DD-MM-YYYY or YYYY-MM-DD")
        return value


class LeaveResponse(BaseModel):
    name: str
    email: str
    start_date: datetime
    end_date: datetime
    days: int
    description: str
    leaves_left: int
    status: str
