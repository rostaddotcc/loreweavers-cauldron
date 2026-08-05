"""
The Lore Weaver's Cauldron — Auth helpers
=============================
JWT + bcrypt mot data/users.json.
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "byt-mig-till-nagot-langt-och-slumpmassigt")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "2"))

DATA_DIR = Path(__file__).resolve().parent / "data"
USERS_FILE = DATA_DIR / "users.json"

# Kontoregler (iteration 1 — SMTP/verifiering/återställning kommer senare)
# 2026-08-06: tillåter å/ä/ö — svenska namn ska fungera i ett svenskt spel.
USERNAME_RE = re.compile(r"^[a-z0-9åäö][a-z0-9åäö_.-]{2,19}$")  # 3-20 tecken, startar med bokstav/siffra
PASSWORD_MIN_LEN = 6


def normalize_username(username: str) -> str:
    """Normalisera användarnamn: trim + lowercase. Dublettskydd bygger på detta."""
    return (username or "").strip().lower()


def validate_username(username: str) -> str | None:
    """Validera användarnamn. Returnerar felmeddelande eller None om OK."""
    uname = normalize_username(username)
    if not uname:
        return "Username is required."
    if not USERNAME_RE.match(uname):
        return "Names must be 3–20 characters: letters a–z (å ä ö ok), numbers, _ - . Start with a letter or number."
    return None


def validate_password(password: str) -> str | None:
    """Validera lösenord. Returnerar felmeddelande eller None om OK."""
    if not password:
        return "Password is required."
    if len(password) < PASSWORD_MIN_LEN:
        return f"Password must be at least {PASSWORD_MIN_LEN} characters."
    return None


def load_users() -> dict:
    """Läs users.json → {username: {password_hash, role}}."""
    if not USERS_FILE.exists():
        return {}
    with open(USERS_FILE) as f:
        return json.load(f)


def save_users(users: dict) -> None:
    """Skriv users.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


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
