"""Password hashing, JWT sessions, and plan-based access control."""
from __future__ import annotations

import datetime as dt
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import hashlib
import secrets

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import ApiKey, User

PLAN_ORDER = {"free": 0, "essential": 1, "pro": 2}


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode({"sub": str(user.id), "iat": int(now.timestamp()),
                       "exp": now + dt.timedelta(hours=settings.jwt_ttl_hours)},
                      settings.jwt_secret, algorithm="HS256")


def _token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get("irai_token")


API_KEY_PREFIX = "irai_"


def new_api_key() -> tuple[str, str]:
    """Returns (plaintext key shown once, sha256 hash stored)."""
    key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return key, hashlib.sha256(key.encode()).hexdigest()


def _api_key_user(request: Request, db: Session) -> User | None:
    key = request.headers.get("x-api-key")
    if not key:
        return None
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        raise HTTPException(403, "API keys are read-only")
    row = db.query(ApiKey).filter(ApiKey.key_hash == hashlib.sha256(key.encode()).hexdigest(),
                                  ApiKey.revoked_at.is_(None)).first()
    if not row:
        raise HTTPException(401, "Invalid or revoked API key")
    user = db.get(User, row.user_id)
    if not user or user.disabled or not limits(user)["api"]:
        raise HTTPException(403, "API access needs an active Pro plan")
    now = dt.datetime.now(dt.timezone.utc)
    last = row.last_used_at.replace(tzinfo=dt.timezone.utc) if row.last_used_at and row.last_used_at.tzinfo is None else row.last_used_at
    if not last or (now - last).total_seconds() > 60:  # don't write on every request
        row.last_used_at = now
        db.commit()
    return user


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    if request.headers.get("x-api-key"):
        return _api_key_user(request, db)
    tok = _token(request)
    if not tok:
        return None
    try:
        data = jwt.decode(tok, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    user = db.get(User, int(data["sub"]))
    if user is None or user.disabled:
        return None
    if user.tokens_valid_after:
        valid_after = user.tokens_valid_after
        if valid_after.tzinfo is None:
            valid_after = valid_after.replace(tzinfo=dt.timezone.utc)
        if data.get("iat", 0) < int(valid_after.timestamp()):
            return None
    return user


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "Sign in required")
    return user


@lru_cache
def plans() -> dict[str, dict[str, Any]]:
    data = json.loads((Path(__file__).parent / "seed_data" / "plans.json").read_text())
    return {p["key"]: p for p in data}


def plan_of(user: User | None) -> str:
    return user.plan if user else "free"


def limits(user: User | None) -> dict[str, Any]:
    return plans()[plan_of(user)]["limits"]


def require_plan(minimum: str):
    def dep(user: User = Depends(current_user)) -> User:
        if PLAN_ORDER.get(user.plan, 0) < PLAN_ORDER[minimum]:
            raise HTTPException(402, f"This feature needs the {plans()[minimum]['name']} plan")
        return user
    return dep
