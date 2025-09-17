from sqlalchemy import Column, Integer, Text, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from .db import Base

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    total_leaves = Column(Integer, nullable=False, default=22)
    connected_account_id = Column(Text, nullable=True)

    leave_applications = relationship("LeaveApplication", back_populates="employee")


class LeaveApplication(Base):
    __tablename__ = "leave_applications"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    start_date = Column(TIMESTAMP, nullable=False)
    end_date = Column(TIMESTAMP, nullable=False)
    days = Column(Integer, nullable=False)
    description = Column(Text)

    employee = relationship("Employee", back_populates="leave_applications")
