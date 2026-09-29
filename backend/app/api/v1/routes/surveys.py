from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.api.deps import owned_session, require_kiosk_device
from app.core.database import get_db
from app.core.errors import AppError
from app.core.responses import success_response
from app.schemas.survey import SurveySubmission
from app.models.schema import Device, Survey, SurveyAnswer, SurveyQuestion, SurveyResponse
from app.services.interaction_service import record_event

router = APIRouter()

@router.get("/active/mock")
async def active() -> dict:
    texts = [("q1", "Bạn có hài lòng với câu trả lời của AI không?", "rating"), ("q2", "AI có giúp bạn giảm thời gian hỏi lễ tân không?", "yes_no"), ("q3", "Bạn có muốn sử dụng kiosk này lần sau không?", "yes_no"), ("q4", "Bạn đánh giá tốc độ phản hồi của AI như thế nào?", "rating")]
    return success_response({"id": "survey-2026-01", "name": "Khảo sát trải nghiệm kiosk", "questions": [{"id": i, "text": t, "type": k} for i, t, k in texts]})

@router.post("/{survey_id}/responses/mock")
async def submit(survey_id: str, payload: SurveySubmission) -> dict:
    return success_response({"survey_id": survey_id, "answer_count": len(payload.answers), "stored": False}, "Cảm ơn bạn đã gửi phản hồi!")


@router.get("/active")
def active_database_survey(db: Session = Depends(get_db)) -> dict:
    survey = db.scalar(select(Survey).options(selectinload(Survey.questions)).where(
        Survey.active.is_(True), Survey.deleted_at.is_(None)).order_by(Survey.version.desc()))
    if survey is None: return success_response(None, "Hiện chưa có khảo sát đang hoạt động.")
    questions = sorted(survey.questions, key=lambda question: question.question_order)
    return success_response({"id": str(survey.id), "name": survey.survey_name, "description": survey.description,
        "version": survey.version, "questions": [{"id": str(q.id), "text": q.question_text,
        "type": q.question_type, "order": q.question_order} for q in questions]})


@router.post("/{survey_id}/responses")
def submit_database_survey(survey_id: UUID, payload: SurveySubmission, device: Device = Depends(require_kiosk_device),
                           db: Session = Depends(get_db)) -> dict:
    session = owned_session(db, payload.session_id, device, required=False)
    if payload.user_id is not None and (session is None or payload.user_id != session.user_id):
        raise AppError(403, "SESSION_NOT_IDENTIFIED", "Người dùng không thuộc phiên kiosk này.")
    survey = db.get(Survey, survey_id)
    if survey is None or not survey.active: raise AppError(404, "SURVEY_NOT_FOUND", "Không tìm thấy khảo sát đang hoạt động.")
    response = SurveyResponse(survey_id=survey.id, user_id=payload.user_id, session_id=payload.session_id, submitted_at=datetime.now(UTC))
    db.add(response); db.flush()
    saved = 0
    for question_id_text, value in payload.answers.items():
        try: question_id = UUID(question_id_text)
        except ValueError as exc: raise AppError(422, "INVALID_QUESTION_ID", f"Mã câu hỏi không hợp lệ: {question_id_text}") from exc
        question = db.scalar(select(SurveyQuestion).where(SurveyQuestion.id == question_id, SurveyQuestion.survey_id == survey.id))
        if question is None: raise AppError(422, "QUESTION_NOT_FOUND", "Câu hỏi không thuộc khảo sát này.")
        answer_text = None; answer_number = None
        if isinstance(value, (int, float)):
            try: answer_number = Decimal(str(value))
            except InvalidOperation: answer_text = str(value)
        else: answer_text = str(value)
        db.add(SurveyAnswer(response_id=response.id, question_id=question.id, answer_text=answer_text, answer_number=answer_number)); saved += 1
    if session is not None:
        record_event(db, event_type="SURVEY_SUBMITTED", session_id=session.id, user_id=payload.user_id,
            device_id=device.id, content_summary=f"{saved} answers")
    db.commit()
    return success_response({"response_id": str(response.id), "survey_id": str(survey.id), "answer_count": saved}, "Cảm ơn bạn đã gửi phản hồi!")
