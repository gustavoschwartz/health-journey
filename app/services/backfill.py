import os
import httpx
import uuid
from datetime import datetime, timezone, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from dotenv import load_dotenv
from app.models import Workout, SyncLog, SyncStatusEnum, SyncSourceEnum
from app.services.strava_auth import get_valid_token
from app.tools.strava import normalize_activity, fetch_activity_calories

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

PER_PAGE = 200  # max allowed by Strava


def fetch_activities_date_range(
    access_token: str,
    start_date: date,
    end_date: date
) -> list[dict]:
    """Fetch all activities between two dates with one date-range query,
    paginating if the range holds more than one page of activities."""
    start = datetime(
        start_date.year, start_date.month, start_date.day,
        0, 0, 0, tzinfo=timezone.utc
    )
    end = datetime(
        end_date.year, end_date.month, end_date.day,
        23, 59, 59, tzinfo=timezone.utc
    )

    activities = []
    page = 1
    while True:
        response = httpx.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "after": int(start.timestamp()),
                "before": int(end.timestamp()),
                "per_page": PER_PAGE,
                "page": page
            }
        )
        response.raise_for_status()
        batch = response.json()
        activities.extend(batch)

        if len(batch) < PER_PAGE:
            return activities
        page += 1


def run_first_backfill(db: Session, today: date | None = None) -> dict:
    """
    Fetch the last 90 days of Strava activities with one date-range query.
    Stores each activity in PostgreSQL and writes per-date coverage to sync_log.
    Skips if already completed; on failure, logs a failed sync_log row and
    leaves nothing stored, so the next app open retries from scratch.

    today: current date in the device's timezone; defaults to server date.
    """
    if today is None:
        today = date.today()

    if is_backfill_complete(db):
        return {"status": "skipped", "reason": "backfill already completed"}

    end_date = today
    start_date = end_date - timedelta(days=BACKFILL_DAYS)

    try:
        access_token = get_valid_token(db)
        activities = fetch_activities_date_range(access_token, start_date, end_date)

        stored_count = 0
        for activity in activities:
            # Use start_date_local for correct local date
            local_date_str = activity.get("start_date_local", "")[:10]
            if not local_date_str:
                continue

            activity_date = date.fromisoformat(local_date_str)
            normalized = normalize_activity(activity)

            # Skip if already exists
            existing = db.query(Workout).filter_by(
                strava_id=normalized["strava_id"]
            ).first()
            if existing:
                continue

            normalized["calories"] = fetch_activity_calories(
                access_token, normalized["strava_id"]
            )
            workout = Workout(
                user_id=TEST_USER_ID,
                date=activity_date,
                **normalized,
                feeling=None,
                feeling_prompted=False,
            )
            db.add(workout)
            stored_count += 1

        # Record per-date coverage so rest days inside the range are cached too.
        # Today stays uncovered — the day isn't over yet, so the Strava tool
        # must keep fetching it fresh.
        yesterday = today - timedelta(days=1)
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

    except Exception as e:
        db.rollback()  # discard any partial workout/coverage writes
        # synced_date is None: the whole range failed, not one date.
        # is_backfill_complete only matches success, so this never blocks a retry.
        db.add(SyncLog(
            user_id=TEST_USER_ID,
            synced_date=None,
            source=SyncSourceEnum.strava,
            is_backfill=True,
            status=SyncStatusEnum.failed,
        ))
        db.commit()
        return {"status": "failed", "error": str(e)}
