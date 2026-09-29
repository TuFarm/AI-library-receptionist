from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import owned_conversation, owned_session, require_kiosk_device
from app.core.database import get_db
from app.core.errors import AppError
from app.core.responses import success_response
from app.models.schema import Conversation, Device
from app.schemas.voice import BrowserTranscriptCreate
from app.services.conversation_service import save_message
from app.services.media_storage_service import MediaStorageService, MediaValidationError
from app.services.voice_service import VoiceService
from app.services.interaction_service import record_event
from app.models.schema import UserSession

router = APIRouter()


@router.post("/transcribe")
async def transcribe(session_id: UUID | None = Form(default=None), conversation_id: UUID | None = Form(default=None),
                     audio_file: UploadFile = File(), device: Device = Depends(require_kiosk_device),
                     db: Session = Depends(get_db)) -> dict:
    owned_session(db, session_id, device, required=False)
    if conversation_id:
        owned_conversation(db, conversation_id, device)
    storage = MediaStorageService()
    try:
        path = await storage.save_audio(audio_file)
        result = VoiceService().transcribe(path)
        message_id = None
        conversation = None
        if conversation_id and result.transcript:
            conversation = db.get(Conversation, conversation_id)
            if conversation is None: raise AppError(404, "CONVERSATION_NOT_FOUND", "Không tìm thấy hội thoại.")
            session = db.get(UserSession, session_id) if session_id and conversation.session_id is None else None
            if session_id and conversation.session_id is None and session is None:
                raise AppError(404, "SESSION_NOT_FOUND", "Không tìm thấy phiên kiosk.")
            message = save_message(db, conversation, "USER", result.transcript, "VOICE"); message_id = str(message.id)
            if session_id and conversation.session_id is None:
                record_event(db, event_type="QUESTION_ASKED", session_id=session_id, user_id=conversation.user_id,
                    device_id=session.device_id, input_method="VOICE", content_summary=result.transcript[:500]); db.commit()
        elif session_id and result.transcript:
            session = db.get(UserSession, session_id)
            if session is None: raise AppError(404, "SESSION_NOT_FOUND", "Không tìm thấy phiên kiosk.")
            record_event(db, event_type="QUESTION_ASKED", session_id=session_id, user_id=session.user_id,
                device_id=session.device_id, input_method="VOICE", content_summary=result.transcript[:500]); db.commit()
        return success_response({"transcript": result.transcript, "provider": result.provider,
            "confidence_score": result.confidence_score, "warning": result.warning, "message_id": message_id}, "Đã xử lý giọng nói.")
    except MediaValidationError as exc: raise AppError(400, "INVALID_AUDIO", str(exc)) from exc
    finally:
        if "path" in locals(): storage.cleanup(path)


@router.post("/browser-transcript")
def browser_transcript(payload: BrowserTranscriptCreate, device: Device = Depends(require_kiosk_device),
                       db: Session = Depends(get_db)) -> dict:
    conversation = owned_conversation(db, payload.conversation_id, device)
    if payload.session_id is not None and conversation.session_id != payload.session_id:
        raise AppError(404, "CONVERSATION_NOT_FOUND", "Không tìm thấy hội thoại.")
    return save_browser_transcript(payload, db)


def save_browser_transcript(payload: BrowserTranscriptCreate, db: Session) -> dict:
    """Persist a browser STT result. Callers must already have verified device ownership."""
    conversation = db.get(Conversation, payload.conversation_id)
    if conversation is None: raise AppError(404, "CONVERSATION_NOT_FOUND", "Không tìm thấy hội thoại.")
    session = db.get(UserSession, payload.session_id) if payload.session_id and conversation.session_id is None else None
    if payload.session_id and conversation.session_id is None and session is None:
        raise AppError(404, "SESSION_NOT_FOUND", "Không tìm thấy phiên kiosk.")
    message = save_message(db, conversation, "USER", payload.transcript, "VOICE")
    if payload.session_id and conversation.session_id is None:
        record_event(db, event_type="QUESTION_ASKED", session_id=payload.session_id, user_id=conversation.user_id,
            device_id=session.device_id, input_method="VOICE", content_summary=payload.transcript[:500]); db.commit()
    return success_response({"message_id": str(message.id), "transcript": payload.transcript,
        "provider": "browser", "confidence_score": payload.confidence_score}, "Đã lưu bản ghi giọng nói từ trình duyệt.")
