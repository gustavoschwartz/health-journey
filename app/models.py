import uuid
from sqlalchemy import (
    Column, String, Integer, Float, Boolean,
    Date, Time, DateTime, Text, Enum, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
import enum

Base = declarative_base()

# --- Enums ---

class OverallFeelingEnum(enum.Enum):
    great = "great"
    good = "good"
    neutral = "neutral"
    bad = "bad"
    terrible = "terrible"

class WorkoutFeelingEnum(enum.Enum):
    strong = "strong"
    normal = "normal"
    weak = "weak"

class AlcoholTypeEnum(enum.Enum):
    beer = "beer"
    wine = "wine"
    hard_liquor = "hard_liquor"

class ConversationRoleEnum(enum.Enum):
    user = "user"
    assistant = "assistant"

class SyncStatusEnum(enum.Enum):
    success = "success"
    partial = "partial"
    failed = "failed"

# --- Models ---

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DailySummary(Base):
    __tablename__ = "daily_summary"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    overall_feeling = Column(Enum(OverallFeelingEnum), nullable=True)
    calories_previous_day = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)


class Workout(Base):
    __tablename__ = "workout"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    strava_id = Column(String, nullable=False, unique=True)
    type = Column(String, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    distance_km = Column(Float, nullable=True)
    avg_heart_rate = Column(Integer, nullable=True)
    calories = Column(Integer, nullable=True)
    feeling = Column(Enum(WorkoutFeelingEnum), nullable=True)
    feeling_prompted = Column(Boolean, nullable=False, default=False)


class AppleHealthDaily(Base):
    __tablename__ = "apple_health_daily"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    timezone = Column(String, nullable=True)
    steps = Column(Integer, nullable=False)
    sleep_hours = Column(Float, nullable=False)
    sleep_deep_minutes = Column(Integer, nullable=False)
    sleep_rem_minutes = Column(Integer, nullable=False)
    sleep_awake_minutes = Column(Integer, nullable=False)
    hrv_ms = Column(Float, nullable=True)
    resting_heart_rate = Column(Integer, nullable=True)


class Weight(Base):
    __tablename__ = "weight"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    weight_kg = Column(Float, nullable=False)


class BpReading(Base):
    __tablename__ = "bp_reading"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    systolic = Column(Integer, nullable=False)
    diastolic = Column(Integer, nullable=False)
    pulse = Column(Integer, nullable=False)
    time_of_day = Column(Time, nullable=True)


class MounjaroDose(Base):
    __tablename__ = "mounjaro_dose"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    dose_mg = Column(Float, nullable=False)


class AlcoholConsumption(Base):
    __tablename__ = "alcohol_consumption"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    type = Column(Enum(AlcoholTypeEnum), nullable=False)
    drinks = Column(Integer, nullable=False)


class ConversationHistory(Base):
    __tablename__ = "conversation_history"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    session_id = Column(UUID(as_uuid=True), nullable=False)
    role = Column(Enum(ConversationRoleEnum), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ConversationSummary(Base):
    __tablename__ = "conversation_summary"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    summary = Column(Text, nullable=False)
    covers_from = Column(Date, nullable=False)
    covers_to = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SyncLog(Base):
    __tablename__ = "sync_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    synced_date = Column(Date, nullable=False)
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(Enum(SyncStatusEnum), nullable=False)

class StravaToken(Base):
    __tablename__ = "strava_token"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

