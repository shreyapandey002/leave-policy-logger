from sqlalchemy.orm import Session
from . import models
from datetime import datetime

def apply_leave(db: Session, employee_id: int, start_date, end_date, days: int, description: str):
    leave = models.LeaveApplication(
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
        days=days,  # store days
        description=description
    )
    db.add(leave)
    db.commit()
    db.refresh(leave)
    return leave
