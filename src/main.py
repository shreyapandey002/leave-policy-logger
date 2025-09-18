from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from src.db import SessionLocal, engine
from src import models, crud, schemas
from sqlalchemy import func

app = FastAPI()

models.Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/leaves", response_model=schemas.LeaveResponse)
def apply_leave(request: schemas.LeaveRequest, db: Session = Depends(get_db)):
    # 1. Check if employee exists
    employee = db.query(models.Employee).filter(models.Employee.email == request.email).first()
    if not employee:
        employee = models.Employee(
            name=request.name,
            email=request.email,
            connected_account_id=request.connected_account_id  
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)

    # 2. Calculate leaves already taken
    total_taken = db.query(models.LeaveApplication).filter(
        models.LeaveApplication.employee_id == employee.id
    ).with_entities(func.sum(models.LeaveApplication.days)).scalar() or 0

    leaves_left = employee.total_leaves - total_taken

    # 3. Check if request exceeds balance
    if request.days > leaves_left:
        # Escalate instead of deducting
        return schemas.LeaveResponse(
            name=employee.name,
            email=employee.email,
            start_date=request.start_date,
            end_date=request.end_date,
            days=request.days,
            description=request.description,
            leaves_left=leaves_left,
            status="pending_hr_approval",   # <-- NEW FIELD
            message=(
                f"Requested {request.days} days but only {leaves_left} available. "
                f"Escalated to HR for approval. No deduction applied."
            )
        )

    # 4. Normal flow → deduct and save leave application
    leave = crud.apply_leave(
        db=db,
        employee_id=employee.id,
        start_date=request.start_date,
        end_date=request.end_date,
        days=request.days,
        description=request.description
    )

    # 5. Recalculate balance after deduction
    total_taken = db.query(models.LeaveApplication).filter(
        models.LeaveApplication.employee_id == employee.id
    ).with_entities(func.sum(models.LeaveApplication.days)).scalar() or 0
    leaves_left = employee.total_leaves - total_taken

    # 6. Return success response
    return schemas.LeaveResponse(
        name=employee.name,
        email=employee.email,
        start_date=leave.start_date,
        end_date=leave.end_date,
        days=leave.days,
        description=leave.description,
        leaves_left=leaves_left
    )
