from fastapi import FastAPI, Form, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from . import models, crud
from .db import SessionLocal, engine

app = FastAPI()
models.Base.metadata.create_all(bind=engine)

# --- Mail config ---
MAILTRAP_HOST = os.getenv("MAILTRAP_HOST")
MAILTRAP_PORT = int(os.getenv("MAILTRAP_PORT"))
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
def init_leave(email: str = Form(...), db: Session = next(get_db())):
    draft = crud.get_draft(db, email)
    if not draft:
        draft = crud.create_draft(db, email)
    return {
        "status": "drafting",
        "current_draft": draft
    }

# ----------------------
# 2️⃣ UPDATE DRAFT
# ----------------------
@app.post("/leaves/update")
def update_leave(
    email: str = Form(...),
    name: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    days: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = next(get_db())
):
    draft = crud.get_draft(db, email)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found. Call /init first.")

    draft_data = {
        "name": name,
        "start_date": start_date,
        "end_date": end_date,
        "days": days,
        "description": description
    }
    draft = crud.update_draft(db, email, draft_data)

    # Check missing fields
    required_fields = ["name", "start_date", "end_date", "days", "description"]
    missing = [f for f in required_fields if not draft[f]]

    status = "drafting" if missing else "ready"
    message = f"Waiting for: {missing}" if missing else "All fields filled. Call /submit to finalize leave."

    return {
        "status": status,
        "message": message,
        "current_draft": draft
    }

# ----------------------
# 3️⃣ SUBMIT LEAVE
# ----------------------
@app.post("/leaves/submit")
def submit_leave(email: str = Form(...), db: Session = next(get_db())):
    draft = crud.get_draft(db, email)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found. Call /init first.")

    # Check required fields
    required_fields = ["name", "start_date", "end_date", "days", "description"]
    missing = [f for f in required_fields if not draft[f]]
    if missing:
        return {"status": "drafting", "message": f"Missing fields: {missing}"}

    # Ensure employee exists
    employee = crud.get_or_create_employee(db, draft)

    # Check leave balance
    leaves_left_before = crud.calculate_leaves_left(db, employee.id)
    if draft["days"] > leaves_left_before:
        return {"status": "rejected", "message": "Not enough leave balance", "leaves_left": leaves_left_before}

    # Apply leave
    leave = crud.apply_leave(db, employee.id, draft)

    # Delete draft
    crud.delete_draft(db, email)

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

    return {"status": "submitted", "message": "Leave application finalized and submitted", "leaves_left": leaves_left_before}
