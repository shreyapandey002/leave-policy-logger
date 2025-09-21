from sqlalchemy.orm import Session
from sqlalchemy import func
from . import models


def upsert_draft(db: Session, draft_data: dict):
    """
    Insert or update a leave draft.
    """
    draft = db.query(models.LeaveDraft).filter(models.LeaveDraft.email == draft_data["email"]).first()
    if draft:
        for key, value in draft_data.items():
            setattr(draft, key, value if value is not None else getattr(draft, key))
    else:
        draft = models.LeaveDraft(**draft_data)
        db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def delete_draft(db: Session, email: str):
    db.query(models.LeaveDraft).filter(models.LeaveDraft.email == email).delete()
    db.commit()


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
