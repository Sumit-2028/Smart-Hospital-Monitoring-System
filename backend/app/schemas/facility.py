from typing import Literal

from pydantic import BaseModel, Field


class DepartmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    active: bool = True


class RoomIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=80)
    room_type: Literal["OPD", "WAITING_AREA", "WARD", "EMERGENCY", "DOCTOR_CABIN"] = "WAITING_AREA"
    department_id: int | None = None
    capacity: int = Field(gt=0, le=100000)
    warning_percentage: int = Field(gt=0, le=100)
    active: bool = True


class CameraIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_type: Literal["WEBCAM", "IP_STREAM"] = "WEBCAM"
    source: str = Field(min_length=1, max_length=500)
    room_id: int
    active: bool = True
    processing_interval: int = Field(default=1, ge=1, le=60)


class DoctorIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    specialty: str = Field(min_length=1, max_length=160)
    department_id: int | None = None
    cabin_id: int | None = None
    work_identifier: str | None = Field(default=None, max_length=120)
    available: bool = True
    active: bool = True


class AdminLogin(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)
