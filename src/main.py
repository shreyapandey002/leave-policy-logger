import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from datetime import datetime, date
import re

from .db import SessionLocal, engine
from . import models, crud, schemas

app = FastAPI()
models.Base.metadata.create_all(bind=engine)

# === Mailtrap / HR email config ===
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

def parse_freeform_input(text: str):
    """
    Parse freeform user input into structured leave data.
    Example inputs:
        "Shreya, shreya2002pandey@gmail.com"
        "shreya, shreya2002pandey@gmail.com, 1"
        "Rahul, rahul@example.com, 25-10-2025 to 27-10-2025, 3 days, personal trip"
    """
    result = {
        "name": None,
        "email": None,
        "start_date": None,
        "end_date": None,
        "days": None,
        "description": None
    }
    
    # Extract email first
    email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)
    if email_match:
        result["email"] = email_match.group()
        parts = text.split(result["email"])
        # Name = text before email
        result["name"] = parts[0].replace(",", "").strip() if parts[0] else None
        # Check if text after email is numeric (days) or description
        after_email = parts[1].replace(",", "").strip() if len(parts) > 1 else None
        if after_email:
            if after_email.isdigit():
                result["days"] = int(after_email)
            else:
                result["description"] = after_email
    else:
        # Fallback parsing
        parts = text.split(",")
        if parts:
            result["name"] = parts[0].strip()
            if len(parts) > 1:
                # If numeric, treat as days, else description
                second_part = parts[1].strip()
                result["days"] = int(second_part) if second_part.isdigit() else None
                result["description"] = second_part if not second_part.isdigit() else None

    # Extract dates (dd-mm-yyyy)
    date_matches = re.findall(r"\d{2}-\d{2}-\d{4}", text)
    if date_matches:
        try:
            result["start_date"] = datetime.strptime(date_matches[0], "%d-%m-%Y")
            result["end_date"] = datetime.strptime(date_matches[1], "%d-%m-%Y") if len(date_matches) > 1 else result["start_date"]
        except Exception:
            pass

    # Extract days if explicitly mentioned as "3 days"
    days_match = re.search(r"(\d+)\s*days?", text)
    if days_match:
        result["days"] = int(days_match.group(1))
    elif result["start_date"] and result["end_date"]:
        result["days"] = (result["end_date"] - result["start_date"]).days + 1

    return result

def safe_to_dict(draft):
    """Convert SQLAlchemy draft object into JSON-serializable dict."""
    fields = ["name", "email", "start_date", "end_date", "days", "description"]
    result = {}
    for f in fields:
        val = getattr(draft, f)
        if isinstance(val, (datetime, date)):
            result[f] = val.isoformat()
        else:
            result[f] = val
    return result

@app.post("/leaves")
def apply_leave(request: schemas.LeaveDraft, db: Session = Depends(get_db)):
    # --- Step 1: Parse input (structured or freeform) ---
    if getattr(request, "freeform", None):
        parsed = parse_freeform_input(request.freeform)
    else:
        parsed = request.dict()

    # --- Step 2: Save/update draft ---
    draft = crud.upsert_draft(db, parsed)

    # --- Step 3: Check missing fields ---
    required_fields = ["name", "email", "start_date", "end_date", "days", "description"]
    missing = [f for f in required_fields if getattr(draft, f) is None]

    if missing:
        return {
            "status": "drafting",
            "message": f"Waiting for: {missing}",
            "current_draft": safe_to_dict(draft),
        }

    # --- Step 4: Ensure employee exists ---
    employee = db.query(models.Employee).filter(models.Employee.email == draft.email).first()
    if not employee:
        employee = models.Employee(name=draft.name, email=draft.email)
        db.add(employee)
        db.commit()
        db.refresh(employee)

    # --- Step 5: Check leave balance ---
    leaves_left_before = crud.calculate_leaves_left(db, employee.id, employee.total_leaves)
    if draft.days > leaves_left_before:
        return {
            "status": "rejected",
            "message": "Not enough leave balance",
            "leaves_left": leaves_left_before,
        }

    # --- Step 6: Finalize leave ---
    leave = crud.apply_leave(
        db=db,
        employee_id=employee.id,
        start_date=draft.start_date,
        end_date=draft.end_date,
        days=draft.days,
        description=draft.description,
    )

    crud.delete_draft(db, draft.email)

    # --- Step 7: Notify HR ---
    email_subject = f"Leave Application Logged: {employee.name}"
    email_body = (
        f"Name: {employee.name}\n"
        f"Email: {employee.email}\n"
        f"Start Date: {leave.start_date}\n"
        f"End Date: {leave.end_date}\n"
        f"Days: {leave.days}\n"
        f"Description: {leave.description}\n"
        f"Leaves Left (before approval): {leaves_left_before}\n"
    )
    try:
        _ = send_leave_email(HR_EMAIL, email_subject, email_body)
    except Exception:
        pass

    # --- Step 8: Return final response ---
    return {
        "status": "submitted",
        "message": "Leave application finalized and submitted",
        "leaves_left": leaves_left_before,
    }
