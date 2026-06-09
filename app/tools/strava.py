import os
import httpx
from datetime import datetime, timezone, date as date_type
from sqlalchemy.orm import Session
from app.models import Workout
from app.services.strava_auth import get_valid_token
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

def normalize_activity(activity: dict, target_date: date_type) -> dict:
    """Normalize a Strava activity to our workout schema."""
    return {
        "strava_id": str(activity["id"]),
        "type": activity.get("sport_type", activity.get("type", "unknown")),
        "duration_minutes": round(activity.get("moving_time", 0) / 60),
        "distance_km": round(activity.get("distance", 0) / 1000, 2) or None,
        "avg_heart_rate": activity.get("average_heartrate") or None,
        "calories": activity.get("calories") or None,
    }


def get_strava_data(target_date: date_type, db: Session) -> dict:
    """
    Fetch Strava activities for a given date.
    Cache-aside: check PostgreSQL first, fetch from API if not found.
    Retries 3 times with exponential backoff on API failure.
    """
    # Check cache first
    cached = db.query(Workout).filter_by(
        user_id=TEST_USER_ID,
        date=target_date
    ).all()

    if cached:
        return {
            "date": str(target_date),
            "source": "cache",
            "workouts": [
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
                for w in cached
            ]
        }

    # Not in cache — fetch from Strava API with retries
    access_token = get_valid_token(db)
    last_error = None

    for attempt in range(3):
        try:
            activities = fetch_from_strava_api(access_token, target_date)

            # Store each activity in PostgreSQL
            for activity in activities:
                normalized = normalize_activity(activity, target_date)

                # Skip if already exists (idempotent)
                existing = db.query(Workout).filter_by(
                    strava_id=normalized["strava_id"]
                ).first()
                if existing:
                    continue

                workout = Workout(
                    user_id=TEST_USER_ID,
                    date=target_date,
                    **normalized,
                    feeling=None,
                    feeling_prompted=False,
                )
                db.add(workout)

            db.commit()

            # Return freshly stored data
            stored = db.query(Workout).filter_by(
                user_id=TEST_USER_ID,
                date=target_date
            ).all()

            return {
                "date": str(target_date),
                "source": "api",
                "workouts": [
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
                    for w in stored
                ]
            }

        except Exception as e:
            last_error = e
            wait = 2 ** attempt  # 1s, 2s, 4s
            time.sleep(wait)

    # All retries failed
    return {
        "date": str(target_date),
        "source": "error",
        "status": "error",
        "message": str(last_error),
        "workouts": []
    }
