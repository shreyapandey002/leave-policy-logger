from fastapi import FastAPI, Form, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime
import os, json, smtplib
from email.message import EmailMessage
from .db import SessionLocal, engine
from . import models, crud

app = FastAPI()
models.Base.metadata.create_all(bind=engine)

UPLOAD_DIR = "leave_drafts"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# -------------------- DB Dependency --------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -------------------- Initialize leave draft --------------------
@app.post("/leaves/init")
def init_leave(email: str = Form(...)):
    folder = os.path.join(UPLOAD_DIR, email)
    os.makedirs(folder, exist_ok=True)

    draft_file = os.path.join(folder, "draft.json")
    if os.path.exists(draft_file):
        with open(draft_file, "r") as f:
            draft = f.read()
    else:
        draft = "{}"
        with open(draft_file, "w") as f:
            f.write(draft)

    return {"status": "drafting", "message": "Leave draft initialized", "draft_file": draft_file}

# -------------------- Update leave draft --------------------
@app.post("/leaves/update")
def update_leave(
    email: str = Form(...),
    name: str = Form(None),
    start_date: str = Form(None),
    end_date: str = Form(None),
    days: str = Form(None),
    description: str = Form(None),
):
    folder = os.path.join(UPLOAD_DIR, email)
    draft_file = os.path.join(folder, "draft.json")
    if not os.path.exists(draft_file):
        raise HTTPException(status_code=404, detail="Draft not initialized. Call /leaves/init first.")

    with open(draft_file, "r") as f:
        draft = json.load(f)

    if name:
        draft["name"] = name

    if start_date:
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
            draft["start_date"] = start_date
        except ValueError:
            return {"status": "error", "message": "start_date must be YYYY-MM-DD"}

    if end_date:
        try:
            datetime.strptime(end_date, "%Y-%m-%d")
            draft["end_date"] = end_date
        except ValueError:
            return {"status": "error", "message": "end_date must be YYYY-MM-DD"}

    if days is not None:
        try:
            days_int = int(days)
            if days_int < 0:
                raise ValueError
            draft["days"] = days_int
        except ValueError:
            return {"status": "error", "message": "days must be a non-negative integer"}

    if description:
        draft["description"] = description

    # Save draft
    with open(draft_file, "w") as f:
        json.dump(draft, f)

    required = ["name", "start_date", "end_date", "days", "description"]
    missing = [f for f in required if f not in draft or draft[f] in (None, "")]

    return {
        "status": "drafting" if missing else "ready",
        "message": "Waiting for: " + ", ".join(missing) if missing else "All fields filled",
        "draft": draft
    }

# -------------------- Send leave email --------------------
def send_leave_email(user_email: str, draft: dict):
    hr_email = os.environ.get("HR_EMAIL")
    mailtrap_host = os.environ.get("MAILTRAP_HOST")
    mailtrap_port = int(os.environ.get("MAILTRAP_PORT", 2525))
    mailtrap_user = os.environ.get("MAILTRAP_USER")
    mailtrap_pass = os.environ.get("MAILTRAP_PASS")

    if not all([hr_email, mailtrap_host, mailtrap_user, mailtrap_pass]):
        raise Exception("Mailtrap or HR email environment variables not set")

    msg = EmailMessage()
    msg["From"] = "noreply@example.com"
    msg["To"] = hr_email
    msg["Cc"] = user_email
    msg["Subject"] = f"Leave Submission - {user_email}"

    body = f"""
Hi HR,

The following leave request has been submitted by {user_email}:

Name: {draft.get('name')}
Start Date: {draft.get('start_date')}
End Date: {draft.get('end_date')}
Days: {draft.get('days')}
Description: {draft.get('description')}

Regards,
Leave Management System
"""
    msg.set_content(body)

    # Attach draft as JSON
    msg.add_attachment(json.dumps(draft, indent=2).encode(), maintype="application", subtype="json", filename="leave_draft.json")

    with smtplib.SMTP(mailtrap_host, mailtrap_port) as smtp:
        smtp.login(mailtrap_user, mailtrap_pass)
        smtp.send_message(msg)

# -------------------- Submit leave --------------------
@app.post("/leaves/submit")
def submit_leave(email: str = Form(...), db: Session = Depends(get_db)):
    folder = os.path.join(UPLOAD_DIR, email)
    draft_file = os.path.join(folder, "draft.json")

    if not os.path.exists(draft_file):
        raise HTTPException(status_code=404, detail="No leave draft found. Call /leaves/init first.")

    with open(draft_file, "r") as f:
        draft = json.load(f)

    required = ["name", "start_date", "end_date", "days", "description"]
    missing = [f for f in required if f not in draft or draft[f] in (None, "")]
    if missing:
        return {"status": "error", "message": "Cannot submit. Missing fields: " + ", ".join(missing)}

    # Update employee in DB
    employee = crud.get_or_create_employee(db, email=email, name=draft["name"])
    total_leaves = 20
    remaining = total_leaves - draft["days"]
    employee.leaves_left = remaining
    db.commit()

    # Send email
    try:
        send_leave_email(email, draft)
    except Exception as e:
        return {"status": "error", "message": f"Leave submitted but failed to send email: {e}"}

    # Delete draft
    os.remove(draft_file)

    return {
        "status": "success",
        "message": f"Leave submitted for {employee.name} and email sent",
        "leaves_left": employee.leaves_left
    }
