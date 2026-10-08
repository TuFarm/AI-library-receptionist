"""Read-only conversation logs for staff, including which answers had no knowledge source."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, exists, func, select
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.database import get_db
from app.core.errors import AppError
from app.core.responses import success_response
from app.models.schema import AIRequest, AIResponse, Conversation, ConversationMessage, Device, User, UserSession
from app.services.admin_dashboard_service import report_window

router = APIRouter(dependencies=[Depends(require_staff)])


def _ungrounded_answer():
    return exists().where(AIRequest.conversation_id == Conversation.id, AIResponse.ai_request_id == AIRequest.id,
                          AIResponse.grounded.is_not(True))


@router.get("")
def list_conversations(days: int = Query(default=7, ge=1, le=90), search: str = Query(default="", max_length=200),
                       ungrounded: bool = Query(default=False), offset: int = Query(default=0, ge=0),
                       limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    since, now = report_window(days)
    query = (select(Conversation, UserSession, Device, User)
             .outerjoin(UserSession, Conversation.session_id == UserSession.id)
             .outerjoin(Device, UserSession.device_id == Device.id)
             .outerjoin(User, Conversation.user_id == User.id)
             .where(Conversation.started_at.between(since, now)))
    if search.strip():
        query = query.where(exists().where(ConversationMessage.conversation_id == Conversation.id,
                                           ConversationMessage.message_text.ilike(f"%{search.strip()}%")))
    if ungrounded:
        query = query.where(_ungrounded_answer())
    total = db.scalar(select(func.count()).select_from(query.with_only_columns(Conversation.id).subquery())) or 0
    rows = db.execute(query.order_by(Conversation.started_at.desc()).offset(offset).limit(limit)).all()
    ids = [conversation.id for conversation, *_ in rows]

    message_counts = dict(db.execute(select(ConversationMessage.conversation_id, func.count(ConversationMessage.id))
                                     .where(ConversationMessage.conversation_id.in_(ids))
                                     .group_by(ConversationMessage.conversation_id)).all()) if ids else {}
    answer_stats = {cid: (answers, grounded) for cid, answers, grounded in db.execute(
        select(AIRequest.conversation_id, func.count(AIResponse.id),
               func.sum(case((AIResponse.grounded.is_(True), 1), else_=0)))
        .join(AIResponse, AIResponse.ai_request_id == AIRequest.id)
        .where(AIRequest.conversation_id.in_(ids)).group_by(AIRequest.conversation_id)).all()} if ids else {}
    first_question = {}
    if ids:
        first = (select(ConversationMessage.conversation_id, func.min(ConversationMessage.message_time).label("first_time"))
                 .where(ConversationMessage.conversation_id.in_(ids), ConversationMessage.sender_type == "USER")
                 .group_by(ConversationMessage.conversation_id).subquery())
        first_question = dict(db.execute(select(ConversationMessage.conversation_id, ConversationMessage.message_text)
                                         .join(first, and_(ConversationMessage.conversation_id == first.c.conversation_id,
                                                           ConversationMessage.message_time == first.c.first_time))
                                         .where(ConversationMessage.sender_type == "USER")).all())

    items = []
    for conversation, session, device, user in rows:
        answers, grounded = answer_stats.get(conversation.id, (0, 0))
        items.append({"id": str(conversation.id), "started_at": conversation.started_at.isoformat(),
                      "status": conversation.status, "device_code": device.device_code if device else None,
                      "visitor": {"full_name": user.full_name, "student_code": user.student_code} if user else None,
                      "identified": bool(session and session.identified), "message_count": message_counts.get(conversation.id, 0),
                      "first_question": first_question.get(conversation.id), "answer_count": answers,
                      "grounded_count": int(grounded or 0)})
    return success_response({"items": items, "total": total})


@router.get("/{conversation_id}")
def get_conversation(conversation_id: UUID, db: Session = Depends(get_db)) -> dict:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise AppError(404, "CONVERSATION_NOT_FOUND", "Không tìm thấy hội thoại.")
    messages = db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conversation.id)
                          .order_by(ConversationMessage.message_time)).all()
    details = {message_id: (response, request) for response, request, message_id in db.execute(
        select(AIResponse, AIRequest, AIResponse.ai_message_id).join(AIRequest, AIResponse.ai_request_id == AIRequest.id)
        .where(AIRequest.conversation_id == conversation.id)).all()}
    user = db.get(User, conversation.user_id) if conversation.user_id else None
    data = []
    for message in messages:
        item = {"id": str(message.id), "sender_type": message.sender_type, "text": message.message_text or "",
                "input_method": message.input_method, "time": message.message_time.isoformat()}
        if message.id in details:
            response, request = details[message.id]
            item["ai"] = {"grounded": bool(response.grounded), "citations": response.citations or [],
                          "model_name": request.model_name, "status": request.status, "latency_ms": request.latency_ms}
        data.append(item)
    return success_response({"id": str(conversation.id), "started_at": conversation.started_at.isoformat(),
                             "status": conversation.status,
                             "visitor": {"full_name": user.full_name, "student_code": user.student_code} if user else None,
                             "messages": data})
