"""Nightly sync: timezone-aware day boundaries and the streaming event protocol."""
import json
from datetime import date, timedelta

import app.services.sync as sync


def success_result(target_date, today, db):
    return {"date": str(target_date), "source": "strava", "status": "success", "workouts": 0}


def test_local_today_respects_timezone():
    """Day boundaries belong to the device's timezone, not the server's."""
    ahead = sync.local_today("Pacific/Kiritimati")  # UTC+14
    behind = sync.local_today("Etc/GMT+12")         # UTC-12
    assert ahead != behind


def test_missing_dates_run_through_yesterday():
    today = date(2026, 6, 11)
    missing = sync.get_missing_dates(date(2026, 6, 7), today)
    assert missing == [date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 10)]


def test_missing_dates_empty_when_up_to_date():
    today = date(2026, 6, 11)
    assert sync.get_missing_dates(date(2026, 6, 10), today) == []


def test_run_sync_yields_typed_progress_then_done(monkeypatch):
    monkeypatch.setattr(sync, "sync_date", success_result)
    events = list(sync.run_sync(date.today() - timedelta(days=3), "America/Los_Angeles", None))

    assert [e["type"] for e in events] == ["progress", "progress", "done"]
    for e in events[:-1]:
        assert {"date", "source", "status"} <= e.keys()
    assert events[-1]["synced_through"] == str(date.today() - timedelta(days=1))


def test_run_sync_up_to_date_yields_done_only(monkeypatch):
    monkeypatch.setattr(sync, "sync_date", success_result)
    last_synced = date.today() - timedelta(days=1)
    events = list(sync.run_sync(last_synced, "America/Los_Angeles", None))

    assert [e["type"] for e in events] == ["done"]
    assert events[0]["synced_through"] == str(last_synced)


def test_synced_through_stops_before_failed_day(monkeypatch):
    """A failed day freezes synced_through so the device retries it next sync,
    even though later days still sync."""
    failed_day = date.today() - timedelta(days=2)

    def flaky(target_date, today, db):
        status = "failed" if target_date == failed_day else "success"
        return {"date": str(target_date), "source": "strava", "status": status}

    monkeypatch.setattr(sync, "sync_date", flaky)
    events = list(sync.run_sync(date.today() - timedelta(days=4), "America/Los_Angeles", None))

    assert len([e for e in events if e["type"] == "progress"]) == 3  # all days attempted
    assert events[-1]["synced_through"] == str(failed_day - timedelta(days=1))


def test_sync_endpoint_streams_contract_events(monkeypatch, client):
    monkeypatch.setattr(sync, "sync_date", success_result)
    last_synced = (date.today() - timedelta(days=2)).isoformat()

    with client.stream("POST", "/sync", json={
        "timezone": "America/Los_Angeles",
        "last_synced_date": last_synced,
    }) as response:
        events = [
            json.loads(line[len("data: "):])
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]

    assert all("type" in e for e in events)
    assert [e["type"] for e in events] == ["progress", "done"]
    assert "synced_through" in events[-1]
