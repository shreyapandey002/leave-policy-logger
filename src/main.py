import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.db import SessionLocal, engine
from src import models, crud, schemas

# -------------------------
# CONFIG
# -------------------------
MAILTRAP_HOST = os.getenv("MAILTRAP_HOST")
MAILTRAP_PORT = int(os.getenv("MAILTRAP_PORT", 587))
MAILTRAP_USER = os.getenv("MAILTRAP_USER")
MAILTRAP_PASS = os.getenv("MAILTRAP_PASS")
HR_EMAIL = os.getenv("HR_EMAIL", "hr@example.com")

# -------------------------
# APP & DB
# -------------------------
app = FastAPI()
models.Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -------------------------
# MAILTRAP HELPER
# -------------------------
def send_leave_email(to_email: str, subject: str, body: str):
    """
    Send an email using Mailtrap (SMTP).
    This function returns status info but we won't include it in the API response.
    """
    msg = MIMEMultipart()
    msg['From'] = MAILTRAP_USER
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(MAILTRAP_HOST, MAILTRAP_PORT) as server:
            server.starttls()
            server.login(MAILTRAP_USER, MAILTRAP_PASS)
            server.send_message(msg)
        return {"status": "sent"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

# -------------------------
# LEAVE ENDPOINT
# -------------------------
@app.post("/leaves", response_model=schemas.LeaveResponse)
def apply_leave(request: schemas.LeaveRequest, db: Session = Depends(get_db)):
    """
    Behavior:
    - Compute leaves_left based on existing DB entries (before applying this request).
    - If request.days > leaves_left_before -> return rejected (no DB insert).
    - Otherwise, insert the leave request into DB (recording it).
    - Send an email notification to HR (send result is not returned in API response).
    - Return leaves_left as the balance BEFORE the current request (i.e. request days are NOT deducted).
    """
    # 1. Ensure employee exists (create if missing)
    employee = db.query(models.Employee).filter(models.Employee.email == request.email).first()
    if not employee:
        employee = models.Employee(
            name=request.name,
            email=request.email
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)

    # 2. Calculate leaves left BEFORE processing this new request.
    #    (sum of all existing leave rows)
    total_taken = db.query(models.LeaveApplication).filter(
        models.LeaveApplication.employee_id == employee.id
    ).with_entities(func.sum(models.LeaveApplication.days)).scalar() or 0

    leaves_left_before = employee.total_leaves - total_taken

    # 3. Reject if requested days exceed the pre-request balance
    if request.days > leaves_left_before:
        # Return "rejected" with leaves_left as the BEFORE-request value
        return schemas.LeaveResponse(
            name=employee.name,
            email=employee.email,
            start_date=request.start_date,
            end_date=request.end_date,
            days=request.days,
            description=request.description,
            leaves_left=leaves_left_before,
            status="rejected"
        )

    # 4. Save leave (we record the leave in DB, but we DO NOT change the returned leaves_left)
    leave = crud.apply_leave(
        db=db,
        employee_id=employee.id,
        start_date=request.start_date,
        end_date=request.end_date,
        days=request.days,
        description=request.description
    )

    # 5. Send email notification to HR (we ignore/send but don't expose this status in API response)
    email_subject = f"Leave Application Logged: {employee.name}"
    email_body = (
        f"Name: {employee.name}\n"
        f"Email: {employee.email}\n"
        f"Start Date: {leave.start_date.date()}\n"
        f"End Date: {leave.end_date.date()}\n"
        f"Days: {leave.days}\n"
        f"Description: {leave.description}\n"
        f"Leaves Left (before approval): {leaves_left_before}\n"
    )
    # Fire-and-forget-like: capture result but do not return it in response_model
    try:
        _ = send_leave_email(HR_EMAIL, email_subject, email_body)
    except Exception:
        # swallow; don't fail the API because email failed
        pass

    # 6. Return response with leaves_left BEFORE the current request (requested days not deducted)
    return schemas.LeaveResponse(
        name=employee.name,
        email=employee.email,
        start_date=leave.start_date,
        end_date=leave.end_date,
        days=leave.days,
        description=leave.description,
        leaves_left=leaves_left_before,   # <-- important: not leaves_left_before - leave.days
        status="logged"
    )
