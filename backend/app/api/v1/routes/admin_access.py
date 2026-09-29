"""Admin-only management of staff accounts and kiosk devices."""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.core.errors import AppError
from app.core.responses import success_response
from app.models.schema import Device, StaffAccount
from app.schemas.auth import DeviceCreate, DeviceUpdate, StaffCreate, StaffPasswordReset, StaffUpdate
from app.services import device_service
from app.services.staff_auth_service import (
    StaffIdentity, create_staff, reset_password, staff_data, update_staff,
)

router = APIRouter(dependencies=[Depends(require_admin)])


def _staff(db: Session, staff_id: UUID) -> StaffAccount:
    staff = db.get(StaffAccount, staff_id)
    if staff is None:
        raise AppError(404, "STAFF_NOT_FOUND", "Không tìm thấy tài khoản nhân viên.")
    return staff


def _device(db: Session, device_id: UUID) -> Device:
    device = db.get(Device, device_id)
    if device is None or device.deleted_at is not None:
        raise AppError(404, "DEVICE_NOT_FOUND", "Không tìm thấy thiết bị.")
    return device


@router.get("/staff")
def list_staff(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(StaffAccount).order_by(StaffAccount.username)).all()
    return success_response([staff_data(row) for row in rows])


@router.post("/staff", status_code=201)
def add_staff(payload: StaffCreate, db: Session = Depends(get_db)) -> dict:
    staff = create_staff(db, payload.username, payload.full_name, payload.role, payload.password)
    db.commit()
    db.refresh(staff)
    return success_response(staff_data(staff), "Đã tạo tài khoản nhân viên.")


@router.patch("/staff/{staff_id}")
def edit_staff(staff_id: UUID, payload: StaffUpdate, actor: StaffIdentity = Depends(require_admin),
               db: Session = Depends(get_db)) -> dict:
    values = payload.model_dump(exclude_unset=True)
    if not values or any(value is None for value in values.values()):
        raise AppError(422, "VALIDATION_ERROR", "Không có thay đổi hợp lệ.")
    staff = update_staff(db, actor, _staff(db, staff_id), **values)
    return success_response(staff_data(staff), "Đã cập nhật tài khoản nhân viên.")


@router.post("/staff/{staff_id}/reset-password")
def reset_staff_password(staff_id: UUID, payload: StaffPasswordReset, db: Session = Depends(get_db)) -> dict:
    reset_password(db, _staff(db, staff_id), payload.new_password)
    return success_response(None, "Đã đặt lại mật khẩu và thu hồi mọi phiên đăng nhập của tài khoản.")


@router.get("/devices")
def list_devices(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Device).where(Device.deleted_at.is_(None)).order_by(Device.device_code)).all()
    return success_response([device_service.device_data(row) for row in rows])


@router.post("/devices", status_code=201)
def add_device(payload: DeviceCreate, db: Session = Depends(get_db)) -> dict:
    device, raw_key = device_service.create_device(db, payload.device_code, payload.device_name.strip(),
                                                   payload.location.strip() if payload.location else None)
    return success_response({**device_service.device_data(device), "device_key": raw_key},
                            "Đã đăng ký thiết bị. Khóa chỉ hiển thị một lần, hãy nhập ngay vào kiosk.")


@router.patch("/devices/{device_id}")
def edit_device(device_id: UUID, payload: DeviceUpdate, db: Session = Depends(get_db)) -> dict:
    device = _device(db, device_id)
    values = payload.model_dump(exclude_unset=True)
    if not values or values.get("device_name", "") is None or values.get("status", "") is None:
        raise AppError(422, "VALIDATION_ERROR", "Không có thay đổi hợp lệ.")
    for field, value in values.items():
        setattr(device, field, value.strip() if isinstance(value, str) and field != "status" else value)
    db.commit()
    db.refresh(device)
    return success_response(device_service.device_data(device), "Đã cập nhật thiết bị.")


@router.post("/devices/{device_id}/rotate-key")
def rotate_device_key(device_id: UUID, db: Session = Depends(get_db)) -> dict:
    device = _device(db, device_id)
    raw_key = device_service.rotate_key(db, device)
    return success_response({**device_service.device_data(device), "device_key": raw_key},
                            "Đã cấp khóa mới. Khóa cũ không còn hiệu lực.")
