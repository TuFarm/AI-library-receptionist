from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import owned_conversation, owned_session, require_kiosk_device
from app.core.database import get_db
from app.core.errors import AppError
from app.core.responses import success_response
from app.models.schema import ConversationMessage, Device
from app.schemas.conversation import ConversationMessageCreate, ConversationStart
from app.services.conversation_service import save_message, start_conversation

router = APIRouter()


@router.post("/start")
def start(payload: ConversationStart, device: Device = Depends(require_kiosk_device),
          db: Session = Depends(get_db)) -> dict:
    session = owned_session(db, payload.session_id, device, active=True)
    if payload.user_id is not None and payload.user_id != session.user_id:
        raise AppError(403, "SESSION_NOT_IDENTIFIED", "Người dùng không thuộc phiên kiosk này.")
    conversation = start_conversation(db, payload.session_id, payload.user_id)
    return success_response({"conversation_id": str(conversation.id), "status": conversation.status})


@router.post("/{conversation_id}/messages")
def create_message(conversation_id: UUID, payload: ConversationMessageCreate,
                   device: Device = Depends(require_kiosk_device), db: Session = Depends(get_db)) -> dict:
    conversation = owned_conversation(db, conversation_id, device)
    message = save_message(db, conversation, payload.sender_type, payload.message_text, payload.input_method)
    return success_response({"id": str(message.id), "conversation_id": str(conversation_id), "sender_type": message.sender_type,
        "message_text": message.message_text, "input_method": message.input_method, "message_time": message.message_time.isoformat()})


@router.get("/{conversation_id}/messages")
def get_messages(conversation_id: UUID, device: Device = Depends(require_kiosk_device),
                 db: Session = Depends(get_db)) -> dict:
    owned_conversation(db, conversation_id, device)
    messages = db.scalars(select(ConversationMessage).where(
        ConversationMessage.conversation_id == conversation_id
    ).order_by(ConversationMessage.message_time)).all()
    return success_response([{"id": str(message.id),
        "role": "assistant" if message.sender_type == "ASSISTANT" else "user",
        "text": message.message_text or "", "inputMethod": message.input_method}
        for message in messages])
