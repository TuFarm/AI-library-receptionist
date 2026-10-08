"""Survey management for staff and answer validation for kiosk submissions.

At most one survey is active; the kiosk shows it. Once a survey has responses its questions
are frozen so stored answers keep their meaning: staff duplicate it as a new version instead.
"""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.models.schema import Survey, SurveyAnswer, SurveyQuestion, SurveyResponse
from app.schemas.survey import MAX_TEXT_ANSWER, YES_NO_CHOICES, SurveyCreate, SurveyQuestionInput, SurveyUpdate


def response_counts(db: Session, survey_ids: list[UUID]) -> dict[UUID, int]:
    if not survey_ids:
        return {}
    rows = db.execute(select(SurveyResponse.survey_id, func.count(SurveyResponse.id))
                      .where(SurveyResponse.survey_id.in_(survey_ids)).group_by(SurveyResponse.survey_id)).all()
    return dict(rows)


def get_survey(db: Session, survey_id: UUID) -> Survey:
    survey = db.scalar(select(Survey).options(selectinload(Survey.questions)).where(Survey.id == survey_id))
    if survey is None or survey.deleted_at is not None:
        raise AppError(404, "SURVEY_NOT_FOUND", "Không tìm thấy khảo sát.")
    return survey


def ordered_questions(survey: Survey) -> list[SurveyQuestion]:
    return sorted(survey.questions, key=lambda question: question.question_order)


def list_surveys(db: Session) -> list[Survey]:
    return list(db.scalars(select(Survey).options(selectinload(Survey.questions))
                           .where(Survey.deleted_at.is_(None))
                           .order_by(Survey.active.desc(), Survey.created_at.desc())).all())


def _next_version(db: Session, name: str) -> int:
    return (db.scalar(select(func.max(Survey.version)).where(Survey.survey_name == name)) or 0) + 1


def _replace_questions(db: Session, survey: Survey, questions: list[SurveyQuestionInput]) -> None:
    for question in list(survey.questions):
        survey.questions.remove(question)
        db.delete(question)
    db.flush()  # the unique (survey_id, question_order) slots must be free before re-adding
    for order, question in enumerate(questions, start=1):
        survey.questions.append(SurveyQuestion(question_text=question.question_text,
                                               question_type=question.question_type, question_order=order))


def create(db: Session, payload: SurveyCreate) -> Survey:
    survey = Survey(survey_name=payload.survey_name, description=payload.description or None,
                    version=_next_version(db, payload.survey_name), active=False)
    db.add(survey)
    _replace_questions(db, survey, payload.questions)
    db.commit()
    return get_survey(db, survey.id)


def update(db: Session, survey_id: UUID, payload: SurveyUpdate) -> Survey:
    survey = get_survey(db, survey_id)
    if payload.questions is not None:
        if response_counts(db, [survey.id]).get(survey.id):
            raise AppError(409, "SURVEY_HAS_RESPONSES",
                           "Khảo sát đã có phản hồi nên không thể sửa câu hỏi. Hãy tạo phiên bản mới.")
        _replace_questions(db, survey, payload.questions)
    if payload.survey_name is not None and payload.survey_name != survey.survey_name:
        survey.version = _next_version(db, payload.survey_name)
        survey.survey_name = payload.survey_name
    if "description" in payload.model_fields_set:
        survey.description = payload.description or None
    db.commit()
    return get_survey(db, survey.id)


def duplicate(db: Session, survey_id: UUID) -> Survey:
    source = get_survey(db, survey_id)
    copy = Survey(survey_name=source.survey_name, description=source.description,
                  version=_next_version(db, source.survey_name), active=False)
    db.add(copy)
    _replace_questions(db, copy, [SurveyQuestionInput(question_text=q.question_text, question_type=q.question_type)
                                  for q in ordered_questions(source)])
    db.commit()
    return get_survey(db, copy.id)


def set_active(db: Session, survey_id: UUID, active: bool) -> Survey:
    survey = get_survey(db, survey_id)
    if active:
        if not survey.questions:
            raise AppError(409, "SURVEY_HAS_NO_QUESTIONS", "Khảo sát cần ít nhất một câu hỏi.")
        for other in db.scalars(select(Survey).where(Survey.active.is_(True), Survey.id != survey.id)).all():
            other.active = False
    survey.active = active
    db.commit()
    return get_survey(db, survey.id)


def remove(db: Session, survey_id: UUID) -> None:
    survey = get_survey(db, survey_id)
    survey.active = False
    survey.deleted_at = datetime.now(UTC)
    db.commit()


def results(db: Session, survey_id: UUID) -> dict:
    survey = get_survey(db, survey_id)
    rows = db.execute(select(SurveyAnswer.question_id, SurveyAnswer.answer_number, SurveyAnswer.answer_text,
                             SurveyResponse.submitted_at)
                      .join(SurveyResponse, SurveyAnswer.response_id == SurveyResponse.id)
                      .where(SurveyResponse.survey_id == survey.id)
                      .order_by(SurveyResponse.submitted_at.desc())).all()
    by_question: dict[UUID, list] = {}
    for question_id, number, text, submitted_at in rows:
        by_question.setdefault(question_id, []).append((number, text, submitted_at))
    questions = []
    for question in ordered_questions(survey):
        answers = by_question.get(question.id, [])
        item = {"id": str(question.id), "text": question.question_text, "type": question.question_type,
                "answer_count": len(answers)}
        if question.question_type == "rating":
            numbers = [int(number) for number, _, _ in answers if number is not None]
            counts = Counter(numbers)
            item["average"] = round(sum(numbers) / len(numbers), 2) if numbers else None
            item["distribution"] = {str(score): counts.get(score, 0) for score in range(1, 6)}
        elif question.question_type == "yes_no":
            counts = Counter(text for _, text, _ in answers)
            item["distribution"] = {choice: counts.get(choice, 0) for choice in YES_NO_CHOICES}
        else:
            item["recent_answers"] = [{"text": text, "submitted_at": submitted_at.isoformat()}
                                      for _, text, submitted_at in answers[:20] if text]
        questions.append(item)
    return {"survey_id": str(survey.id), "response_count": response_counts(db, [survey.id]).get(survey.id, 0),
            "questions": questions}


def parse_answer(question: SurveyQuestion, value: object) -> tuple[str | None, Decimal | None]:
    """Validate one kiosk answer against its question type → (answer_text, answer_number)."""
    invalid = AppError(422, "INVALID_SURVEY_ANSWER", f"Câu trả lời không hợp lệ cho câu hỏi: {question.question_text}")
    if question.question_type == "rating":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) or not 1 <= value <= 5:
            raise invalid
        return None, Decimal(int(value))
    if question.question_type == "yes_no":
        if value not in YES_NO_CHOICES:
            raise invalid
        return str(value), None
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT_ANSWER:
        raise invalid
    return value.strip(), None
