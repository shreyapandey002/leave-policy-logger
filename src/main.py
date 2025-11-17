from fastapi import FastAPI, Form, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime
import os, json
from .db import SessionLocal, engine
from . import models, crud
import requests

app = FastAPI()
models.Base.metadata.create_all(bind=engine)

UPLOAD_DIR = "leave_drafts"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ------------ DB dependency ------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------ Composio Email Sender ------------
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
BASE_URL = os.getenv("COMPOSIO_BASE_URL", "https://backend.composio.dev/api/v3")
GMAIL_CONNECTED_ACCOUNT_ID = os.getenv("GMAIL_CONNECTED_ACCOUNT_ID")

def send_email_via_composio(user_email: str, draft: dict):
    if not COMPOSIO_API_KEY:
        raise Exception("Missing COMPOSIO_API_KEY")

    if not GMAIL_CONNECTED_ACCOUNT_ID:
        raise Exception("Missing GMAIL_CONNECTED_ACCOUNT_ID")

    hr_email = os.getenv("HR_EMAIL")
    if not hr_email:
        raise Exception("Missing HR_EMAIL env variable")

    subject = f"Leave Submission - {user_email}"

    body = f"""
Hi HR,

A new leave request has been submitted.

Name: {draft.get('name')}
Start Date: {draft.get('start_date')}
End Date: {draft.get('end_date')}
Days: {draft.get('days')}
Description: {draft.get('description')}

Regards,
Leave Management System
"""

    payload = {
        "connected_account_id": GMAIL_CONNECTED_ACCOUNT_ID,
        "arguments": {
            "recipient_email": f"{hr_email}",
            "subject": subject,
            "body": body,
            "is_html": False
        }
    }

    endpoint = f"{BASE_URL}/tools/execute/GMAIL_SEND_EMAIL"

    resp = requests.post(
        endpoint,
        json=payload,
        headers={"x-api-key": COMPOSIO_API_KEY},
        timeout=60
    )

    data = resp.json()
    if resp.status_code != 200 or not data.get("successful", True):
        raise Exception(f"Composio Gmail Error: {data}")

    return data


# ------------ Initialize leave draft ------------
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


# ------------ Update leave draft ------------
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
        datetime.strptime(start_date, "%Y-%m-%d")
        draft["start_date"] = start_date

    if end_date:
        datetime.strptime(end_date, "%Y-%m-%d")
        draft["end_date"] = end_date

    if days is not None:
        days_int = int(days)
        if days_int < 0:
            raise ValueError
        draft["days"] = days_int

    if description:
        draft["description"] = description

    with open(draft_file, "w") as f:
        json.dump(draft, f)

    required = ["name", "start_date", "end_date", "days", "description"]
    missing = [f for f in required if f not in draft or draft[f] in (None, "")]

    return {
        "status": "drafting" if missing else "ready",
        "message": "Waiting for: " + ", ".join(missing) if missing else "All fields filled",
        "draft": draft
    }


# ------------ Submit leave + send Composio Gmail email ------------
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

    # Update DB
    employee = crud.get_or_create_employee(db, email=email, name=draft["name"])
    total_leaves = 20
    employee.leaves_left = total_leaves - int(draft["days"])
    db.commit()

    # Send via Composio Gmail
    try:
        send_email_via_composio(email, draft)
    except Exception as e:
        return {"status": "error", "message": f"Leave submitted but email failed: {e}"}

    os.remove(draft_file)

    return {
        "status": "success",
        "message": f"Leave submitted for {employee.name} and email sent successfully",
        "leaves_left": employee.leaves_left
    }
