"""Recompute daily_report_metrics for the last N UTC days. Run from backend (e.g. from cron):

    python scripts/aggregate_daily_reports.py --days 7

Safe to repeat: each day's row is overwritten with numbers recomputed from the raw logs.
Use this instead of REPORT_JOB_ENABLED when several backend workers run.
"""
import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from app.services.report_service import aggregate_range  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate raw kiosk logs into daily_report_metrics.")
    parser.add_argument("--days", type=int, default=2, help="number of UTC days ending today (1–366)")
    args = parser.parse_args()
    if not 1 <= args.days <= 366:
        parser.error("--days must be between 1 and 366")
    end = datetime.now(UTC).date()
    with SessionLocal() as db:
        rows = aggregate_range(db, end - timedelta(days=args.days - 1), end)
    for row in rows:
        print(f"{row.report_date}: {row.total_sessions} sessions, {row.total_questions} questions, {row.total_surveys} surveys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
