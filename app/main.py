from dotenv import load_dotenv
load_dotenv()

from fastapi.responses import StreamingResponse
from app.services.sync import run_sync, local_today
from app.services.backfill import run_first_backfill
import json
import os
from datetime import date
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine, text
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session, sessionmaker
from app.services.strava_auth import get_auth_url, exchange_code_for_tokens, consume_state

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")
# pre_ping revalidates pooled connections — Railway's proxy drops idle ones,
# which otherwise surfaces as a stale-connection error on the first request
# after a quiet period
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


# --- Request models ---

class ConversationRequest(BaseModel):
    session_id: str
    message: str
    timezone: str

class CheckinRequest(BaseModel):
    date: str
    field: str
    value: Optional[str] = None
    strava_id: Optional[str] = None

class SyncRequest(BaseModel):
    timezone: str
    last_synced_date: str

class BackfillRequest(BaseModel):
    timezone: str


# --- Database session dependency ---

SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Routes ---

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/health/db")
def db_health_check():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}

@app.post("/conversation")
def conversation(request: ConversationRequest):
    return {"status": "stub", "message": request.message}

@app.post("/checkin")
def checkin(request: CheckinRequest):
    return {"status": "stub", "field": request.field}

@app.post("/sync")
def sync(request: SyncRequest, db: Session = Depends(get_db)):
    last_synced = date.fromisoformat(request.last_synced_date)

    def generate():
        # run_sync is a generator — each event streams as its date completes
        for event in run_sync(last_synced, request.timezone, db):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/backfill")
def backfill(request: BackfillRequest, db: Session = Depends(get_db)):
    return run_first_backfill(db, today=local_today(request.timezone))


# --- Strava OAuth routes ---

@app.get("/strava/auth-url")
def strava_auth_url():
    return {"url": get_auth_url()}


@app.get("/strava/callback")
def strava_callback(code: str, state: str = "", db: Session = Depends(get_db)):
    # Reject any callback we didn't initiate — without this, an attacker
    # could complete the flow and bind their Strava account to our tokens
    if not consume_state(state):
        raise HTTPException(status_code=403, detail="Invalid or expired OAuth state")
    token = exchange_code_for_tokens(code, db)
    return {"status": "success", "expires_at": str(token.expires_at)}
