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
    # 1. Check if employee exists
    employee = db.query(models.Employee).filter(models.Employee.email == request.email).first()
    if not employee:
        employee = models.Employee(
            name=request.name,
            email=request.email
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)

    # 2. Calculate leaves left
    total_taken = db.query(models.LeaveApplication).filter(
        models.LeaveApplication.employee_id == employee.id
    ).with_entities(func.sum(models.LeaveApplication.days)).scalar() or 0
    leaves_left = employee.total_leaves - total_taken

    # 3. Reject if requested days exceed balance
    if request.days > leaves_left:
        return schemas.LeaveResponse(
            name=employee.name,
            email=employee.email,
            start_date=request.start_date,
            end_date=request.end_date,
            days=request.days,
            description=request.description,
            leaves_left=leaves_left,
            status="rejected"
        )

    # 4. Save leave if valid
    leave = crud.apply_leave(
        db=db,
        employee_id=employee.id,
        start_date=request.start_date,
        end_date=request.end_date,
        days=request.days,
        description=request.description
    )

    leaves_left -= request.days

    # 5. Send email notification
    email_subject = f"Leave Application Logged: {employee.name}"
    email_body = (
        f"Name: {employee.name}\n"
        f"Email: {employee.email}\n"
        f"Start Date: {leave.start_date.date()}\n"
        f"End Date: {leave.end_date.date()}\n"
        f"Days: {leave.days}\n"
        f"Description: {leave.description}\n"
        f"Leaves Left: {leaves_left}"
    )
    email_status = send_leave_email(HR_EMAIL, email_subject, email_body)

    return {
        "name": employee.name,
        "email": employee.email,
        "start_date": leave.start_date,
        "end_date": leave.end_date,
        "days": leave.days,
        "description": leave.description,
        "leaves_left": leaves_left,
        "status": "logged",
        "email_status": email_status
    }
