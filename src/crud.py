from sqlalchemy.orm import Session
from sqlalchemy import func
from . import models

def get_or_create_employee(db: Session, email: str, name: str):
    employee = db.query(models.Employee).filter(models.Employee.email == email).first()
    if not employee:
        employee = models.Employee(email=email, name=name)
        db.add(employee)
        db.commit()
        db.refresh(employee)
    return employee

def apply_leave(db: Session, employee_id: int, start_date, end_date, days: int, description: str):
    leave = models.LeaveApplication(
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
        days=days,
        description=description,
    )
    db.add(leave)
    db.commit()
    db.refresh(leave)
    return leave

def calculate_leaves_left(db: Session, employee_id: int, total_leaves: int):
    total_taken = db.query(models.LeaveApplication).filter(
        models.LeaveApplication.employee_id == employee_id
    ).with_entities(func.sum(models.LeaveApplication.days)).scalar() or 0
    return total_leaves - total_taken
