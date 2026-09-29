from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.schema import Device, UserSession
from app.services.interaction_service import record_event


def start_session(db: Session, device: Device) -> UserSession:
    session = UserSession(device_id=device.id, user_id=None, identified=False, started_at=datetime.now(UTC))
    db.add(session); db.flush()
    record_event(db, event_type="SESSION_STARTED", session_id=session.id, device_id=device.id)
    db.commit(); db.refresh(session)
    return session


def end_session(db: Session, session_id: UUID, exit_reason: str) -> UserSession | None:
    session = db.get(UserSession, session_id)
    if session is None: return None
    now = datetime.now(UTC)
    started = session.started_at if session.started_at.tzinfo else session.started_at.replace(tzinfo=UTC)
    session.ended_at = now; session.duration_seconds = max(0, int((now - started).total_seconds())); session.exit_reason = exit_reason
    record_event(db, event_type="SESSION_ENDED", session_id=session.id, user_id=session.user_id,
        device_id=session.device_id, content_summary=exit_reason)
    db.commit(); db.refresh(session)
    return session
