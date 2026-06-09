import uuid
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from app.models import User

load_dotenv()

TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def seed():
    engine = create_engine(os.getenv("DATABASE_URL"))
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    existing = db.query(User).filter_by(id=TEST_USER_ID).first()
    if existing:
        print("Phase 1 user already exists — skipping")
    else:
        user = User(
            id=TEST_USER_ID,
            email="gustavovarejao@gmail.com"
        )
        db.add(user)
        db.commit()
        print(f"Phase 1 user created: {TEST_USER_ID}")

    db.close()


if __name__ == "__main__":
    seed()
