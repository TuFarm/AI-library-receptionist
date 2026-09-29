from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import owned_session, require_kiosk_device
from app.api.v1.routes.face import _user_data
from app.core.database import get_db
from app.core.errors import AppError
from app.core.responses import success_response
from app.models.schema import Device, User, UserSession
from app.schemas.kiosk import KioskEventCreate, KioskSessionEnd, KioskSessionStart
from app.schemas.user import UserProfileUpdate
from app.services.device_service import device_data
from app.services.interaction_service import record_event
from app.services.kiosk_service import end_session, start_session
from app.services.user_service import apply_profile_update, delete_face_profiles

router = APIRouter()


def _identified_user(db: Session, session: UserSession) -> User:
    """Kiosk profile actions are limited to the visitor identified in this live session."""
    user = db.get(User, session.user_id) if session.identified and session.user_id else None
    if user is None or user.deleted_at is not None:
        raise AppError(403, "SESSION_NOT_IDENTIFIED", "Phiên kiosk chưa xác nhận danh tính người dùng.")
    return user


@router.get("/device")
def current_device(device: Device = Depends(require_kiosk_device)) -> dict:
    data = device_data(device)
    return success_response({key: data[key] for key in ("id", "device_code", "device_name", "location", "status")})


@router.post("/sessions/start")
def start(payload: KioskSessionStart, device: Device = Depends(require_kiosk_device),
          db: Session = Depends(get_db)) -> dict:
    # The device comes from its key; `payload.device_code` is kept for client compatibility only.
    session = start_session(db, device)
    return success_response({"session_id": str(session.id), "device_id": str(device.id), "status": "active",
        "next_state": "FACE_SCANNING"}, "Đã bắt đầu phiên kiosk")


@router.post("/sessions/{session_id}/end")
def end(session_id: UUID, payload: KioskSessionEnd, device: Device = Depends(require_kiosk_device),
        db: Session = Depends(get_db)) -> dict:
    owned_session(db, session_id, device)
    session = end_session(db, session_id, payload.exit_reason)
    if session is None: raise AppError(404, "SESSION_NOT_FOUND", "Không tìm thấy phiên kiosk.")
    return success_response({"session_id": str(session.id), "duration_seconds": session.duration_seconds, "next_state": "IDLE"}, "Đã kết thúc phiên kiosk")


@router.post("/sessions/{session_id}/events")
def create_event(session_id: UUID, payload: KioskEventCreate, device: Device = Depends(require_kiosk_device),
                 db: Session = Depends(get_db)) -> dict:
    session = owned_session(db, session_id, device)
    event = record_event(db, session_id=session.id, user_id=session.user_id, device_id=session.device_id,
        event_type=payload.event_type, input_method=payload.input_method,
        content_summary=payload.content_summary, success=payload.success)
    db.commit()
    return success_response({"event_id": str(event.id), "event_type": event.event_type, "event_time": event.event_time.isoformat()})


@router.patch("/sessions/{session_id}/profile")
def update_session_profile(session_id: UUID, payload: UserProfileUpdate,
                           device: Device = Depends(require_kiosk_device), db: Session = Depends(get_db)) -> dict:
    session = owned_session(db, session_id, device, active=True)
    user = apply_profile_update(db, _identified_user(db, session), payload.model_dump(exclude_unset=True))
    record_event(db, event_type="PROFILE_UPDATED", session_id=session.id, user_id=user.id, device_id=device.id)
    db.commit()
    return success_response(_user_data(user), "Cập nhật thông tin thành công.")


@router.delete("/sessions/{session_id}/face-profile")
def delete_session_face_profile(session_id: UUID, device: Device = Depends(require_kiosk_device),
                                db: Session = Depends(get_db)) -> dict:
    session = owned_session(db, session_id, device, active=True)
    user = _identified_user(db, session)
    deleted = delete_face_profiles(db, user.id)
    record_event(db, event_type="FACE_PROFILE_DELETED", session_id=session.id, user_id=user.id, device_id=device.id)
    db.commit()
    return success_response({"user_id": str(user.id), "deleted_profiles": deleted}, "Đã xóa Face ID.")
