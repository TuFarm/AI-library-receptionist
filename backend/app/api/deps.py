"""FastAPI dependencies for authentication and authorization."""
import base64
import binascii
import hashlib
import secrets
from datetime import UTC, datetime

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import AppError
from app.services.admin_auth_service import ensure_configured, read_session, verify_credentials


def _hash_api_key(raw_key: str) -> str:
    """SHA-256 hash of the API key for storage/comparison. Never log the raw key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def validate_kiosk_key(
    x_kiosk_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Validate a kiosk device API key and update its heartbeat."""
    if not x_kiosk_api_key:
        raise AppError(401, "MISSING_API_KEY", "API key không được cung cấp.")

    from app.models.schema import KioskDevice

    device = db.scalar(
        select(KioskDevice).where(KioskDevice.api_key_hash == _hash_api_key(x_kiosk_api_key))
    )
    if device is None:
        raise AppError(401, "INVALID_API_KEY", "API key không hợp lệ.")
    if device.status != "ACTIVE":
        raise AppError(403, "DEVICE_INACTIVE", "Thiết bị không hoạt động.")

    device.last_ping_at = datetime.now(UTC)
    db.commit()
    return device


def _decode_basic_credentials(authorization: str) -> tuple[str, str] | None:
    if not authorization.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(authorization[6:], validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    username, separator, password = decoded.partition(":")
    return (username, password) if separator else None


def require_admin_credentials(
    request: Request,
    authorization: str | None = Header(default=None),
    x_admin_device: str = Header(default="", max_length=128),
):
    """Browser sessions are IP/device bound; Basic remains available to API clients."""
    ensure_configured()
    if not authorization:
        raise AppError(401, "ADMIN_CREDENTIALS_REQUIRED", "Vui lòng đăng nhập quyền quản trị.")
    if authorization.startswith("Bearer "):
        return read_session(authorization[7:], request.client.host if request.client else "",
                            x_admin_device, request.headers.get("user-agent", ""))
    credentials = _decode_basic_credentials(authorization)
    if credentials is None:
        raise AppError(401, "ADMIN_CREDENTIALS_INVALID", "Thông tin đăng nhập quản trị không hợp lệ.")
    username, password = credentials
    verify_credentials(username, password)
    return {"username": username}
