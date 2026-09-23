"""Read-only queries shared by staff dashboard and reporting."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.schema import UserSession


def report_window(days: int) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    since = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    return since, now


def daily_sessions(db: Session, since: datetime, until: datetime) -> list[dict]:
    timestamp = UserSession.started_at
    if db.get_bind().dialect.name == "postgresql":
        timestamp = func.timezone("UTC", timestamp)
    day = func.date(timestamp)
    rows = db.execute(select(
        day, func.count(UserSession.id),
        func.sum(case((UserSession.identified.is_(True), 1), else_=0)),
    ).where(UserSession.started_at.between(since, until)).group_by(day).order_by(day)).all()
    return [{"date": str(date), "sessions": count, "identified": identified}
            for date, count, identified in rows]
