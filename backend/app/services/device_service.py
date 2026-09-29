"""Kiosk device registration and key authentication."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import DEVICE_KEY_PREFIX, device_key_prefix, new_device_key, sha256_hex
from app.models.schema import Device

DEVICE_STATUSES = ("active", "disabled")


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def _issue_key(device: Device) -> str:
    raw_key = new_device_key()
    device.api_key_hash = sha256_hex(raw_key)
    device.api_key_prefix = device_key_prefix(raw_key)
    device.api_key_rotated_at = datetime.now(UTC)
    return raw_key


def create_device(db: Session, device_code: str, device_name: str, location: str | None) -> tuple[Device, str]:
    """Register a kiosk, or claim a legacy row that has never had a key, and return its raw key once."""
    device = db.scalar(select(Device).where(Device.device_code == device_code))
    if device is not None and (device.api_key_hash is not None and device.deleted_at is None):
        raise AppError(409, "DEVICE_CODE_EXISTS", "Mã thiết bị đã được đăng ký.")
    if device is None:
        device = Device(device_code=device_code, device_name=device_name, location=location, status="active")
        db.add(device)
    else:
        device.device_name, device.location, device.status, device.deleted_at = device_name, location, "active", None
    raw_key = _issue_key(device)
    db.commit()
    db.refresh(device)
    return device, raw_key


def rotate_key(db: Session, device: Device) -> str:
    raw_key = _issue_key(device)
    db.commit()
    db.refresh(device)
    return raw_key


def authenticate(db: Session, raw_key: str | None) -> Device:
    """Resolve an active device from its raw key or raise a 401/403 AppError."""
    if not raw_key:
        raise AppError(401, "DEVICE_KEY_REQUIRED", "Thiết bị kiosk chưa được cấp khóa truy cập.")
    if not raw_key.startswith(DEVICE_KEY_PREFIX) or len(raw_key) > 128:
        raise AppError(401, "DEVICE_KEY_INVALID", "Khóa thiết bị không hợp lệ.")
    device = db.scalar(select(Device).where(Device.api_key_hash == sha256_hex(raw_key)))
    if device is None:
        raise AppError(401, "DEVICE_KEY_INVALID", "Khóa thiết bị không hợp lệ.")
    if device.deleted_at is not None or device.status != "active":
        raise AppError(403, "DEVICE_DISABLED", "Thiết bị kiosk đã bị vô hiệu hóa.")
    now = datetime.now(UTC)
    last_seen = _aware(device.last_seen_at)
    if last_seen is None or now - last_seen >= timedelta(seconds=settings.device_last_seen_interval_seconds):
        device.last_seen_at = now
        db.commit()
    return device


def device_data(device: Device) -> dict:
    return {"id": str(device.id), "device_code": device.device_code, "device_name": device.device_name,
            "location": device.location, "status": device.status, "has_key": device.api_key_hash is not None,
            "key_prefix": device.api_key_prefix,
            "key_rotated_at": _aware(device.api_key_rotated_at).isoformat() if device.api_key_rotated_at else None,
            "last_seen_at": _aware(device.last_seen_at).isoformat() if device.last_seen_at else None}
