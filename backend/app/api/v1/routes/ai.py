from datetime import UTC, datetime
from time import perf_counter

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import owned_conversation, require_kiosk_device
from app.core.database import get_db
from app.core.errors import AppError
from app.core.responses import success_response
from app.models.schema import AIRequest, AIResponse, Conversation, ConversationMessage, Device, UserSession
from app.schemas.ai import AIRuntimeRequest, AIAnswerRequest
from app.services.ai_service import AIService
from app.services.conversation_service import save_message
from app.services.interaction_service import record_event
from app.services.rag_service import retrieve

router = APIRouter()


@router.post("/answer")
def runtime_answer(payload: AIRuntimeRequest, device: Device = Depends(require_kiosk_device),
                   db: Session = Depends(get_db)) -> dict:
    conversation = owned_conversation(db, payload.conversation_id, device)
    if payload.session_id is not None and conversation.session_id != payload.session_id:
        raise AppError(404, "CONVERSATION_NOT_FOUND", "Không tìm thấy hội thoại.")
    return answer_turn(payload, db)


def answer_turn(payload: AIRuntimeRequest, db: Session) -> dict:
    """Run one AI turn. Callers must already have verified the conversation's device ownership."""
    conversation = db.get(Conversation, payload.conversation_id)
    if conversation is None: raise AppError(404, "CONVERSATION_NOT_FOUND", "Không tìm thấy hội thoại.")
    history_rows = list(reversed(db.scalars(select(ConversationMessage).where(
        ConversationMessage.conversation_id == conversation.id
    ).order_by(ConversationMessage.message_time.desc()).limit(10)).all()))
    if history_rows and history_rows[-1].sender_type == "USER" and history_rows[-1].message_text == payload.message_text:
        history_rows.pop()
    history = [{"role": "model" if row.sender_type == "ASSISTANT" else "user", "text": row.message_text or ""}
        for row in history_rows if row.sender_type in {"USER", "ASSISTANT"} and row.message_text]
    user_message = save_message(db, conversation, "USER", payload.message_text, "TEXT") if payload.save_user_message else db.scalar(
        select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation.id,
            ConversationMessage.sender_type == "USER",
        ).order_by(ConversationMessage.message_time.desc())
    )
    started = perf_counter()
    context = retrieve(db, payload.message_text)
    answer = AIService().answer(payload.message_text, history, context)
    latency = int((perf_counter() - started) * 1000)
    request = AIRequest(conversation_id=conversation.id, user_message_id=user_message.id if user_message else None,
        request_type="library_qa_rag" if context else "library_qa", model_name=answer.model_name, input_token_count=None,
        output_token_count=None, latency_ms=latency,
        status="failed" if answer.provider_error else ("fallback" if answer.used_fallback else "completed"))
    db.add(request); db.flush()
    ai_message = ConversationMessage(conversation_id=conversation.id, sender_type="ASSISTANT", message_text=answer.text,
        input_method="SYSTEM", message_time=datetime.now(UTC))
    db.add(ai_message); db.flush()
    response = AIResponse(ai_request_id=request.id, ai_message_id=ai_message.id, response_text=answer.text,
        response_summary=answer.text[:500], grounded=answer.grounded, confidence_score=answer.confidence_score,
        citations=answer.citations or None)
    db.add(response)
    session = db.get(UserSession, payload.session_id) if payload.session_id else None
    record_event(db, event_type="AI_ANSWERED", session_id=payload.session_id, user_id=conversation.user_id,
        device_id=session.device_id if session else None, input_method="TEXT",
        content_summary=answer.text[:500], success=not answer.used_fallback)
    db.commit()
    return success_response({"answer": answer.text, "provider": answer.provider, "model_name": answer.model_name,
        "grounded": answer.grounded, "citations": answer.citations, "confidence_score": answer.confidence_score, "latency_ms": latency,
        "warning": answer.warning, "next_state": "AI_VOICE_CHAT"}, "Đã tạo câu trả lời.")


@router.post("/answer/mock", dependencies=[Depends(require_kiosk_device)])
def mock_answer(payload: AIAnswerRequest) -> dict:
    # May call the real AI provider, so it is not public.
    answer = AIService().answer(payload.question)
    return success_response({"question": payload.question, "answer": answer.text, "request_type": "library_qa",
        "model_name": answer.model_name, "grounded": False, "confidence_score": answer.confidence_score, "latency_ms": 0})
