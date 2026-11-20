from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, Watchlist
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
    resp.set_cookie("irai_token", tok, httponly=True, samesite="lax", max_age=72 * 3600)
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
    db.commit()
    return _session(resp, u)


@router.post("/login")
def login(body: LoginIn, resp: Response, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return _session(resp, u)


@router.post("/logout")
def logout(resp: Response):
    resp.delete_cookie("irai_token")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)
