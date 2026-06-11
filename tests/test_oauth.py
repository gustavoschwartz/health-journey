"""Strava OAuth: state lifecycle (CSRF), redirect URI configuration, token
expiry margin, and (live) the deployed service's behavior."""
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

import app.main as main
import app.services.strava_auth as auth

PRODUCTION_BASE = "https://health-journey-production.up.railway.app"


# --- state lifecycle ---

def test_state_is_single_use():
    state = auth.generate_state()
    assert auth.consume_state(state) is True
    assert auth.consume_state(state) is False  # replay rejected


def test_expired_state_rejected():
    state = auth.generate_state()
    auth._pending_states[state] = time.time() - 1
    assert auth.consume_state(state) is False


def test_unknown_state_rejected():
    assert auth.consume_state("never-issued") is False


# --- auth URL and callback routes ---

def test_auth_url_contains_required_params(client):
    url = client.get("/strava/auth-url").json()["url"]
    params = parse_qs(urlparse(url).query)

    assert "strava.com/oauth/authorize" in url
    assert "client_id" in params
    assert params["scope"] == ["activity:read_all"]
    assert len(params["state"][0]) >= 40  # 32 urlsafe bytes


def test_redirect_uri_defaults_to_localhost(client, monkeypatch):
    monkeypatch.delenv("STRAVA_REDIRECT_URI", raising=False)
    url = client.get("/strava/auth-url").json()["url"]
    params = parse_qs(urlparse(url).query)
    assert params["redirect_uri"] == ["http://localhost:8000/strava/callback"]


def test_redirect_uri_honors_env(client, monkeypatch):
    monkeypatch.setenv("STRAVA_REDIRECT_URI", "https://example.app/strava/callback")
    url = client.get("/strava/auth-url").json()["url"]
    params = parse_qs(urlparse(url).query)
    assert params["redirect_uri"] == ["https://example.app/strava/callback"]


def test_callback_rejects_missing_and_forged_state(client, mocker):
    exchange = mocker.patch.object(main, "exchange_code_for_tokens")

    assert client.get("/strava/callback?code=x").status_code == 403
    assert client.get("/strava/callback?code=x&state=forged").status_code == 403
    assert exchange.call_count == 0  # rejected before any Strava call


def test_callback_accepts_issued_state_once(client, mocker):
    mocker.patch.object(
        main, "exchange_code_for_tokens",
        return_value=SimpleNamespace(expires_at="2026-01-01"),
    )
    url = client.get("/strava/auth-url").json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]

    assert client.get(f"/strava/callback?code=x&state={state}").status_code == 200
    assert client.get(f"/strava/callback?code=x&state={state}").status_code == 403  # replay


# --- token expiry margin ---

def make_token(expires_in):
    return SimpleNamespace(
        access_token="tok",
        refresh_token="ref",
        expires_at=datetime.now(tz=timezone.utc) + expires_in,
    )


def test_token_in_expiry_margin_is_refreshed(mocker, fake_db):
    token = make_token(timedelta(minutes=2))
    fake_db.query.return_value.filter_by.return_value.first.return_value = token
    refresh = mocker.patch.object(auth, "refresh_access_token", return_value=token)

    auth.get_valid_token(fake_db)
    assert refresh.call_count == 1


def test_fresh_token_is_not_refreshed(mocker, fake_db):
    token = make_token(timedelta(hours=5))
    fake_db.query.return_value.filter_by.return_value.first.return_value = token
    refresh = mocker.patch.object(auth, "refresh_access_token")

    assert auth.get_valid_token(fake_db) == "tok"
    assert refresh.call_count == 0


# --- live: deployed service ---

@pytest.mark.live
def test_production_auth_url_uses_railway_redirect_and_state():
    url = httpx.get(f"{PRODUCTION_BASE}/strava/auth-url", timeout=10).json()["url"]
    params = parse_qs(urlparse(url).query)
    assert params["redirect_uri"] == [f"{PRODUCTION_BASE}/strava/callback"]
    assert len(params["state"][0]) >= 40


@pytest.mark.live
def test_production_rejects_forged_state():
    response = httpx.get(
        f"{PRODUCTION_BASE}/strava/callback?code=x&state=forged", timeout=10
    )
    assert response.status_code == 403


@pytest.mark.live
def test_production_database_healthy():
    body = httpx.get(f"{PRODUCTION_BASE}/health/db", timeout=10).json()
    assert body == {"status": "ok", "database": "connected"}
