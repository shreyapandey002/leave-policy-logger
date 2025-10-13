from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime, date
from typing import Optional, List
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from . import models, crud, schemas
from .db import SessionLocal, engine

app = FastAPI()
models.Base.metadata.create_all(bind=engine)

# --- Mail config ---
MAILTRAP_HOST = os.getenv("MAILTRAP_HOST")
MAILTRAP_PORT = int(os.getenv("MAILTRAP_PORT", 587))
MAILTRAP_USER = os.getenv("MAILTRAP_USER")
MAILTRAP_PASS = os.getenv("MAILTRAP_PASS")
HR_EMAIL = os.getenv("HR_EMAIL", "hr@example.com")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def send_leave_email(to_email: str, subject: str, body: str):
    msg = MIMEMultipart()
    msg["From"] = MAILTRAP_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(MAILTRAP_HOST, MAILTRAP_PORT) as server:
            server.starttls()
            server.login(MAILTRAP_USER, MAILTRAP_PASS)
            server.send_message(msg)
        return {"status": "sent"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

# ----------------------
# 1️⃣ INIT DRAFT
# ----------------------
@app.post("/leaves/init")
def init_leave(email: str, db: Session = Depends(get_db)):
    draft = db.query(models.LeaveDraft).filter(models.LeaveDraft.email == email).first()
    if not draft:
        draft = models.LeaveDraft(email=email)
        db.add(draft)
        db.commit()
        db.refresh(draft)
    return {
        "status": "drafting",
        "current_draft": {
            "email": draft.email,
            "name": draft.name,
            "start_date": draft.start_date,
            "end_date": draft.end_date,
            "days": draft.days,
            "description": draft.description
        }
    }

# ----------------------
# 2️⃣ UPDATE DRAFT
# ----------------------
@app.post("/leaves/update")
def update_leave(
    email: str,
    name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    days: Optional[int] = None,
    description: Optional[str] = None,
    db: Session = Depends(get_db)
):
    draft = db.query(models.LeaveDraft).filter(models.LeaveDraft.email == email).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found. Call /init first.")

    if name:
        draft.name = name
    if start_date:
        draft.start_date = datetime.fromisoformat(start_date) if 'T' in start_date else datetime.strptime(start_date, "%d-%m-%Y")
    if end_date:
        draft.end_date = datetime.fromisoformat(end_date) if 'T' in end_date else datetime.strptime(end_date, "%d-%m-%Y")
    if days is not None:
        draft.days = days
    if description:
        draft.description = description

    db.commit()
    db.refresh(draft)

    required_fields = ["name", "start_date", "end_date", "days", "description"]
    missing = [f for f in required_fields if getattr(draft, f) is None]

    if missing:
        return {
            "status": "drafting",
            "message": f"Waiting for: {missing}",
            "current_draft": {
                "email": draft.email,
                "name": draft.name,
                "start_date": draft.start_date,
                "end_date": draft.end_date,
                "days": draft.days,
                "description": draft.description
            }
        }
    else:
        return {
            "status": "ready",
            "message": "All fields filled. Call /submit to finalize leave.",
            "current_draft": {
                "email": draft.email,
                "name": draft.name,
                "start_date": draft.start_date,
                "end_date": draft.end_date,
                "days": draft.days,
                "description": draft.description
            }
        }

# ----------------------
# 3️⃣ SUBMIT LEAVE
# ----------------------
@app.post("/leaves/submit")
def submit_leave(email: str, db: Session = Depends(get_db)):
    draft = db.query(models.LeaveDraft).filter(models.LeaveDraft.email == email).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found. Call /init first.")

    # Check required fields
    required_fields = ["name", "start_date", "end_date", "days", "description"]
    missing = [f for f in required_fields if getattr(draft, f) is None]
    if missing:
        return {"status": "drafting", "message": f"Missing fields: {missing}"}

    # Ensure employee exists
    employee = db.query(models.Employee).filter(models.Employee.email == draft.email).first()
    if not employee:
        employee = models.Employee(name=draft.name, email=draft.email)
        db.add(employee)
        db.commit()
        db.refresh(employee)

    # Check leave balance
    leaves_left_before = crud.calculate_leaves_left(db, employee.id, employee.total_leaves)
    if draft.days > leaves_left_before:
        return {
            "status": "rejected",
            "message": "Not enough leave balance",
            "leaves_left": leaves_left_before
        }

    # Apply leave
    leave = crud.apply_leave(
        db=db,
        employee_id=employee.id,
        start_date=draft.start_date,
        end_date=draft.end_date,
        days=draft.days,
        description=draft.description
    )

    crud.delete_draft(db, draft.email)

    # Notify HR
    subject = f"Leave Application: {employee.name}"
    body = (
        f"Name: {employee.name}\n"
        f"Email: {employee.email}\n"
        f"Start Date: {leave.start_date}\n"
        f"End Date: {leave.end_date}\n"
        f"Days: {leave.days}\n"
        f"Description: {leave.description}\n"
        f"Leaves Left (before approval): {leaves_left_before}\n"
    )
    try:
        _ = send_leave_email(HR_EMAIL, subject, body)
    except Exception:
        pass

    return {
        "status": "submitted",
        "message": "Leave application finalized and submitted",
        "leaves_left": leaves_left_before
    }
