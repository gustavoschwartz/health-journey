import uuid
from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.models import SyncLog, SyncStatusEnum
from app.tools.strava import get_strava_data

TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def get_missing_dates(last_synced_date: date, db: Session) -> list[date]:
    """Return list of dates that need syncing, from oldest to newest."""
    today = date.today()
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


def sync_date(target_date: date, db: Session) -> dict:
    """Sync a single date — fetch Strava data and update sync_log."""
    try:
        result = get_strava_data(target_date, db)

        status = SyncStatusEnum.success
        if result.get("source") == "error":
            status = SyncStatusEnum.failed

        log = SyncLog(
            user_id=TEST_USER_ID,
            synced_date=target_date,
            status=status,
            is_backfill=False,
        )
        db.add(log)
        db.commit()

        return {
            "date": str(target_date),
            "source": "strava",
            "status": status.value,
            "workouts": len(result.get("workouts", []))
        }

    except Exception as e:
        log = SyncLog(
            user_id=TEST_USER_ID,
            synced_date=target_date,
            status=SyncStatusEnum.failed,
            is_backfill=False,
        )
        db.add(log)
        db.commit()
        return {
            "date": str(target_date),
            "source": "strava",
            "status": "failed",
            "error": str(e)
        }


def run_sync(last_synced_date: date, db: Session) -> list[dict]:
    """
    Run sync for all missing dates since last_synced_date.
    Returns list of results per date.
    """
    missing_dates = get_missing_dates(last_synced_date, db)

    if not missing_dates:
        return [{"status": "up_to_date"}]

    results = []
    for target_date in missing_dates:
        result = sync_date(target_date, db)
        results.append(result)

    return results
