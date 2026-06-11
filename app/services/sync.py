import uuid
from datetime import date, datetime, timedelta
from typing import Iterator
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from app.models import SyncLog, SyncStatusEnum, SyncSourceEnum
from app.tools.strava import get_strava_data

TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def local_today(timezone_name: str) -> date:
    """Today in the device's timezone — the device defines day boundaries,
    not the server (which runs in UTC on Railway)."""
    return datetime.now(ZoneInfo(timezone_name)).date()


def get_missing_dates(last_synced_date: date, today: date) -> list[date]:
    """Return list of dates that need syncing, from oldest to newest."""
    yesterday = today - timedelta(days=1)

    # If already synced yesterday, nothing to do
    if last_synced_date >= yesterday:
        return []

    # Collect all dates from day after last sync up to yesterday
    missing = []
    current = last_synced_date + timedelta(days=1)
    while current <= yesterday:
        missing.append(current)
        current += timedelta(days=1)

    return missing


def log_failure(target_date: date, db: Session) -> None:
    db.add(SyncLog(
        user_id=TEST_USER_ID,
        synced_date=target_date,
        source=SyncSourceEnum.strava,
        status=SyncStatusEnum.failed,
        is_backfill=False,
    ))
    db.commit()


def sync_date(target_date: date, today: date, db: Session) -> dict:
    """Sync a single date — get_strava_data records successful coverage
    in sync_log itself, so only failures are logged here."""
    try:
        result = get_strava_data(target_date, db, today=today)

        if result.get("source") == "error":
            log_failure(target_date, db)
            return {
                "date": str(target_date),
                "source": "strava",
                "status": "failed",
                "error": result.get("message")
            }

        return {
            "date": str(target_date),
            "source": "strava",
            "status": "success",
            "workouts": len(result.get("workouts", []))
        }

    except Exception as e:
        log_failure(target_date, db)
        return {
            "date": str(target_date),
            "source": "strava",
            "status": "failed",
            "error": str(e)
        }


def run_sync(last_synced_date: date, timezone_name: str, db: Session) -> Iterator[dict]:
    """
    Sync all missing dates since last_synced_date, yielding one progress
    event per date as it completes, then a done event.

    synced_through only advances while every date so far has succeeded —
    a gap left by a failed date must be retried on the next sync, so the
    device must not record dates beyond it as synced.
    """
    today = local_today(timezone_name)
    missing_dates = get_missing_dates(last_synced_date, today)

    synced_through = last_synced_date
    contiguous = True

    for target_date in missing_dates:
        result = sync_date(target_date, today, db)
        yield {"type": "progress", **result}

        if contiguous and result["status"] == "success":
            synced_through = target_date
        else:
            contiguous = False

    yield {"type": "done", "synced_through": str(synced_through)}
