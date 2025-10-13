from sqlalchemy.orm import Session
from sqlalchemy import func
from . import models
from datetime import datetime

def get_or_create_employee(db: Session, email: str, name: str = None):
    employee = db.query(models.Employee).filter(models.Employee.email == email).first()
    if not employee:
        employee = models.Employee(email=email, name=name)
        db.add(employee)
        db.commit()
        db.refresh(employee)
    return employee

def calculate_leaves_left(db: Session, employee_id: int):
    employee = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
    if not employee:
        return 0
    taken = db.query(func.sum(models.LeaveApplication.days)).filter(
        models.LeaveApplication.employee_id == employee_id
    ).scalar() or 0
    return employee.total_leaves - taken

def apply_leave(db: Session, employee_id: int, start_date: datetime, end_date: datetime, days: int, description: str):
    leave = models.LeaveApplication(
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
        days=days,
        description=description
    )
    db.add(leave)
    db.commit()
    db.refresh(leave)
    return leave
