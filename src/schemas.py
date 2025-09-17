from pydantic import BaseModel
from datetime import datetime

from pydantic import BaseModel, field_validator
from datetime import datetime

class LeaveRequest(BaseModel):
    email: str
    name: str
    start_date: datetime
    end_date: datetime
    days: int
    description: str
    connected_account_id: str

    @field_validator("start_date", "end_date", mode="before")
    def parse_date(cls, value):
        if isinstance(value, str):
            try:
                # Parse DD-MM-YYYY
                return datetime.strptime(value, "%d-%m-%Y")
            except ValueError:
                raise ValueError("Date must be in format DD-MM-YYYY")
        return value


class LeaveResponse(BaseModel):
    name: str
    email: str
    start_date: datetime
    end_date: datetime
    days: int
    description: str
    leaves_left: int
