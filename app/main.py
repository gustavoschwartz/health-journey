import os
from fastapi import FastAPI, Depends
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from app.services.strava_auth import get_auth_url, exchange_code_for_tokens

load_dotenv()

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)


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
def sync(request: SyncRequest):
    return {"status": "stub", "timezone": request.timezone}

# --- Database session dependency ---

def get_db():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Strava OAuth routes ---

@app.get("/strava/auth-url")
def strava_auth_url():
    return {"url": get_auth_url()}


@app.get("/strava/callback")
def strava_callback(code: str, db: Session = Depends(get_db)):
    token = exchange_code_for_tokens(code, db)
    return {"status": "success", "expires_at": str(token.expires_at)}
