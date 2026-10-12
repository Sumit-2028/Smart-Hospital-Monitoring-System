from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session
from urllib.parse import urlparse

from app.auth import AuthenticationConfigurationError, issue_token, require_admin, verify_password
from app.database import get_db
from app.models.facility import AdminUser, Camera, Department, Doctor, Room
from app.schemas.facility import AdminLogin, CameraIn, DepartmentIn, DoctorIn, RoomIn

router = APIRouter(prefix="/api/admin", tags=["Administration"])


def room_json(room):
    return {"id": room.id, "name": room.name, "code": room.code, "room_type": room.room_type,
            "department_id": room.department_id, "capacity": room.capacity,
            "warning_percentage": room.warning_percentage, "active": room.active}


def camera_json(camera):
    return {"id": camera.id, "name": camera.name, "source_type": camera.source_type, "room_id": camera.room_id,
            "active": camera.active, "status": camera.status, "last_frame_at": camera.last_frame_at,
            "processing_interval": camera.processing_interval}


@router.post("/login")
def login(data: AdminLogin, db: Session = Depends(get_db)):
    user = db.query(AdminUser).filter(AdminUser.username == data.username, AdminUser.active.is_(True)).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    try:
        token = issue_token(user.username)
    except AuthenticationConfigurationError as error:
        raise HTTPException(status_code=503, detail="Authentication is not configured. Set ADMIN_TOKEN_SECRET and restart the backend.") from error
    return {"access_token": token, "token_type": "bearer"}


@router.get("/departments")
def list_departments(_: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(Department).order_by(Department.name).all()


@router.post("/departments")
def create_department(data: DepartmentIn, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    department = Department(**data.model_dump())
    db.add(department)
    try:
        db.commit(); db.refresh(department); return department
    except IntegrityError:
        db.rollback(); raise HTTPException(status_code=409, detail="Department name already exists")


@router.put("/departments/{department_id}")
def update_department(department_id: int, data: DepartmentIn, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    department = db.get(Department, department_id)
    if not department: raise HTTPException(404, "Department not found")
    for key, value in data.model_dump().items(): setattr(department, key, value)
    try:
        db.commit(); db.refresh(department); return department
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "Department name already exists")


@router.get("/rooms")
def list_rooms(_: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    return [room_json(r) for r in db.query(Room).order_by(Room.name).all()]


@router.get("/cabins")
def list_cabins(_: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    """Return active doctor-cabin rooms for doctor assignment controls."""
    return [room_json(r) for r in db.query(Room).filter(func.upper(Room.room_type) == "DOCTOR_CABIN", Room.active.is_(True)).order_by(Room.name).all()]


@router.post("/rooms")
def create_room(data: RoomIn, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    if data.department_id and not db.get(Department, data.department_id): raise HTTPException(400, "Department not found")
    room = Room(**data.model_dump()); db.add(room)
    try: db.commit(); db.refresh(room); return room_json(room)
    except IntegrityError: db.rollback(); raise HTTPException(409, "Room code already exists")


@router.put("/rooms/{room_id}")
def update_room(room_id: int, data: RoomIn, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    room = db.get(Room, room_id)
    if not room: raise HTTPException(404, "Room not found")
    if data.department_id and not db.get(Department, data.department_id): raise HTTPException(400, "Department not found")
    for key, value in data.model_dump().items(): setattr(room, key, value)
    try: db.commit(); db.refresh(room); return room_json(room)
    except IntegrityError: db.rollback(); raise HTTPException(409, "Room code already exists")


@router.get("/cameras")
def list_cameras(_: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    return [camera_json(c) for c in db.query(Camera).order_by(Camera.name).all()]


@router.get("/cameras/{camera_id}/edit")
def camera_edit_details(camera_id: int, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    camera = db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(404, "Camera not found")
    return {**camera_json(camera), "source": camera.source}


@router.post("/cameras")
def create_camera(data: CameraIn, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    room = db.get(Room, data.room_id)
    if not room or not room.active: raise HTTPException(400, "Camera room must be an active room")
    if data.active and db.query(Camera).filter(Camera.room_id == data.room_id, Camera.active.is_(True)).first():
        raise HTTPException(409, "Only one active occupancy camera is allowed per room")
    if data.source_type == "WEBCAM":
        try: int(data.source)
        except ValueError: raise HTTPException(422, "WEBCAM source must be a device index")
    elif urlparse(data.source).scheme not in {"http", "https", "rtsp"}:
        raise HTTPException(422, "IP_STREAM source must use http, https, or rtsp")
    camera = Camera(**data.model_dump()); db.add(camera); db.commit(); db.refresh(camera)
    return camera_json(camera)


@router.put("/cameras/{camera_id}")
def update_camera(camera_id: int, data: CameraIn, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    camera = db.get(Camera, camera_id)
    room = db.get(Room, data.room_id)
    if not camera: raise HTTPException(404, "Camera not found")
    if not room or not room.active: raise HTTPException(400, "Camera room must be an active room")
    if data.active and db.query(Camera).filter(Camera.room_id == data.room_id, Camera.active.is_(True), Camera.id != camera_id).first():
        raise HTTPException(409, "Only one active occupancy camera is allowed per room")
    if data.source_type == "WEBCAM":
        try: int(data.source)
        except ValueError: raise HTTPException(422, "WEBCAM source must be a device index")
    elif urlparse(data.source).scheme not in {"http", "https", "rtsp"}:
        raise HTTPException(422, "IP_STREAM source must use http, https, or rtsp")
    for key, value in data.model_dump().items(): setattr(camera, key, value)
    db.commit(); db.refresh(camera); return camera_json(camera)


@router.get("/doctors")
def list_doctors(_: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(Doctor).order_by(Doctor.name).all()


@router.post("/doctors")
def create_doctor(data: DoctorIn, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    if data.department_id and not db.get(Department, data.department_id): raise HTTPException(400, "Department not found")
    if data.cabin_id:
        cabin = db.get(Room, data.cabin_id)
        if not cabin or (cabin.room_type or "").upper() != "DOCTOR_CABIN" or not cabin.active: raise HTTPException(400, "Doctor cabin must be an active DOCTOR_CABIN room")
        if db.query(Doctor).filter(Doctor.cabin_id == data.cabin_id, Doctor.active.is_(True)).first(): raise HTTPException(409, "Cabin already has an active doctor")
    doctor = Doctor(**data.model_dump()); db.add(doctor); db.commit(); db.refresh(doctor); return doctor


@router.put("/doctors/{doctor_id}")
def update_doctor(doctor_id: int, data: DoctorIn, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    doctor = db.get(Doctor, doctor_id)
    if not doctor: raise HTTPException(404, "Doctor not found")
    if data.cabin_id:
        cabin = db.get(Room, data.cabin_id)
        if not cabin or (cabin.room_type or "").upper() != "DOCTOR_CABIN" or not cabin.active: raise HTTPException(400, "Doctor cabin must be an active DOCTOR_CABIN room")
        conflict = db.query(Doctor).filter(Doctor.cabin_id == data.cabin_id, Doctor.id != doctor_id, Doctor.active.is_(True)).first()
        if conflict: raise HTTPException(409, "Cabin already has an active doctor")
    for key, value in data.model_dump().items(): setattr(doctor, key, value)
    db.commit(); db.refresh(doctor); return doctor


@router.patch("/{resource}/{record_id}/active")
def set_active(resource: str, record_id: int, active: bool, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    models = {"departments": Department, "rooms": Room, "cameras": Camera, "doctors": Doctor}
    model = models.get(resource)
    if not model:
        raise HTTPException(404, "Unknown administration resource")
    record = db.get(model, record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    if resource == "rooms" and not active and db.query(Camera).filter(Camera.room_id == record_id, Camera.active.is_(True)).first():
        raise HTTPException(409, "Deactivate the room's active camera first")
    if resource == "departments" and not active:
        if db.query(Room).filter(Room.department_id == record_id, Room.active.is_(True)).first() or db.query(Doctor).filter(Doctor.department_id == record_id, Doctor.active.is_(True)).first():
            raise HTTPException(409, "Deactivate assigned rooms and doctors first")
    if resource == "cameras" and active and db.query(Camera).filter(Camera.room_id == record.room_id, Camera.active.is_(True), Camera.id != record_id).first():
        raise HTTPException(409, "Only one active occupancy camera is allowed per room")
    record.active = active
    db.commit()
    return {"id": record.id, "active": record.active}
