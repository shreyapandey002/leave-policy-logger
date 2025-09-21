import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
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

# -------------------------
# LEAVE ENDPOINT
# -------------------------
@app.post("/leaves")
def apply_leave(request: schemas.LeaveDraftRequest, db: Session = Depends(get_db)):
    """
    Step-by-step drafting:
    - Store whatever fields user has given in LeaveDraft.
    - If all required fields are filled -> finalize, move to LeaveApplication, send email, delete draft.
    - Otherwise -> return which fields are still missing.
    """

    # 1. Save/Update draft
    draft = crud.upsert_draft(db, request.dict())

    # 2. Check if draft is complete
    required_fields = ["name", "email", "start_date", "end_date", "days", "description"]
    missing = [f for f in required_fields if getattr(draft, f) is None]

    if missing:
        return {
            "status": "drafting",
            "message": f"Waiting for: {missing}",
            "current_draft": {f: getattr(draft, f) for f in required_fields},
        }

    # 3. Finalize (all fields present)
    # Ensure employee exists
    employee = db.query(models.Employee).filter(models.Employee.email == draft.email).first()
    if not employee:
        employee = models.Employee(name=draft.name, email=draft.email)
        db.add(employee)
        db.commit()
        db.refresh(employee)

    # Compute leaves left BEFORE this request
    leaves_left_before = crud.calculate_leaves_left(db, employee.id, employee.total_leaves)

    if draft.days > leaves_left_before:
        return {
            "status": "rejected",
            "message": "Not enough leave balance",
            "leaves_left": leaves_left_before,
        }

    # Save leave
    leave = crud.apply_leave(
        db=db,
        employee_id=employee.id,
        start_date=draft.start_date,
        end_date=draft.end_date,
        days=draft.days,
        description=draft.description,
    )

    # Delete draft
    crud.delete_draft(db, draft.email)

    # Send email
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
    try:
        _ = send_leave_email(HR_EMAIL, email_subject, email_body)
    except Exception:
        pass

    return {
        "status": "submitted",
        "message": "Leave application finalized and submitted",
        "leaves_left": leaves_left_before,
    }
