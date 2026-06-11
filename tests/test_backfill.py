"""First run backfill: pagination and the skip guard."""
from datetime import date

import pytest

import app.services.backfill as backfill


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_pagination_collects_all_pages(monkeypatch):
    """A range holding more than one page (200) of activities is fully fetched."""
    pages = [
        [{"id": i} for i in range(backfill.PER_PAGE)],
        [{"id": backfill.PER_PAGE + i} for i in range(30)],
    ]
    requested = []

    def fake_get(url, headers, params):
        requested.append(params["page"])
        return FakeResponse(pages[len(requested) - 1])

    # patched on the module's httpx so monkeypatch restores the global after
    monkeypatch.setattr(backfill.httpx, "get", fake_get)

    activities = backfill.fetch_activities_date_range("tok", date(2026, 3, 1), date(2026, 6, 1))

    assert len(activities) == backfill.PER_PAGE + 30
    assert requested == [1, 2]


def test_single_short_page_stops_immediately(monkeypatch):
    requested = []

    def fake_get(url, headers, params):
        requested.append(params["page"])
        return FakeResponse([{"id": 1}])

    monkeypatch.setattr(backfill.httpx, "get", fake_get)

    activities = backfill.fetch_activities_date_range("tok", date(2026, 3, 1), date(2026, 6, 1))

    assert len(activities) == 1
    assert requested == [1]


@pytest.mark.live
def test_completed_backfill_skips_without_fetching(db, mocker):
    if not backfill.is_backfill_complete(db):
        pytest.skip("backfill has not completed in this database")

    fetch = mocker.patch.object(backfill, "fetch_activities_date_range")
    result = backfill.run_first_backfill(db)

    assert result["status"] == "skipped"
    assert fetch.call_count == 0
