"""Daily reporting: idempotently aggregate raw logs into `daily_report_metrics`.

The aggregate is derived data and never replaces the raw facts; re-running a day overwrites
that day's row with freshly computed numbers. Days are UTC calendar days, like the dashboard.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.schema import (
    AIRequest, DailyReportMetric, InteractionEvent, SurveyAnswer, SurveyQuestion, SurveyResponse, UserSession,
)

logger = logging.getLogger(__name__)
QUESTION_EVENTS = ("QUESTION_ASKED", "USER_MESSAGE")
ANSWERED_STATUSES = ("completed", "fallback", "success")


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _between(column, start: datetime, end: datetime):
    return (column >= start) & (column < end)


def average_satisfaction(db: Session, start: datetime, end: datetime) -> Decimal | None:
    """Mean of 1–5 rating answers submitted in the window."""
    value = db.scalar(select(func.avg(SurveyAnswer.answer_number))
                      .join(SurveyQuestion, SurveyAnswer.question_id == SurveyQuestion.id)
                      .join(SurveyResponse, SurveyAnswer.response_id == SurveyResponse.id)
                      .where(SurveyQuestion.question_type == "rating", SurveyAnswer.answer_number.between(1, 5),
                             _between(SurveyResponse.submitted_at, start, end)))
    return Decimal(str(round(float(value), 2))) if value is not None else None


def aggregate_day(db: Session, day: date) -> DailyReportMetric:
    start, end = day_bounds(day)
    count = lambda query: db.scalar(query) or 0  # noqa: E731
    sessions = count(select(func.count(UserSession.id)).where(_between(UserSession.started_at, start, end)))
    identified = count(select(func.count(UserSession.id)).where(
        _between(UserSession.started_at, start, end), UserSession.identified.is_(True)))
    questions = count(select(func.count(InteractionEvent.id)).where(
        InteractionEvent.event_type.in_(QUESTION_EVENTS), _between(InteractionEvent.event_time, start, end)))
    answers = count(select(func.count(AIRequest.id)).where(
        AIRequest.status.in_(ANSWERED_STATUSES), _between(AIRequest.created_at, start, end)))
    surveys = count(select(func.count(SurveyResponse.id)).where(_between(SurveyResponse.submitted_at, start, end)))
    latency = db.scalar(select(func.avg(AIRequest.latency_ms)).where(
        AIRequest.latency_ms.is_not(None), _between(AIRequest.created_at, start, end)))

    row = db.scalar(select(DailyReportMetric).where(DailyReportMetric.report_date == day))
    if row is None:
        row = DailyReportMetric(report_date=day)
        db.add(row)
    row.total_sessions, row.total_identified_users = sessions, identified
    row.total_questions, row.total_ai_answers, row.total_surveys = questions, answers, surveys
    row.avg_satisfaction_score = average_satisfaction(db, start, end)
    row.avg_ai_response_time_ms = Decimal(str(round(float(latency), 2))) if latency is not None else None
    db.flush()
    return row


def aggregate_range(db: Session, start: date, end: date) -> list[DailyReportMetric]:
    rows = []
    day = start
    while day <= end:
        rows.append(aggregate_day(db, day)); day += timedelta(days=1)
    db.commit()
    return rows


# --- background job -------------------------------------------------------------------------------

@dataclass
class JobState:
    last_run_at: datetime | None = None
    last_error: str | None = None


job_state = JobState()


def run_once(session_factory, days: int = 2) -> None:
    """Refresh today and the previous `days - 1` days (late events still land in yesterday)."""
    today = datetime.now(UTC).date()
    with session_factory() as db:
        aggregate_range(db, today - timedelta(days=days - 1), today)


async def report_scheduler(session_factory) -> None:
    interval = settings.report_job_interval_minutes * 60
    while True:
        try:
            await asyncio.to_thread(run_once, session_factory)
            job_state.last_run_at, job_state.last_error = datetime.now(UTC), None
        except Exception as exc:  # the job must survive a database outage
            job_state.last_error = type(exc).__name__
            logger.warning("Daily report aggregation failed: %s", type(exc).__name__)
        await asyncio.sleep(interval)
