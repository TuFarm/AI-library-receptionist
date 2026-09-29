"""FastAPI dependencies for staff authorization and kiosk device authentication."""
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.models.schema import Conversation, Device, UserSession
from app.services import device_service
from app.services.staff_auth_service import StaffIdentity, client_binding, read_session


def request_binding(request: Request, x_admin_device: str = Header(default="", max_length=128)) -> str:
    return client_binding(request.client.host if request.client else "", x_admin_device,
                          request.headers.get("user-agent", ""))


def login_binding(request: Request, x_admin_device: str = Header(min_length=16, max_length=128)) -> str:
    """Login requires the browser's random device ID so the new session can be bound to it."""
    return request_binding(request, x_admin_device)


def get_current_staff(
    authorization: str | None = Header(default=None),
    binding: str = Depends(request_binding),
    db: Session = Depends(get_db),
) -> StaffIdentity:
    if not authorization:
        raise AppError(401, "ADMIN_CREDENTIALS_REQUIRED", "Vui lòng đăng nhập quyền quản trị.")
    if not authorization.startswith("Bearer ") or not authorization[7:].strip():
        raise AppError(401, "ADMIN_CREDENTIALS_INVALID", "Thông tin đăng nhập quản trị không hợp lệ.")
    return read_session(db, authorization[7:].strip(), binding)


def require_staff(staff: StaffIdentity = Depends(get_current_staff)) -> StaffIdentity:
    """Any active staff role (admin or librarian)."""
    return staff


def require_admin(staff: StaffIdentity = Depends(get_current_staff)) -> StaffIdentity:
    if not staff.is_admin:
        raise AppError(403, "ADMIN_ROLE_REQUIRED", "Chức năng này chỉ dành cho quản trị viên.")
    return staff


def require_kiosk_device(
    x_device_key: str | None = Header(default=None, max_length=128),
    db: Session = Depends(get_db),
) -> Device:
    return device_service.authenticate(db, x_device_key)


def owned_session(db: Session, session_id: UUID | None, device: Device, *, required: bool = True,
                  active: bool = False) -> UserSession | None:
    """Return the kiosk session only if it was started by this device.

    A foreign session is reported as not found so a device cannot probe other kiosks' IDs.
    """
    if session_id is None:
        if required:
            raise AppError(422, "SESSION_REQUIRED", "Thiếu mã phiên kiosk.")
        return None
    session = db.get(UserSession, session_id)
    if session is None or session.device_id != device.id:
        raise AppError(404, "SESSION_NOT_FOUND", "Không tìm thấy phiên kiosk.")
    if active and session.ended_at is not None:
        raise AppError(409, "SESSION_ENDED", "Phiên kiosk đã kết thúc.")
    return session


def owned_conversation(db: Session, conversation_id: UUID, device: Device) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    session = db.get(UserSession, conversation.session_id) if conversation and conversation.session_id else None
    if conversation is None or session is None or session.device_id != device.id:
        raise AppError(404, "CONVERSATION_NOT_FOUND", "Không tìm thấy hội thoại.")
    return conversation
