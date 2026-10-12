import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import (
    AuthenticationConfigurationError,
    hash_password,
    issue_token,
    normalize_username,
    require_admin,
    require_superadmin,
    verify_password,
)
from app.database import get_db
from app.models.facility import AdminUser, Camera, Department, Doctor, Room
from app.schemas.facility import AdminCreate, AdminLogin, AdminUpdate, CameraIn, DepartmentIn, DoctorIn, RoomIn
from app.services.audit_service import add_audit, record_failed_audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Administration"])


def room_json(room):
    return {"id": room.id, "name": room.name, "code": room.code, "room_type": room.room_type,
            "department_id": room.department_id, "capacity": room.capacity,
            "warning_percentage": room.warning_percentage, "active": room.active}


def camera_json(camera):
    return {"id": camera.id, "name": camera.name, "source_type": camera.source_type,
            "room_id": camera.room_id, "active": camera.active, "status": camera.status,
            "last_frame_at": camera.last_frame_at, "processing_interval": camera.processing_interval}


def admin_json(admin):
    """Never expose password hashes, tokens, or other credentials."""
    return {"id": admin.id, "username": admin.username, "role": admin.role or "ADMIN",
            "active": admin.active, "created_at": admin.created_at}


def _commit_audited(db, actor, action, resource_type, resource_id, context=None):
    try:
        add_audit(db, actor=actor, action=action, outcome="SUCCESS", resource_type=resource_type,
                  resource_id=resource_id, context=context)
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        if isinstance(error, IntegrityError):
            raise
        logger.exception("administration transaction failed", extra={
            "action": action, "resource_type": resource_type, "resource_id": resource_id, "actor_id": actor.id,
        })
        raise HTTPException(status_code=503, detail="Administration change could not be stored.") from error


def _audit_failure(db, actor, action, resource_type=None, resource_id=None, reason=None, actor_username=None):
    return record_failed_audit(db, actor=actor, actor_username=actor_username, action=action,
                               resource_type=resource_type, resource_id=resource_id,
                               context={"reason": reason} if reason else None)


def _validate_camera_source(data: CameraIn):
    if data.source_type == "WEBCAM":
        try:
            int(data.source)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="WEBCAM source must be a device index") from error
    elif urlparse(data.source).scheme not in {"http", "https", "rtsp"}:
        raise HTTPException(status_code=422, detail="IP_STREAM source must use http, https, or rtsp")


@router.post("/login")
def login(data: AdminLogin, db: Session = Depends(get_db)):
    username = normalize_username(data.username)
    user = db.query(AdminUser).filter(func.lower(AdminUser.username) == username,
                                      AdminUser.active.is_(True)).first()
    if not user or not verify_password(data.password, user.password_hash):
        _audit_failure(db, None, "LOGIN", "ADMIN_USER", actor_username=username, reason="invalid_credentials")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    try:
        token = issue_token(user.username)
        add_audit(db, actor=user, action="LOGIN", outcome="SUCCESS", resource_type="ADMIN_USER", resource_id=user.id)
        db.commit()
    except AuthenticationConfigurationError as error:
        _audit_failure(db, user, "LOGIN", "ADMIN_USER", user.id, "authentication_not_configured")
        raise HTTPException(status_code=503, detail="Authentication is not configured. Set ADMIN_TOKEN_SECRET and restart the backend.") from error
    except SQLAlchemyError as error:
        db.rollback()
        logger.exception("successful login audit could not be persisted", extra={"actor_id": user.id, "action": "LOGIN"})
        raise HTTPException(status_code=503, detail="Login could not be completed.") from error
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
def current_admin(admin: AdminUser = Depends(require_admin)):
    return admin_json(admin)


@router.get("/admins")
def list_admins(_: AdminUser = Depends(require_superadmin), db: Session = Depends(get_db)):
    return [admin_json(admin) for admin in db.query(AdminUser).order_by(AdminUser.username).all()]


@router.post("/admins")
def create_admin(data: AdminCreate, actor: AdminUser = Depends(require_superadmin), db: Session = Depends(get_db)):
    username = normalize_username(data.username)
    if db.query(AdminUser).filter(func.lower(AdminUser.username) == username).first():
        _audit_failure(db, actor, "ADMIN_CREATED", "ADMIN_USER", username, "duplicate_username")
        raise HTTPException(status_code=409, detail="Admin username already exists")
    admin = AdminUser(username=username, password_hash=hash_password(data.password), role=data.role, active=data.active)
    db.add(admin)
    try:
        db.flush()
        add_audit(db, actor=actor, action="ADMIN_CREATED", outcome="SUCCESS", resource_type="ADMIN_USER",
                  resource_id=admin.id, context={"role": admin.role})
        db.commit()
        db.refresh(admin)
        return admin_json(admin)
    except IntegrityError as error:
        _audit_failure(db, actor, "ADMIN_CREATED", "ADMIN_USER", username, "duplicate_username")
        raise HTTPException(status_code=409, detail="Admin username already exists") from error
    except SQLAlchemyError as error:
        db.rollback()
        logger.exception("admin creation failed", extra={"actor_id": actor.id, "action": "ADMIN_CREATED"})
        raise HTTPException(status_code=503, detail="Administrator could not be created.") from error


@router.put("/admins/{admin_id}")
def update_admin(admin_id: int, data: AdminUpdate, actor: AdminUser = Depends(require_superadmin), db: Session = Depends(get_db)):
    admin = db.get(AdminUser, admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Administrator not found")
    username = normalize_username(data.username)
    if db.query(AdminUser).filter(func.lower(AdminUser.username) == username, AdminUser.id != admin_id).first():
        _audit_failure(db, actor, "ADMIN_UPDATED", "ADMIN_USER", admin_id, "duplicate_username")
        raise HTTPException(status_code=409, detail="Admin username already exists")
    if admin.id == actor.id and not data.active:
        _audit_failure(db, actor, "ADMIN_UPDATED", "ADMIN_USER", admin_id, "self_deactivation")
        raise HTTPException(status_code=409, detail="You cannot deactivate your current administrator account")
    if admin.role == "SUPERADMIN" and data.role != "SUPERADMIN":
        active_superadmins = db.query(AdminUser).filter(AdminUser.role == "SUPERADMIN", AdminUser.active.is_(True)).count()
        if active_superadmins <= 1:
            _audit_failure(db, actor, "ADMIN_UPDATED", "ADMIN_USER", admin_id, "last_superadmin")
            raise HTTPException(status_code=409, detail="At least one active super administrator is required")
    changed = []
    if admin.username != username:
        changed.append("username")
        admin.username = username
    if admin.role != data.role:
        changed.append("role")
        admin.role = data.role
    if admin.active != data.active:
        changed.append("active")
        admin.active = data.active
    if data.password is not None:
        changed.append("password")
        admin.password_hash = hash_password(data.password)
    try:
        db.flush()
        add_audit(db, actor=actor, action="ADMIN_UPDATED", outcome="SUCCESS", resource_type="ADMIN_USER",
                  resource_id=admin.id, context={"changed_fields": changed})
        db.commit()
        db.refresh(admin)
        return admin_json(admin)
    except IntegrityError as error:
        _audit_failure(db, actor, "ADMIN_UPDATED", "ADMIN_USER", admin_id, "duplicate_username")
        raise HTTPException(status_code=409, detail="Admin username already exists") from error
    except SQLAlchemyError as error:
        db.rollback()
        logger.exception("admin update failed", extra={"actor_id": actor.id, "target_id": admin_id, "action": "ADMIN_UPDATED"})
        raise HTTPException(status_code=503, detail="Administrator could not be updated.") from error


@router.patch("/admins/{admin_id}/active")
def set_admin_active(admin_id: int, active: bool, actor: AdminUser = Depends(require_superadmin), db: Session = Depends(get_db)):
    admin = db.get(AdminUser, admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Administrator not found")
    if admin.id == actor.id and not active:
        _audit_failure(db, actor, "ADMIN_DEACTIVATED", "ADMIN_USER", admin_id, "self_deactivation")
        raise HTTPException(status_code=409, detail="You cannot deactivate your current administrator account")
    if admin.role == "SUPERADMIN" and not active:
        active_superadmins = db.query(AdminUser).filter(AdminUser.role == "SUPERADMIN", AdminUser.active.is_(True)).count()
        if active_superadmins <= 1:
            _audit_failure(db, actor, "ADMIN_DEACTIVATED", "ADMIN_USER", admin_id, "last_superadmin")
            raise HTTPException(status_code=409, detail="At least one active super administrator is required")
    admin.active = active
    action = "ADMIN_ACTIVATED" if active else "ADMIN_DEACTIVATED"
    _commit_audited(db, actor, action, "ADMIN_USER", admin.id)
    return admin_json(admin)


@router.get("/departments")
def list_departments(_: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(Department).order_by(Department.name).all()


@router.post("/departments")
def create_department(data: DepartmentIn, actor: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    department = Department(**data.model_dump())
    db.add(department)
    try:
        db.flush()
        add_audit(db, actor=actor, action="DEPARTMENT_CREATED", outcome="SUCCESS", resource_type="DEPARTMENT", resource_id=department.id)
        db.commit()
        db.refresh(department)
        return department
    except IntegrityError as error:
        _audit_failure(db, actor, "DEPARTMENT_CREATED", "DEPARTMENT", None, "duplicate_name")
        raise HTTPException(status_code=409, detail="Department name already exists") from error
    except SQLAlchemyError as error:
        db.rollback()
        logger.exception("department creation failed", extra={"actor_id": actor.id})
        raise HTTPException(status_code=503, detail="Department could not be created.") from error


@router.put("/departments/{department_id}")
def update_department(department_id: int, data: DepartmentIn, actor: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    department = db.get(Department, department_id)
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")
    for key, value in data.model_dump().items():
        setattr(department, key, value)
    try:
        _commit_audited(db, actor, "DEPARTMENT_UPDATED", "DEPARTMENT", department.id)
        db.refresh(department)
        return department
    except IntegrityError as error:
        _audit_failure(db, actor, "DEPARTMENT_UPDATED", "DEPARTMENT", department_id, "duplicate_name")
        raise HTTPException(status_code=409, detail="Department name already exists") from error


@router.get("/rooms")
def list_rooms(_: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    return [room_json(room) for room in db.query(Room).order_by(Room.name).all()]


@router.get("/cabins")
def list_cabins(_: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    return [room_json(room) for room in db.query(Room).filter(func.upper(Room.room_type) == "DOCTOR_CABIN", Room.active.is_(True)).order_by(Room.name).all()]


@router.post("/rooms")
def create_room(data: RoomIn, actor: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    if data.department_id and not db.get(Department, data.department_id):
        raise HTTPException(status_code=400, detail="Department not found")
    room = Room(**data.model_dump())
    db.add(room)
    try:
        db.flush()
        add_audit(db, actor=actor, action="ROOM_CREATED", outcome="SUCCESS", resource_type="ROOM", resource_id=room.id,
                  context={"capacity": room.capacity, "warning_percentage": room.warning_percentage})
        db.commit()
        db.refresh(room)
        return room_json(room)
    except IntegrityError as error:
        _audit_failure(db, actor, "ROOM_CREATED", "ROOM", None, "duplicate_code")
        raise HTTPException(status_code=409, detail="Room code already exists") from error
    except SQLAlchemyError as error:
        db.rollback()
        logger.exception("room creation failed", extra={"actor_id": actor.id})
        raise HTTPException(status_code=503, detail="Room could not be created.") from error


@router.put("/rooms/{room_id}")
def update_room(room_id: int, data: RoomIn, actor: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if data.department_id and not db.get(Department, data.department_id):
        raise HTTPException(status_code=400, detail="Department not found")
    changed = [field for field in ("capacity", "warning_percentage") if getattr(room, field) != getattr(data, field)]
    for key, value in data.model_dump().items():
        setattr(room, key, value)
    try:
        _commit_audited(db, actor, "ROOM_UPDATED", "ROOM", room.id, {"changed_fields": changed})
        db.refresh(room)
        return room_json(room)
    except IntegrityError as error:
        _audit_failure(db, actor, "ROOM_UPDATED", "ROOM", room_id, "duplicate_code")
        raise HTTPException(status_code=409, detail="Room code already exists") from error


@router.get("/cameras")
def list_cameras(_: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    return [camera_json(camera) for camera in db.query(Camera).order_by(Camera.name).all()]


@router.get("/cameras/{camera_id}/edit")
def camera_edit_details(camera_id: int, _: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    camera = db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {**camera_json(camera), "source": camera.source}


@router.post("/cameras")
def create_camera(data: CameraIn, actor: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    room = db.get(Room, data.room_id)
    if not room or not room.active:
        raise HTTPException(status_code=400, detail="Camera room must be an active room")
    if data.active and db.query(Camera).filter(Camera.room_id == data.room_id, Camera.active.is_(True)).first():
        raise HTTPException(status_code=409, detail="Only one active occupancy camera is allowed per room")
    _validate_camera_source(data)
    camera = Camera(**data.model_dump())
    db.add(camera)
    try:
        db.flush()
        add_audit(db, actor=actor, action="CAMERA_CREATED", outcome="SUCCESS", resource_type="CAMERA", resource_id=camera.id,
                  context={"source_type": camera.source_type, "room_id": camera.room_id})
        db.commit()
        db.refresh(camera)
        return camera_json(camera)
    except SQLAlchemyError as error:
        db.rollback()
        logger.exception("camera creation failed", extra={"actor_id": actor.id, "room_id": data.room_id})
        raise HTTPException(status_code=503, detail="Camera could not be created.") from error


@router.put("/cameras/{camera_id}")
def update_camera(camera_id: int, data: CameraIn, actor: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    camera = db.get(Camera, camera_id)
    room = db.get(Room, data.room_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    if not room or not room.active:
        raise HTTPException(status_code=400, detail="Camera room must be an active room")
    if data.active and db.query(Camera).filter(Camera.room_id == data.room_id, Camera.active.is_(True), Camera.id != camera_id).first():
        raise HTTPException(status_code=409, detail="Only one active occupancy camera is allowed per room")
    _validate_camera_source(data)
    for key, value in data.model_dump().items():
        setattr(camera, key, value)
    try:
        _commit_audited(db, actor, "CAMERA_UPDATED", "CAMERA", camera.id,
                        {"room_id": camera.room_id, "source_type": camera.source_type})
        db.refresh(camera)
        return camera_json(camera)
    except IntegrityError as error:
        _audit_failure(db, actor, "CAMERA_UPDATED", "CAMERA", camera_id, "constraint_violation")
        raise HTTPException(status_code=409, detail="Camera could not be updated") from error


@router.get("/doctors")
def list_doctors(_: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(Doctor).order_by(Doctor.name).all()


def _validate_doctor_assignment(data: DoctorIn, doctor_id, db: Session):
    if data.department_id:
        department = db.get(Department, data.department_id)
        if not department or not department.active:
            raise HTTPException(status_code=400, detail="Doctor department must be active")
    if data.cabin_id:
        cabin = db.get(Room, data.cabin_id)
        if not cabin or (cabin.room_type or "").upper() != "DOCTOR_CABIN" or not cabin.active:
            raise HTTPException(status_code=400, detail="Doctor cabin must be an active DOCTOR_CABIN room")
        if db.query(Doctor).filter(Doctor.cabin_id == data.cabin_id, Doctor.active.is_(True), Doctor.id != doctor_id).first():
            raise HTTPException(status_code=409, detail="Cabin already has an active doctor")


@router.post("/doctors")
def create_doctor(data: DoctorIn, actor: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    _validate_doctor_assignment(data, None, db)
    doctor = Doctor(**data.model_dump())
    db.add(doctor)
    try:
        db.flush()
        add_audit(db, actor=actor, action="DOCTOR_CREATED", outcome="SUCCESS", resource_type="DOCTOR", resource_id=doctor.id,
                  context={"department_id": doctor.department_id, "cabin_id": doctor.cabin_id})
        db.commit()
        db.refresh(doctor)
        return doctor
    except SQLAlchemyError as error:
        db.rollback()
        logger.exception("doctor creation failed", extra={"actor_id": actor.id})
        raise HTTPException(status_code=503, detail="Doctor could not be created.") from error


@router.put("/doctors/{doctor_id}")
def update_doctor(doctor_id: int, data: DoctorIn, actor: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    doctor = db.get(Doctor, doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    _validate_doctor_assignment(data, doctor_id, db)
    for key, value in data.model_dump().items():
        setattr(doctor, key, value)
    try:
        _commit_audited(db, actor, "DOCTOR_UPDATED", "DOCTOR", doctor.id,
                        {"department_id": doctor.department_id, "cabin_id": doctor.cabin_id})
        db.refresh(doctor)
        return doctor
    except SQLAlchemyError as error:
        db.rollback()
        logger.exception("doctor update failed", extra={"actor_id": actor.id, "target_id": doctor_id})
        raise HTTPException(status_code=503, detail="Doctor could not be updated.") from error


@router.patch("/{resource}/{record_id}/active")
def set_active(resource: str, record_id: int, active: bool, actor: AdminUser = Depends(require_admin), db: Session = Depends(get_db)):
    models = {"departments": Department, "rooms": Room, "cameras": Camera, "doctors": Doctor}
    model = models.get(resource)
    if not model:
        raise HTTPException(status_code=404, detail="Unknown administration resource")
    record = db.get(model, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if resource == "rooms" and not active and db.query(Camera).filter(Camera.room_id == record_id, Camera.active.is_(True)).first():
        raise HTTPException(status_code=409, detail="Deactivate the room's active camera first")
    if resource == "departments" and not active:
        if db.query(Room).filter(Room.department_id == record_id, Room.active.is_(True)).first() or db.query(Doctor).filter(Doctor.department_id == record_id, Doctor.active.is_(True)).first():
            raise HTTPException(status_code=409, detail="Deactivate assigned rooms and doctors first")
    if resource == "cameras" and active and db.query(Camera).filter(Camera.room_id == record.room_id, Camera.active.is_(True), Camera.id != record_id).first():
        raise HTTPException(status_code=409, detail="Only one active occupancy camera is allowed per room")
    record.active = active
    singular = resource[:-1].upper()
    _commit_audited(db, actor, f"{singular}_{'ACTIVATED' if active else 'DEACTIVATED'}", singular, record.id)
    return {"id": record.id, "active": record.active}
