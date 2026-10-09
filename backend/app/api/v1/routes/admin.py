from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff, login_binding, require_staff
from app.core.config import settings
from app.core.database import get_db
from app.core.responses import success_response
from app.models.schema import AIRequest, AIResponse, KnowledgeDocument, FaceAuthenticationLog, InteractionEvent, SurveyResponse, UserSession
from app.schemas.auth import AdminLoginRequest, AdminPasswordChange
from app.services.admin_dashboard_service import daily_sessions, report_window
from app.services.report_service import average_satisfaction, job_state
from app.services.staff_auth_service import StaffIdentity, change_password, login, revoke_session

login_router = APIRouter()
router = APIRouter(dependencies=[Depends(require_staff)])


@login_router.post("/login")
def admin_login(credentials: AdminLoginRequest, binding: str = Depends(login_binding),
                db: Session = Depends(get_db)) -> dict:
    token, identity = login(db, credentials.username, credentials.password, binding)
    return success_response({"token": token, **identity.public()}, "Đăng nhập quản trị thành công.")


@router.get("/session")
def session_info(identity: StaffIdentity = Depends(get_current_staff)) -> dict:
    return success_response(identity.public())


@router.post("/logout")
def logout(identity: StaffIdentity = Depends(get_current_staff), db: Session = Depends(get_db)) -> dict:
    revoke_session(db, identity.token_hash)
    return success_response(None, "Đã đăng xuất.")


@router.post("/password")
def update_password(payload: AdminPasswordChange, identity: StaffIdentity = Depends(get_current_staff),
                    db: Session = Depends(get_db)) -> dict:
    change_password(db, identity.id, payload.current_password, payload.new_password)
    return success_response(None, "Đã đổi mật khẩu. Vui lòng đăng nhập lại.")


@router.get("/dashboard")
def live_dashboard(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> dict:
    since, now = report_window(days)
    sessions = db.scalar(select(func.count(UserSession.id)).where(UserSession.started_at.between(since, now))) or 0
    identified = db.scalar(select(func.count(UserSession.id)).where(
        UserSession.started_at.between(since, now), UserSession.identified.is_(True))) or 0
    questions = db.scalar(select(func.count(InteractionEvent.id)).where(
        InteractionEvent.event_type.in_(("QUESTION_ASKED", "USER_MESSAGE")),
        InteractionEvent.event_time.between(since, now),
    )) or 0
    ai_answers = db.scalar(select(func.count(AIRequest.id)).where(
        AIRequest.status.in_(("completed", "fallback", "success")),
        AIRequest.created_at.between(since, now),
    )) or 0
    surveys = db.scalar(select(func.count(SurveyResponse.id)).where(SurveyResponse.submitted_at.between(since, now))) or 0
    attempts = db.scalar(select(func.count(FaceAuthenticationLog.id)).where(FaceAuthenticationLog.occurred_at.between(since, now))) or 0
    successes = db.scalar(select(func.count(FaceAuthenticationLog.id)).where(
        FaceAuthenticationLog.result.in_(("MATCH", "SUCCESS", "RECOGNIZED")),
        FaceAuthenticationLog.occurred_at.between(since, now),
    )) or 0
    avg_processing_ms = db.scalar(select(func.avg(FaceAuthenticationLog.processing_time_ms)).where(
        FaceAuthenticationLog.processing_time_ms.is_not(None),
        FaceAuthenticationLog.occurred_at.between(since, now),
    ))
    satisfaction = average_satisfaction(db, since, now)
    answered = db.scalar(select(func.count(AIResponse.id)).where(AIResponse.created_at.between(since, now))) or 0
    grounded = db.scalar(select(func.count(AIResponse.id)).where(
        AIResponse.created_at.between(since, now), AIResponse.grounded.is_(True))) or 0
    return success_response({
        "total_sessions": sessions,
        "identified_users": identified,
        "questions": questions,
        "ai_answers": ai_answers,
        "surveys": surveys,
        "recognition_success_count": successes,
        "recognition_failure_count": max(attempts - successes, 0),
        "recognition_success_rate": round(successes / attempts * 100, 1) if attempts else 0,
        "avg_wait_seconds": round(float(avg_processing_ms) / 1000, 2) if avg_processing_ms is not None else 0,
        "camera_network_errors": db.scalar(select(func.count(InteractionEvent.id)).where(
            InteractionEvent.event_type.in_(("CAMERA_ERROR", "NETWORK_ERROR", "CAMERA_FAILED", "NETWORK_FAILED")),
            InteractionEvent.event_time.between(since, now),
        )) or 0,
        "avg_satisfaction": float(satisfaction) if satisfaction is not None else None,
        "grounded_answers": grounded,
        "grounded_rate": round(grounded / answered * 100, 1) if answered else 0,
        "daily": daily_sessions(db, since, now),
    })


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    documents = db.scalar(select(func.count(KnowledgeDocument.id)).where(
        KnowledgeDocument.deleted_at.is_(None), KnowledgeDocument.is_active.is_(True),
        KnowledgeDocument.processing_status == "processed")) or 0
    return success_response([{"module": "Database", "status": "Completed"},
        {"module": "Kiosk flow", "status": "Realtime"},
        {"module": "FaceID", "status": settings.face_provider,
         "warning": "Chế độ mock chỉ dành cho kiểm thử, không nhận diện danh tính thật."
            if settings.face_provider == "mock" else None},
        {"module": "AI", "status": settings.ai_provider,
         "warning": "Chế độ mock: câu trả lời được trích nguyên văn từ tài liệu, không dùng mô hình ngôn ngữ."
            if settings.ai_provider != "gemini" else None},
        {"module": "RAG", "status": f"{documents} tài liệu",
         "warning": None if documents else "Chưa có tài liệu tri thức đang hoạt động; AI sẽ từ chối trả lời thông tin chính thức."},
        {"module": "Voice", "status": settings.voice_provider,
         "warning": "Nhận dạng giọng nói chạy trên trình duyệt kiosk; trình duyệt không có Web Speech (như Firefox) sẽ chỉ nhập bằng bàn phím."
            if settings.voice_provider in {"mock", "browser"} else None},
        {"module": "Báo cáo ngày", "status": "Tự động" if settings.report_job_enabled else "Thủ công",
         "warning": (f"Lần chạy gần nhất lỗi: {job_state.last_error}" if job_state.last_error else
                     f"Chạy gần nhất: {job_state.last_run_at:%Y-%m-%d %H:%M} UTC" if job_state.last_run_at else
                     None if settings.report_job_enabled else
                     "Bật REPORT_JOB_ENABLED hoặc chạy scripts/aggregate_daily_reports.py theo lịch.")}])
