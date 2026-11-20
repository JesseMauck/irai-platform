from __future__ import annotations

import datetime as dt
import hashlib
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import mail
from ..config import settings
from ..db import get_db
from ..models import PasswordReset, User, Watchlist
from ..security import create_token, current_user, hash_password, limits, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,29}$")


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    handle: str = Field(min_length=3, max_length=30)
    display_name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "handle": u.handle, "display_name": u.display_name, "plan": u.plan,
            "is_admin": u.is_admin, "verified_trader": u.verified_trader, "limits": limits(u)}


def _session(resp: Response, u: User) -> dict:
    tok = create_token(u)
    resp.set_cookie("irai_token", tok, httponly=True, samesite="lax", max_age=settings.jwt_ttl_hours * 3600,
                    secure=settings.public_url.startswith("https://"))
    return {"token": tok, "user": user_out(u)}


@router.post("/register")
def register(body: RegisterIn, resp: Response, db: Session = Depends(get_db)):
    handle = body.handle.lower()
    if not HANDLE_RE.match(handle):
        raise HTTPException(422, "Handle: 3-30 lowercase letters, digits, '-' or '_'")
    if db.scalar(select(User).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(409, "An account with that email already exists")
    if db.scalar(select(User).where(User.handle == handle)):
        raise HTTPException(409, "That handle is taken")
    u = User(email=body.email.lower(), handle=handle, display_name=body.display_name.strip(),
             password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    db.add(Watchlist(user_id=u.id, name="My watchlist"))
    mail.enqueue(db, u.email, "Welcome to Irradiance",
                 f"Hi {u.display_name},\n\nYour account (@{u.handle}) is ready. Press ⌘K on any page to look up a ticker, "
                 f"or start with the ADR Monitor: {mail.link('/monitor/adr')}{mail.FOOTER}", "welcome")
    db.commit()
    return _session(resp, u)


@router.post("/login")
def login(body: LoginIn, resp: Response, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Wrong email or password")
    if u.disabled:
        raise HTTPException(403, "This account is disabled")
    return _session(resp, u)


@router.post("/logout")
def logout(resp: Response):
    resp.delete_cookie("irai_token")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


RESET_TTL = dt.timedelta(hours=1)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ForgotIn(BaseModel):
    email: EmailStr


@router.post("/forgot")
def forgot(body: ForgotIn, db: Session = Depends(get_db)):
    """Always answers the same way, so the endpoint can't be used to discover which emails have accounts."""
    u = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if u and not u.disabled:
        token = secrets.token_urlsafe(32)
        db.add(PasswordReset(user_id=u.id, token_hash=_hash(token),
                             expires_at=dt.datetime.now(dt.timezone.utc) + RESET_TTL))
        mail.enqueue(db, u.email, "Reset your Irradiance password",
                     f"Hi {u.display_name},\n\nUse this link within the next hour to choose a new password:\n"
                     f"{mail.link('/reset?token=' + token)}\n\nIf you didn't ask for this, ignore this email.{mail.FOOTER}",
                     "password_reset")
        db.commit()
    return {"ok": True, "message": "If that email has an account, a reset link is on its way."}


class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=128)


@router.post("/reset")
def reset(body: ResetIn, resp: Response, db: Session = Depends(get_db)):
    now = dt.datetime.now(dt.timezone.utc)
    pr = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == _hash(body.token)))
    exp = pr.expires_at.replace(tzinfo=dt.timezone.utc) if pr and pr.expires_at.tzinfo is None else (pr.expires_at if pr else None)
    if not pr or pr.used_at or exp < now:
        raise HTTPException(400, "This reset link is invalid or has expired")
    u = db.get(User, pr.user_id)
    u.password_hash = hash_password(body.password)
    u.tokens_valid_after = now.replace(microsecond=0)  # sign out every earlier session
    for other in db.scalars(select(PasswordReset).where(PasswordReset.user_id == u.id, PasswordReset.used_at.is_(None))):
        other.used_at = now
    mail.enqueue(db, u.email, "Your Irradiance password was changed",
                 f"Hi {u.display_name},\n\nYour password was just changed and other sessions were signed out. "
                 f"If this wasn't you, reset it again now: {mail.link('/forgot')}{mail.FOOTER}", "password_changed")
    db.commit()
    return _session(resp, u)
