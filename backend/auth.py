"""
Mörkrets Rike — Auth helpers
=============================
JWT + bcrypt mot data/users.json.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "byt-mig-till-nagot-langt-och-slumpmassigt")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

DATA_DIR = Path(__file__).resolve().parent / "data"
USERS_FILE = DATA_DIR / "users.json"


def load_users() -> dict:
    """Läs users.json → {username: {password_hash, role}}."""
    if not USERS_FILE.exists():
        return {}
    with open(USERS_FILE) as f:
        return json.load(f)


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def create_token(username: str, role: str) -> str:
    """Skapa JWT med 24h livslängd."""
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict | None:
    """Validera JWT. Returnerar payload eller None."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
