from fastapi import FastAPI, Form, UploadFile, Depends
from sqlalchemy.orm import Session
from datetime import datetime
import os, tempfile, requests, shutil
from .db import SessionLocal, engine
from . import models, crud

app = FastAPI()
models.Base.metadata.create_all(bind=engine)

UPLOAD_DIR = "leave_drafts"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------- Init leave draft ----------------
@app.post("/leaves/init")
def init_leave(email: str = Form(...)):
    folder = os.path.join(UPLOAD_DIR, email)
    os.makedirs(folder, exist_ok=True)
    # Check if a draft.json exists
    draft_file = os.path.join(folder, "draft.json")
    if os.path.exists(draft_file):
        with open(draft_file, "r") as f:
            draft = f.read()
    else:
        draft = "{}"
        with open(draft_file, "w") as f:
            f.write(draft)
    return {"status": "drafting", "message": "Leave draft initialized", "draft_file": draft_file}

# ---------------- Update leave draft ----------------
@app.post("/leaves/update")
def update_leave(
    email: str = Form(...),
    name: str = Form(None),
    start_date: str = Form(None),
    end_date: str = Form(None),
    days: int = Form(None),
    description: str = Form(None),
):
    folder = os.path.join(UPLOAD_DIR, email)
    draft_file = os.path.join(folder, "draft.json")
    if not os.path.exists(draft_file):
        return {"status": "error", "message": "Draft not initialized. Call /init first."}

    import json
    with open(draft_file, "r") as f:
        draft = json.load(f)

    if name:
        draft["name"] = name
    if start_date:
        draft["start_date"] = start_date
    if end_date:
        draft["end_date"] = end_date
    if days is not None:
        draft["days"] = days
    if description:
        draft["description"] = description

    with open(draft_file, "w") as f:
        json.dump(draft, f)

    required = ["name", "start_date", "end_date", "days", "description"]
    missing = [f for f in required if f not in draft or draft[f] is None]

    return {
        "status": "drafting" if missing else "ready",
        "message": "Waiting for: " + ", ".join(missing) if missing else "All fields filled",
        "draft": draft
    }

# ---------------- Submit leave ----------------
@app.post("/leaves/submit")
def submit_leave(email: str = Form(...), db: Session = Depends(get_db)):
    folder = os.path.join(UPLOAD_DIR, email)
    draft_file = os.path.join(folder, "draft.json")
    if not os.path.exists(draft_file):
        return {"status": "error", "message": "Draft not initialized"}

    import json
    with open(draft_file, "r") as f:
        draft = json.load(f)

    required = ["name", "start_date", "end_date", "days", "description"]
    missing = [f for f in required if f not in draft or draft[f] is None]
    if missing:
        return {"status": "drafting", "message": "Missing fields: " + ", ".join(missing)}

    # Convert dates
    for key in ["start_date", "end_date"]:
        if "T" in draft[key]:
            draft[key] = datetime.fromisoformat(draft[key])
        else:
            draft[key] = datetime.strptime(draft[key], "%d-%m-%Y")

    employee = crud.get_or_create_employee(db, email=draft["email"], name=draft["name"])
    leaves_left = crud.calculate_leaves_left(db, employee.id)

    if draft["days"] > leaves_left:
        return {"status": "rejected", "message": "Not enough leave balance", "leaves_left": leaves_left}

    crud.apply_leave(db, employee.id, draft["start_date"], draft["end_date"], draft["days"], draft["description"])

    # Delete draft
    shutil.rmtree(folder)

    leaves_left_after = crud.calculate_leaves_left(db, employee.id)

    return {
        "status": "submitted",
        "message": "Leave application finalized and submitted",
        "leaves_left": leaves_left_after
    }
