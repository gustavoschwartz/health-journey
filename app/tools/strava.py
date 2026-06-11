import os
import httpx
from datetime import datetime, timezone, date as date_type
from sqlalchemy.orm import Session
from app.models import Workout, SyncLog, SyncStatusEnum, SyncSourceEnum
from app.services.strava_auth import get_valid_token, refresh_access_token
import uuid
import time

# Hardcoded for Phase 1
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

def fetch_from_strava_api(access_token: str, target_date: date_type) -> list[dict]:
    """Fetch activities from Strava API for a specific date.
    Uses a wider UTC window and filters by start_date_local to avoid
    timezone boundary errors.
    """
    from datetime import timedelta

    # Fetch a wider window: day before to day after in UTC
    start = datetime(
        target_date.year, target_date.month, target_date.day,
        0, 0, 0, tzinfo=timezone.utc
    ) - timedelta(days=1)

    end = datetime(
        target_date.year, target_date.month, target_date.day,
        23, 59, 59, tzinfo=timezone.utc
    ) + timedelta(days=1)

    response = httpx.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "after": int(start.timestamp()),
            "before": int(end.timestamp()),
            "per_page": 50
        }
    )
    response.raise_for_status()
    
    # Filter by local date — Strava's start_date_local reflects
    # the timezone where the activity actually happened
    activities = response.json()
    return [
        a for a in activities
        if a.get("start_date_local", "")[:10] == str(target_date)
    ]

def fetch_activity_calories(access_token: str, strava_id: str) -> int | None:
    """Fetch calories for one activity. Calories only exist on the activity
    detail endpoint — summary activities from the list endpoint omit them.
    Returns None on any failure: calories are enrichment, never worth
    failing a sync over."""
    try:
        response = httpx.get(
            f"https://www.strava.com/api/v3/activities/{strava_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        calories = response.json().get("calories")
        return round(calories) if calories else None
    except Exception:
        return None


def normalize_activity(activity: dict) -> dict:
    """Normalize a Strava summary activity to our workout schema."""
    return {
        "strava_id": str(activity["id"]),
        "type": activity.get("sport_type", activity.get("type", "unknown")),
        "duration_minutes": round(activity.get("moving_time", 0) / 60),
        "distance_km": round(activity.get("distance", 0) / 1000, 2) or None,
        "avg_heart_rate": activity.get("average_heartrate") or None,
        "calories": None,  # summary activities never carry calories — enriched at store time
    }


def serialize_workouts(workouts: list[Workout]) -> list[dict]:
    """Convert Workout rows to the tool contract shape."""
    return [
        {
            "strava_id": w.strava_id,
            "type": w.type,
            "duration_minutes": w.duration_minutes,
            "distance_km": w.distance_km,
            "avg_heart_rate": w.avg_heart_rate,
            "calories": w.calories,
            "feeling": w.feeling.value if w.feeling else None,
            "feeling_prompted": w.feeling_prompted,
        }
        for w in workouts
    ]


def is_date_covered(target_date: date_type, db: Session) -> bool:
    """A date is covered when sync_log records a successful Strava fetch for it.
    Coverage is per source — another source's success says nothing about Strava."""
    return db.query(SyncLog).filter_by(
        user_id=TEST_USER_ID,
        synced_date=target_date,
        source=SyncSourceEnum.strava,
        status=SyncStatusEnum.success,
    ).first() is not None


def record_coverage(target_date: date_type, db: Session) -> None:
    """Mark a date as successfully fetched so empty (rest) days are cached too.
    Does not commit — the caller owns the transaction."""
    db.add(SyncLog(
        user_id=TEST_USER_ID,
        synced_date=target_date,
        source=SyncSourceEnum.strava,
        status=SyncStatusEnum.success,
        is_backfill=False,
    ))


def get_strava_data(
    target_date: date_type,
    db: Session,
    today: date_type | None = None,
) -> dict:
    """
    Fetch Strava activities for a given date.
    Cache-aside: a past date is served from PostgreSQL when its workouts are
    stored or sync_log records a successful fetch (so rest days are cached too).
    Today is always fetched fresh — the day isn't over yet.
    Retries 3 times with exponential backoff on API failure.

    today: current date in the caller's timezone; defaults to server date.
    Callers with a device timezone should pass it so "today" matches the user.
    """
    if today is None:
        today = date_type.today()
    is_past_date = target_date < today

    if is_past_date:
        cached = db.query(Workout).filter_by(
            user_id=TEST_USER_ID,
            date=target_date
        ).all()

        covered = is_date_covered(target_date, db)
        if cached or covered:
            if not covered:
                # Workouts stored before coverage tracking existed
                record_coverage(target_date, db)
                db.commit()
            return {
                "date": str(target_date),
                "source": "cache",
                "workouts": serialize_workouts(cached),
            }

    # Not in cache — fetch from Strava API with retries
    last_error = None

    for attempt in range(3):
        try:
            # Resolved inside the loop so a token that expires mid-retry
            # is refreshed instead of reused
            access_token = get_valid_token(db)
            activities = fetch_from_strava_api(access_token, target_date)

            # Store each activity in PostgreSQL
            for activity in activities:
                normalized = normalize_activity(activity)

                # Skip if already exists (idempotent)
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
                    date=target_date,
                    **normalized,
                    feeling=None,
                    feeling_prompted=False,
                )
                db.add(workout)

            # Today stays uncovered so later activities are still fetched;
            # a past date reaching this point is never covered yet
            if is_past_date:
                record_coverage(target_date, db)

            db.commit()

            # Return freshly stored data
            stored = db.query(Workout).filter_by(
                user_id=TEST_USER_ID,
                date=target_date
            ).all()

            return {
                "date": str(target_date),
                "source": "api",
                "workouts": serialize_workouts(stored),
            }

        except ValueError:
            raise  # no stored token — OAuth must run first, retrying won't help

        except Exception as e:
            last_error = e

            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 401:
                # Token rejected despite a future expires_at (e.g. revoked or
                # rotated elsewhere) — force a refresh before the next attempt
                try:
                    refresh_access_token(db)
                except Exception:
                    pass  # if refresh also fails, the retry result surfaces it

            if attempt < 2:
                time.sleep(2 ** attempt)  # 1s, then 2s between attempts

    # All retries failed
    return {
        "date": str(target_date),
        "source": "error",
        "status": "error",
        "message": str(last_error),
        "workouts": []
    }


# --- Claude-facing tool layer ---
# The schema speaks JSON (string dates); the handler converts to the typed
# signature above and is where the orchestrator (Task 8) routes tool calls.

GET_STRAVA_DATA_TOOL = {
    "name": "get_strava_data",
    "description": (
        "Get the user's workouts for a single date from Strava. "
        "Returns a list of workouts — empty if the user didn't work out that day — "
        "with type, duration, distance, heart rate, calories, and how the workout "
        "felt if the user recorded a feeling. Call once per date of interest."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "The date to fetch, format YYYY-MM-DD, in the user's local timezone.",
            }
        },
        "required": ["date"],
    },
}


def handle_get_strava_data(
    tool_input: dict,
    db: Session,
    today: date_type | None = None,
) -> dict:
    """Adapter between Claude tool use and get_strava_data.
    Invalid input returns an error dict instead of raising, so the
    orchestrator can hand it back to Claude to self-correct."""
    raw_date = tool_input.get("date", "")
    try:
        target_date = date_type.fromisoformat(raw_date)
    except ValueError:
        return {
            "date": raw_date,
            "source": "error",
            "status": "error",
            "message": f"Invalid date {raw_date!r} — expected YYYY-MM-DD.",
            "workouts": [],
        }

    return get_strava_data(target_date, db, today=today)
