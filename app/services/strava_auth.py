import os
import httpx
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models import StravaToken
import uuid

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
STRAVA_REDIRECT_URI = "http://localhost:8000/strava/callback"

# Hardcoded for Phase 1 — no auth yet
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def get_auth_url() -> str:
    """Generate the Strava OAuth authorization URL."""
    return (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={STRAVA_CLIENT_ID}"
        f"&redirect_uri={STRAVA_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=activity:read_all"
    )


def exchange_code_for_tokens(code: str, db: Session) -> StravaToken:
    """Exchange authorization code for access + refresh tokens."""
    response = httpx.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        }
    )
    response.raise_for_status()
    data = response.json()

    expires_at = datetime.fromtimestamp(data["expires_at"], tz=timezone.utc)

    # Upsert — update if exists, insert if not
    token = db.query(StravaToken).filter_by(user_id=TEST_USER_ID).first()
    if token:
        token.access_token = data["access_token"]
        token.refresh_token = data["refresh_token"]
        token.expires_at = expires_at
    else:
        token = StravaToken(
            user_id=TEST_USER_ID,
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=expires_at,
        )
        db.add(token)

    db.commit()
    db.refresh(token)
    return token


def refresh_access_token(db: Session) -> StravaToken:
    """Use refresh token to get a new access token when expired."""
    token = db.query(StravaToken).filter_by(user_id=TEST_USER_ID).first()
    if not token:
        raise ValueError("No Strava token found — run OAuth flow first")

    response = httpx.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "refresh_token": token.refresh_token,
            "grant_type": "refresh_token",
        }
    )
    response.raise_for_status()
    data = response.json()

    token.access_token = data["access_token"]
    token.refresh_token = data["refresh_token"]
    token.expires_at = datetime.fromtimestamp(data["expires_at"], tz=timezone.utc)

    db.commit()
    db.refresh(token)
    return token


# Refresh slightly early so a token can't expire between this check
# and the API call that uses it
TOKEN_EXPIRY_MARGIN = timedelta(minutes=5)


def get_valid_token(db: Session) -> str:
    """Return a valid access token, refreshing if expired or about to expire."""
    token = db.query(StravaToken).filter_by(user_id=TEST_USER_ID).first()
    if not token:
        raise ValueError("No Strava token found — run OAuth flow first")

    now = datetime.now(tz=timezone.utc)
    if token.expires_at <= now + TOKEN_EXPIRY_MARGIN:
        token = refresh_access_token(db)

    return token.access_token
