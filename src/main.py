from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, Dict, Any
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

# --- In-memory draft store (like onboarding agent)
draft_store: Dict[str, Dict[str, Any]] = {}

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
def init_leave(email: str):
    if email not in draft_store:
        draft_store[email] = {
            "email": email,
            "name": None,
            "start_date": None,
            "end_date": None,
            "days": None,
            "description": None
        }
    return {"status": "drafting", "current_draft": draft_store[email]}

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
    description: Optional[str] = None
):
    if email not in draft_store:
        raise HTTPException(status_code=404, detail="Draft not found. Call /init first.")

    draft = draft_store[email]
    if name: draft["name"] = name
    if start_date: draft["start_date"] = datetime.strptime(start_date, "%d-%m-%Y")
    if end_date: draft["end_date"] = datetime.strptime(end_date, "%d-%m-%Y")
    if days is not None: draft["days"] = days
    if description: draft["description"] = description

    missing = [k for k, v in draft.items() if v is None and k != "email"]
    status = "drafting" if missing else "ready"
    return {"status": status, "missing_fields": missing, "current_draft": draft}

# ----------------------
# 3️⃣ SUBMIT LEAVE
# ----------------------
@app.post("/leaves/submit")
def submit_leave(email: str, db: Session = Depends(get_db)):
    if email not in draft_store:
        raise HTTPException(status_code=404, detail="Draft not found. Call /init first.")

    draft = draft_store[email]
    missing = [k for k, v in draft.items() if v is None and k != "email"]
    if missing:
        return {"status": "drafting", "missing_fields": missing}

    employee = crud.get_or_create_employee(db, email=draft["email"], name=draft["name"])
    leaves_left = crud.calculate_leaves_left(db, employee.id, employee.total_leaves)

    if draft["days"] > leaves_left:
        return {"status": "rejected", "message": "Not enough leave balance", "leaves_left": leaves_left}

    leave = crud.apply_leave(
        db=db,
        employee_id=employee.id,
        start_date=draft["start_date"],
        end_date=draft["end_date"],
        days=draft["days"],
        description=draft["description"]
    )

    # Notify HR
    body = (
        f"Name: {employee.name}\nEmail: {employee.email}\n"
        f"Start: {leave.start_date}\nEnd: {leave.end_date}\n"
        f"Days: {leave.days}\nReason: {leave.description}\n"
        f"Leaves left before approval: {leaves_left}"
    )
    try: send_leave_email(HR_EMAIL, f"Leave Application - {employee.name}", body)
    except: pass

    # Remove draft
    del draft_store[email]

    return {"status": "submitted", "leaves_left": leaves_left, "leave_details": leave.__dict__}
