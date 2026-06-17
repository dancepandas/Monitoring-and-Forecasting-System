import bcrypt
import logging
from sqlalchemy.orm import Session
from .database import engine, SessionLocal, Base
from .models import User

logger = logging.getLogger(__name__)

INIT_USERS = [
    {"username": "admin", "password": "admin123", "display_name": "超级管理员", "role": "super_admin"},
    {"username": "operator", "password": "operator123", "display_name": "值班管理员", "role": "admin"},
]

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(User).count()
        if existing > 0:
            logger.info(f"Database already has {existing} users, skipping seed")
            return
        for u in INIT_USERS:
            pw = bcrypt.hashpw(u["password"].encode(), bcrypt.gensalt()).decode()
            db.add(User(username=u["username"], password_hash=pw, display_name=u["display_name"], role=u["role"]))
        db.commit()
        logger.info(f"Seeded {len(INIT_USERS)} users: {[u['username'] for u in INIT_USERS]}")
    finally:
        db.close()
