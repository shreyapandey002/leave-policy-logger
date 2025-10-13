from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class LeaveRequest(BaseModel):
    email: str
    name: str
    start_date: datetime
    end_date: datetime
    days: int
    description: str


class LeaveResponse(BaseModel):
    name: str
    email: str
    start_date: datetime
    end_date: datetime
    days: int
    description: str
    leaves_left: int
    status: str
