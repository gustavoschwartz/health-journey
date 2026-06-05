import os
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional

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
