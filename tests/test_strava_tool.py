"""Strava tool: normalization, retry behavior, the Claude-facing layer,
and (live) the coverage-based cache."""
import json
from datetime import date, timedelta

import httpx
import pytest

import app.tools.strava as tool
from app.config import TEST_USER_ID
from app.models import SyncLog, SyncSourceEnum, SyncStatusEnum, Workout


def test_normalize_activity_shape():
    normalized = tool.normalize_activity(
        {"id": 123, "sport_type": "Ride", "moving_time": 3720, "distance": 25400}
    )
    assert normalized == {
        "strava_id": "123",
        "type": "Ride",
        "duration_minutes": 62,
        "distance_km": 25.4,
        "avg_heart_rate": None,
        "calories": None,  # summary activities never carry calories
    }


def test_tool_schema_is_valid_anthropic_definition():
    schema = tool.GET_STRAVA_DATA_TOOL
    assert set(schema) == {"name", "description", "input_schema"}
    assert schema["name"] == "get_strava_data"
    assert schema["input_schema"]["required"] == ["date"]
    json.dumps(schema)  # must be serializable for the API call


@pytest.mark.parametrize("bad_input", [{"date": "June 9th"}, {"date": "2026-13-45"}, {}])
def test_handler_rejects_bad_date_without_raising(bad_input):
    result = tool.handle_get_strava_data(bad_input, db=None)
    assert result["status"] == "error"
    assert result["workouts"] == []
    assert "YYYY-MM-DD" in result["message"]


def test_retry_makes_three_attempts_then_error(mocker, fake_db):
    mocker.patch.object(tool, "get_valid_token", return_value="tok")
    mocker.patch.object(tool.time, "sleep")
    fetch = mocker.patch.object(
        tool, "fetch_from_strava_api", side_effect=Exception("API down")
    )

    result = tool.get_strava_data(date.today() - timedelta(days=400), fake_db)

    assert fetch.call_count == 3
    assert result["status"] == "error"
    assert result["workouts"] == []


def test_401_forces_token_refresh_then_succeeds(mocker, fake_db):
    response = httpx.Response(401, request=httpx.Request("GET", "https://x"))
    unauthorized = httpx.HTTPStatusError("401", request=response.request, response=response)

    mocker.patch.object(tool, "get_valid_token", return_value="tok")
    mocker.patch.object(tool.time, "sleep")
    refresh = mocker.patch.object(tool, "refresh_access_token")
    fetch = mocker.patch.object(
        tool, "fetch_from_strava_api", side_effect=[unauthorized, []]
    )

    result = tool.get_strava_data(date.today() - timedelta(days=400), fake_db)

    assert refresh.call_count == 1
    assert fetch.call_count == 2
    assert result["source"] == "api"


def test_missing_token_fails_fast(mocker, fake_db):
    mocker.patch.object(
        tool, "get_valid_token", side_effect=ValueError("No Strava token found")
    )
    fetch = mocker.patch.object(tool, "fetch_from_strava_api")

    with pytest.raises(ValueError):
        tool.get_strava_data(date.today() - timedelta(days=400), fake_db)
    assert fetch.call_count == 0


# --- live: coverage-based cache against the real database (read-only) ---

def find_covered_rest_day(db):
    """Most recent date with a success coverage row and no workouts."""
    rows = db.query(SyncLog.synced_date).filter(
        SyncLog.user_id == TEST_USER_ID,
        SyncLog.source == SyncSourceEnum.strava,
        SyncLog.status == SyncStatusEnum.success,
        SyncLog.synced_date.isnot(None),
    ).all()
    for (d,) in sorted(rows, reverse=True):
        if not db.query(Workout).filter_by(user_id=TEST_USER_ID, date=d).first():
            return d
    return None


@pytest.mark.live
def test_covered_rest_day_served_from_cache(db, mocker):
    rest_day = find_covered_rest_day(db)
    if rest_day is None:
        pytest.skip("no covered rest day in the database yet")

    fetch = mocker.patch.object(tool, "fetch_from_strava_api")
    result = tool.get_strava_data(rest_day, db)

    assert result["source"] == "cache"
    assert result["workouts"] == []
    assert fetch.call_count == 0


@pytest.mark.live
def test_coverage_is_source_scoped(db):
    rest_day = find_covered_rest_day(db)
    if rest_day is None:
        pytest.skip("no covered rest day in the database yet")

    assert tool.is_date_covered(rest_day, db)
    other_source = db.query(SyncLog).filter_by(
        user_id=TEST_USER_ID,
        synced_date=rest_day,
        source=SyncSourceEnum.apple_health,
    ).first()
    assert other_source is None


@pytest.mark.live
def test_cached_workout_day_includes_calories(db, mocker):
    workout = db.query(Workout).filter(
        Workout.user_id == TEST_USER_ID,
        Workout.calories.isnot(None),
        Workout.date < date.today(),
    ).first()
    if workout is None:
        pytest.skip("no workout with calories in the database yet")

    fetch = mocker.patch.object(tool, "fetch_from_strava_api")
    result = tool.get_strava_data(workout.date, db)

    assert result["source"] == "cache"
    assert any(w["calories"] == workout.calories for w in result["workouts"])
    assert fetch.call_count == 0


@pytest.mark.live
def test_handler_delegates_valid_date(db):
    rest_day = find_covered_rest_day(db)
    if rest_day is None:
        pytest.skip("no covered rest day in the database yet")

    result = tool.handle_get_strava_data({"date": str(rest_day)}, db)
    assert result["source"] == "cache"
