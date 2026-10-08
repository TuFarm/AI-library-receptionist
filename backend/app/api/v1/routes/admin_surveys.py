from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.database import get_db
from app.core.responses import success_response
from app.models.schema import Survey
from app.schemas.survey import SurveyCreate, SurveyUpdate
from app.services import survey_service

router = APIRouter(dependencies=[Depends(require_staff)])


def _survey_data(survey: Survey, response_count: int) -> dict:
    return {"id": str(survey.id), "survey_name": survey.survey_name, "description": survey.description,
            "version": survey.version, "active": survey.active, "response_count": response_count,
            "questions": [{"id": str(q.id), "question_text": q.question_text, "question_type": q.question_type,
                           "question_order": q.question_order} for q in survey_service.ordered_questions(survey)],
            "created_at": survey.created_at.isoformat() if survey.created_at else None}


def _single(db: Session, survey: Survey) -> dict:
    return _survey_data(survey, survey_service.response_counts(db, [survey.id]).get(survey.id, 0))


@router.get("")
def list_surveys(db: Session = Depends(get_db)) -> dict:
    surveys = survey_service.list_surveys(db)
    counts = survey_service.response_counts(db, [survey.id for survey in surveys])
    return success_response([_survey_data(survey, counts.get(survey.id, 0)) for survey in surveys])


@router.post("", status_code=201)
def create_survey(payload: SurveyCreate, db: Session = Depends(get_db)) -> dict:
    return success_response(_single(db, survey_service.create(db, payload)), "Đã tạo khảo sát (chưa kích hoạt).")


@router.get("/{survey_id}")
def get_survey(survey_id: UUID, db: Session = Depends(get_db)) -> dict:
    return success_response(_single(db, survey_service.get_survey(db, survey_id)))


@router.patch("/{survey_id}")
def update_survey(survey_id: UUID, payload: SurveyUpdate, db: Session = Depends(get_db)) -> dict:
    return success_response(_single(db, survey_service.update(db, survey_id, payload)), "Đã cập nhật khảo sát.")


@router.post("/{survey_id}/activate")
def activate_survey(survey_id: UUID, db: Session = Depends(get_db)) -> dict:
    return success_response(_single(db, survey_service.set_active(db, survey_id, True)), "Kiosk sẽ hiển thị khảo sát này.")


@router.post("/{survey_id}/deactivate")
def deactivate_survey(survey_id: UUID, db: Session = Depends(get_db)) -> dict:
    return success_response(_single(db, survey_service.set_active(db, survey_id, False)), "Đã tắt khảo sát.")


@router.post("/{survey_id}/duplicate", status_code=201)
def duplicate_survey(survey_id: UUID, db: Session = Depends(get_db)) -> dict:
    return success_response(_single(db, survey_service.duplicate(db, survey_id)), "Đã tạo phiên bản mới để chỉnh sửa.")


@router.delete("/{survey_id}")
def delete_survey(survey_id: UUID, db: Session = Depends(get_db)) -> dict:
    survey_service.remove(db, survey_id)
    return success_response({"id": str(survey_id)}, "Đã xóa khảo sát. Phản hồi cũ vẫn được giữ.")


@router.get("/{survey_id}/results")
def survey_results(survey_id: UUID, db: Session = Depends(get_db)) -> dict:
    return success_response(survey_service.results(db, survey_id))
