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
    days: str = Form(None),
    description: str = Form(None),
):
    folder = os.path.join(UPLOAD_DIR, email)
    draft_file = os.path.join(folder, "draft.json")
    if not os.path.exists(draft_file):
        raise HTTPException(status_code=404, detail="Draft not initialized. Call /leaves/init first.")

    import json
    with open(draft_file, "r") as f:
        draft = json.load(f)

    # Update fields if provided
    if name:
        draft["name"] = name

    if start_date:
        try:
            datetime.strptime(start_date, "%Y-%m-%d")  # validate format
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

    # Save draft back to file
    with open(draft_file, "w") as f:
        json.dump(draft, f)

    # Check missing fields
    required = ["name", "start_date", "end_date", "days", "description"]
    missing = [f for f in required if f not in draft or draft[f] in (None, "")]

    return {
        "status": "drafting" if missing else "ready",
        "message": "Waiting for: " + ", ".join(missing) if missing else "All fields filled",
        "draft": draft
    }

# ---------------- Submit leave ----------------
@app.post("/leaves/submit")
def submit_leave(email: str = Form(...), db: Session = Depends(get_db)):
    """
    Submit the leave draft for the given email.
    Creates/updates the employee's leave record and deletes the draft file.
    """
    folder = os.path.join(UPLOAD_DIR, email)
    draft_file = os.path.join(folder, "draft.json")

    if not os.path.exists(draft_file):
        raise HTTPException(status_code=404, detail="No leave draft found. Call /leaves/init first.")

    # Read draft from JSON
    import json
    with open(draft_file, "r") as f:
        draft = json.load(f)

    # Make sure all fields are present
    required = ["name", "start_date", "end_date", "days", "description"]
    missing = [f for f in required if f not in draft or draft[f] in (None, "")]
    if missing:
        return {"status": "error", "message": "Cannot submit. Missing fields: " + ", ".join(missing)}

    # Create or get employee
    employee = crud.get_or_create_employee(db, email=email, name=draft["name"])

    # Compute remaining leaves
    total_leaves = 20  # example max leaves per year
    remaining = total_leaves - draft["days"]

    # Update employee leaves left
    employee.leaves_left = remaining
    db.commit()

    # Delete draft file
    os.remove(draft_file)

    return {
        "status": "success",
        "message": f"Leave submitted for {employee.name}",
        "leaves_left": employee.leaves_left
    }
