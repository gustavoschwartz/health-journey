import os
import secrets
import time
import httpx
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models import StravaToken
from app.config import TEST_USER_ID


# Env vars read inside functions, not at import time — module import order
# must never decide whether credentials are present.

def _client_credentials() -> tuple[str, str]:
    return os.getenv("STRAVA_CLIENT_ID"), os.getenv("STRAVA_CLIENT_SECRET")


def _redirect_uri() -> str:
    return os.getenv("STRAVA_REDIRECT_URI", "http://localhost:8000/strava/callback")


# --- OAuth state (CSRF protection) ---
# One-time tokens held in memory: fine for the single-process Phase 1 deploy,
# and losing them on restart only means re-requesting the auth URL.

STATE_TTL_SECONDS = 600  # OAuth round-trip should take minutes, not hours

_pending_states: dict[str, float] = {}


def _prune_expired_states() -> None:
    now = time.time()
    for state, expires in list(_pending_states.items()):
        if expires <= now:
            del _pending_states[state]


def generate_state() -> str:
    _prune_expired_states()
    state = secrets.token_urlsafe(32)
    _pending_states[state] = time.time() + STATE_TTL_SECONDS
    return state


def consume_state(state: str) -> bool:
    """One-time check: True only if we issued this state and it hasn't
    expired or been used. Consuming removes it — replays fail."""
    _prune_expired_states()
    return _pending_states.pop(state, None) is not None


def get_auth_url() -> str:
    """Generate the Strava OAuth authorization URL."""
    client_id, _ = _client_credentials()
    return (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={_redirect_uri()}"
        f"&response_type=code"
        f"&scope=activity:read_all"
        f"&state={generate_state()}"
    )


def exchange_code_for_tokens(code: str, db: Session) -> StravaToken:
    """Exchange authorization code for access + refresh tokens."""
    client_id, client_secret = _client_credentials()
    response = httpx.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
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

    client_id, client_secret = _client_credentials()
    response = httpx.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
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
