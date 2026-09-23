"""Reporting endpoints for analytics and metrics.

Provides read-only access to aggregated system metrics.
Mock endpoints remain available for frontend compatibility.
"""
from datetime import date, datetime, timedelta, UTC

from fastapi import APIRouter, Depends, Query
from app.api.deps import require_admin_credentials
from app.core.errors import AppError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import success_response
from app.models.schema import (
    AIRequest,
    DailyReportMetric,
    FaceAuthenticationLog,
    InteractionEvent,
    UserSession,
)
from app.services.admin_dashboard_service import report_window

router = APIRouter(dependencies=[Depends(require_admin_credentials)])


@router.get("/overview/mock")
async def overview() -> dict:
    return success_response({
        "total_sessions": 1284, "total_identified_users": 947,
        "total_questions": 3260, "total_ai_answers": 3198,
        "total_surveys": 486, "avg_satisfaction_score": 4.6,
        "avg_ai_response_time_ms": 842.5,
    })


@router.get("/feature-status")
async def feature_status() -> dict:
    modules = [
        ("Database", "Completed"), ("Backend Foundation", "In Progress"),
        ("Frontend Foundation", "In Progress"), ("FaceID", "Mock only"),
        ("AI Chat", "Mock only"), ("Knowledge Upload", "Placeholder"),
        ("RAG", "Not implemented"), ("Dashboard", "Basic placeholder"),
    ]
    return success_response(
        [{"module": module, "status": status} for module, status in modules]
    )


@router.get("/overview")
def report_overview(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> dict:
    """Aggregated overview metrics for the last N days."""
    since, now = report_window(days)

    total_sessions = db.scalar(
        select(func.count(UserSession.id)).where(UserSession.started_at.between(since, now))
    ) or 0
    identified = db.scalar(
        select(func.count(UserSession.id)).where(
            UserSession.started_at.between(since, now), UserSession.identified.is_(True)
        )
    ) or 0
    questions = db.scalar(
        select(func.count(InteractionEvent.id)).where(
            InteractionEvent.event_time.between(since, now),
            InteractionEvent.event_type.in_(("QUESTION_ASKED", "USER_MESSAGE")),
        )
    ) or 0
    ai_answers = db.scalar(
        select(func.count(AIRequest.id)).where(
            AIRequest.created_at.between(since, now),
            AIRequest.status.in_(("completed", "fallback", "success")),
        )
    ) or 0
    auth_attempts = db.scalar(
        select(func.count(FaceAuthenticationLog.id)).where(
            FaceAuthenticationLog.occurred_at.between(since, now)
        )
    ) or 0
    auth_success = db.scalar(
        select(func.count(FaceAuthenticationLog.id)).where(
            FaceAuthenticationLog.occurred_at.between(since, now),
            FaceAuthenticationLog.result.in_(("MATCH", "SUCCESS", "RECOGNIZED")),
        )
    ) or 0
    avg_processing = db.scalar(
        select(func.avg(FaceAuthenticationLog.processing_time_ms)).where(
            FaceAuthenticationLog.occurred_at.between(since, now),
            FaceAuthenticationLog.processing_time_ms.is_not(None),
        )
    )
    camera_network_errors = db.scalar(
        select(func.count(InteractionEvent.id)).where(
            InteractionEvent.event_time.between(since, now),
            InteractionEvent.event_type.in_(
                ("CAMERA_ERROR", "NETWORK_ERROR", "CAMERA_FAILED", "NETWORK_FAILED")
            ),
        )
    ) or 0

    return success_response({
        "period_days": days,
        "total_sessions": total_sessions,
        "identified_users": identified,
        "total_questions": questions,
        "total_ai_answers": ai_answers,
        "recognition_success": auth_success,
        "recognition_failure": max(auth_attempts - auth_success, 0),
        "recognition_success_rate": (
            round(auth_success / auth_attempts * 100, 1) if auth_attempts else 0
        ),
        "avg_wait_seconds": (
            round(float(avg_processing) / 1000, 2)
            if avg_processing is not None else 0
        ),
        "camera_network_errors": camera_network_errors,
    })


@router.get("/daily")
def report_daily(
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Daily aggregated metrics from the daily_report_metrics table."""
    if not end_date:
        end_date = datetime.now(UTC).date()
    if not start_date:
        start_date = end_date - timedelta(days=6)
    if start_date > end_date or (end_date - start_date).days >= 90:
        raise AppError(422, "INVALID_REPORT_PERIOD", "Khoảng ngày không hợp lệ hoặc vượt quá 90 ngày.")

    rows = db.scalars(
        select(DailyReportMetric).where(
            DailyReportMetric.report_date >= start_date,
            DailyReportMetric.report_date <= end_date,
        ).order_by(DailyReportMetric.report_date)
    ).all()

    return success_response({
        "metrics": [
            {
                "date": m.report_date.isoformat(),
                "total_sessions": m.total_sessions,
                "identified_users": m.total_identified_users,
                "total_questions": m.total_questions,
                "total_ai_answers": m.total_ai_answers,
                "total_surveys": m.total_surveys,
                "avg_satisfaction_score": (
                    float(m.avg_satisfaction_score) if m.avg_satisfaction_score else None
                ),
                "avg_ai_response_time_ms": (
                    float(m.avg_ai_response_time_ms) if m.avg_ai_response_time_ms is not None else None
                ),
            }
            for m in rows
        ],
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
    })


@router.get("/sessions")
def report_sessions(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> dict:
    """Session analytics: breakdown by exit reason, device, and average duration."""
    since, now = report_window(days)

    # By exit reason
    exit_rows = db.execute(
        select(UserSession.exit_reason, func.count(UserSession.id)).where(
            UserSession.started_at.between(since, now)
        ).group_by(UserSession.exit_reason)
    )
    by_exit = {row[0] or "unknown": row[1] for row in exit_rows}

    # By device
    device_rows = db.execute(
        select(UserSession.device_id, func.count(UserSession.id)).where(
            UserSession.started_at.between(since, now)
        ).group_by(UserSession.device_id)
    )
    by_device = {str(row[0]) if row[0] else "unknown": row[1] for row in device_rows}

    # Average duration
    avg_duration = db.scalar(
        select(func.avg(UserSession.duration_seconds)).where(
            UserSession.started_at.between(since, now),
            UserSession.duration_seconds.is_not(None),
        )
    )

    return success_response({
        "period_days": days,
        "by_exit_reason": by_exit,
        "by_device": by_device,
        "avg_duration_seconds": round(float(avg_duration), 1) if avg_duration else 0,
    })
