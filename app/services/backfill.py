import os
import httpx
import uuid
from datetime import datetime, timezone, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from dotenv import load_dotenv
from app.models import Workout, SyncLog, SyncStatusEnum, SyncSourceEnum
from app.services.strava_auth import get_valid_token

load_dotenv()

TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
BACKFILL_DAYS = 90


def is_backfill_complete(db: Session) -> bool:
    log = db.query(SyncLog).filter_by(
        user_id=TEST_USER_ID,
        source=SyncSourceEnum.strava,
        is_backfill=True,
        status=SyncStatusEnum.success,
    ).first()
    return log is not None

def fetch_activities_date_range(
    access_token: str,
    start_date: date,
    end_date: date
) -> list[dict]:
    """Fetch all activities between two dates in a single Strava API call."""
    start = datetime(
        start_date.year, start_date.month, start_date.day,
        0, 0, 0, tzinfo=timezone.utc
    )
    end = datetime(
        end_date.year, end_date.month, end_date.day,
        23, 59, 59, tzinfo=timezone.utc
    )

    response = httpx.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "after": int(start.timestamp()),
            "before": int(end.timestamp()),
            "per_page": 200  # max allowed by Strava
        }
    )
    response.raise_for_status()
    return response.json()


def run_first_backfill(db: Session) -> dict:
    """
    Fetch last 90 days of Strava activities in one API call.
    Stores each activity in PostgreSQL.
    Marks backfill complete in sync_log.
    Skips if already completed.
    """
    if is_backfill_complete(db):
        return {"status": "skipped", "reason": "backfill already completed"}

    end_date = date.today()
    start_date = end_date - timedelta(days=BACKFILL_DAYS)

    access_token = get_valid_token(db)
    activities = fetch_activities_date_range(access_token, start_date, end_date)

    stored_count = 0
    for activity in activities:
        # Use start_date_local for correct local date
        local_date_str = activity.get("start_date_local", "")[:10]
        if not local_date_str:
            continue

        activity_date = date.fromisoformat(local_date_str)

        # Skip if already exists
        existing = db.query(Workout).filter_by(
            strava_id=str(activity["id"])
        ).first()
        if existing:
            continue

        workout = Workout(
            user_id=TEST_USER_ID,
            date=activity_date,
            strava_id=str(activity["id"]),
            type=activity.get("sport_type", activity.get("type", "unknown")),
            duration_minutes=round(activity.get("moving_time", 0) / 60),
            distance_km=round(activity.get("distance", 0) / 1000, 2) or None,
            avg_heart_rate=activity.get("average_heartrate") or None,
            calories=activity.get("calories") or None,
            feeling=None,
            feeling_prompted=False,
        )
        db.add(workout)
        stored_count += 1

    # Record per-date coverage so rest days inside the range are cached too.
    # Today stays uncovered — the day isn't over yet, so the Strava tool
    # must keep fetching it fresh.
    yesterday = date.today() - timedelta(days=1)
    current = start_date
    while current <= yesterday:
        db.add(SyncLog(
            user_id=TEST_USER_ID,
            synced_date=current,
            source=SyncSourceEnum.strava,
            is_backfill=True,
            status=SyncStatusEnum.success,
        ))
        current += timedelta(days=1)
    db.commit()

    return {
        "status": "success",
        "activities_stored": stored_count,
        "date_range": f"{start_date} to {end_date}"
    }
