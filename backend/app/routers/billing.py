"""Subscriptions: an in-app 7-day trial (no card), then paid plans through Square.

  POST /api/billing/trial        start the one-time 7-day trial of Essential or Pro
  POST /api/billing/checkout     Square-hosted checkout link for a plan variation (or dev-mode activation)
  POST /api/billing/cancel       cancel at the end of the paid period (Square) / end a trial
  POST /api/billing/webhook/square   subscription.created / subscription.updated (signature-verified)

Without SQUARE_ACCESS_TOKEN (local dev) checkout activates the plan directly so the app is testable.
"""
from __future__ import annotations

import datetime as dt
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import mail
from ..config import settings
from ..db import get_db
from ..models import Subscription, User
from ..payments.square import SquareClient, SquareConfig, SquareError, verify_signature
from ..security import current_user, plans

router = APIRouter(prefix="/api/billing", tags=["billing"])
log = logging.getLogger("irai.billing")
TRIAL_DAYS = 7
LIVE = ("trialing", "active", "past_due")


def square_client() -> SquareClient | None:
    cfg = SquareConfig.from_env()
    return SquareClient(cfg) if cfg.enabled else None


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(d: dt.datetime | None) -> dt.datetime | None:
    return d.replace(tzinfo=dt.timezone.utc) if d is not None and d.tzinfo is None else d


def _iso(d: dt.datetime | None) -> str | None:
    """Always answer in UTC, whatever time zone the database session uses."""
    d = _aware(d)
    return d.astimezone(dt.timezone.utc).isoformat() if d else None


def _current(db: Session, user: User) -> Subscription | None:
    return db.scalar(select(Subscription).where(Subscription.user_id == user.id, Subscription.status.in_(LIVE))
                     .order_by(Subscription.id.desc()))


def _sub_out(s: Subscription | None) -> dict | None:
    if not s:
        return None
    return {"plan": s.plan, "interval": s.interval, "status": s.status, "provider": s.provider,
            "cancel_at_period_end": s.cancel_at_period_end,
            "trial_ends_at": _iso(s.trial_ends_at), "current_period_end": _iso(s.current_period_end)}


@router.get("/subscription")
def subscription(user: User = Depends(current_user), db: Session = Depends(get_db)):
    used_trial = db.scalar(select(func.count()).select_from(Subscription).where(
        Subscription.user_id == user.id, Subscription.provider == "internal", Subscription.trial_ends_at.is_not(None))) or 0
    return {"plan": user.plan, "subscription": _sub_out(_current(db, user)), "trial_available": used_trial == 0,
            "payments": "square" if square_client() else "dev"}


class PlanIn(BaseModel):
    plan: str
    interval: str = "monthly"


def _check(body: PlanIn) -> None:
    if body.plan not in ("essential", "pro") or body.interval not in ("monthly", "annual"):
        raise HTTPException(422, "plan must be essential|pro and interval monthly|annual")


@router.post("/trial")
def start_trial(body: PlanIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _check(body)
    if db.scalar(select(Subscription).where(Subscription.user_id == user.id, Subscription.provider == "internal",
                                            Subscription.trial_ends_at.is_not(None))):
        raise HTTPException(409, "You've already used your free trial")
    cur = _current(db, user)
    if cur and cur.provider == "square":
        raise HTTPException(409, "You already have a paid membership")
    end = _now() + dt.timedelta(days=TRIAL_DAYS)
    db.add(Subscription(user_id=user.id, plan=body.plan, interval=body.interval, status="trialing", provider="internal",
                        trial_ends_at=end, current_period_end=end))
    user.plan = body.plan
    mail.enqueue(db, user.email, f"Your 7-day {plans()[body.plan]['name']} trial has started",
                 f"Hi {user.display_name},\n\nYou have full {plans()[body.plan]['name']} access until "
                 f"{end:%B %d}. No card was taken. To keep it afterwards, choose a plan at {mail.link('/pricing')}."
                 f"{mail.FOOTER}", "trial_started")
    db.commit()
    return {"plan": user.plan, "trial_ends_at": end.isoformat()}


@router.post("/checkout")
def checkout(body: PlanIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _check(body)
    sq = square_client()
    p = plans()[body.plan]
    if sq is None:  # dev mode: no processor configured → activate directly so the product is testable
        cur = _current(db, user)
        if cur:
            cur.status = "canceled"
        db.add(Subscription(user_id=user.id, plan=body.plan, interval=body.interval, status="active", provider="internal",
                            current_period_end=_now() + dt.timedelta(days=30 if body.interval == "monthly" else 365)))
        user.plan = body.plan
        db.commit()
        return {"url": None, "plan": user.plan, "dev_mode": True}
    variation = sq.cfg.plan_variations.get(f"{body.plan}_{body.interval}")
    if not variation:
        raise HTTPException(500, f"Square plan variation for {body.plan}_{body.interval} is not configured")
    cents = int((p["monthly"] if body.interval == "monthly" else p["annual"]) * 100)
    try:
        link = sq.create_subscription_link(
            variation_id=variation, name=f"Irradiance {p['name']} ({body.interval})", amount_cents=cents,
            buyer_email=user.email, redirect_url=f"{settings.public_url}/account?checkout=square",
            reference=f"irai-user:{user.id}")
    except SquareError as e:
        raise HTTPException(502, f"Square: {e}")
    db.add(Subscription(user_id=user.id, plan=body.plan, interval=body.interval, status="pending", provider="square",
                        provider_ref=link["order_id"] or link["id"]))
    db.commit()
    return {"url": link["url"]}


@router.post("/cancel")
def cancel(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _current(db, user)
    if not s:
        raise HTTPException(404, "No active membership")
    if s.provider == "square" and s.provider_subscription_id:
        sq = square_client()
        if sq is None:
            raise HTTPException(500, "Square is not configured")
        try:
            sub = sq.cancel_subscription(s.provider_subscription_id)
        except SquareError as e:
            raise HTTPException(502, f"Square: {e}")
        s.cancel_at_period_end = True
        if sub.get("canceled_date"):
            s.current_period_end = dt.datetime.fromisoformat(sub["canceled_date"]).replace(tzinfo=dt.timezone.utc)
        db.commit()
        return {"ok": True, "plan": user.plan, "access_until": _iso(s.current_period_end)}
    s.status, user.plan = "canceled", "free"
    db.commit()
    return {"ok": True, "plan": user.plan}


# ── Square webhook ─────────────────────────────────────────────────────────────────────────────────
SQUARE_STATUS = {"ACTIVE": "active", "PENDING": "pending", "PAUSED": "past_due", "CANCELED": "canceled",
                 "DEACTIVATED": "canceled"}


def apply_square_subscription(db: Session, sub: dict, sq: SquareClient | None) -> str:
    """Upsert our subscription row from a Square subscription object. Idempotent."""
    cfg = sq.cfg if sq else SquareConfig.from_env()
    mapped = cfg.plan_for_variation(sub.get("plan_variation_id"))
    if not mapped:
        return "ignored: unknown plan variation"
    plan, interval = mapped
    row = db.scalar(select(Subscription).where(Subscription.provider_subscription_id == sub["id"]))
    user = db.get(User, row.user_id) if row else None
    if user is None and sub.get("customer_id"):
        user = db.scalar(select(User).where(User.payment_customer_id == sub["customer_id"]))
        if user is None and sq is not None:
            try:
                email = (sq.get_customer(sub["customer_id"]).get("email_address") or "").lower()
            except SquareError:
                email = ""
            if email:
                user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        log.warning("square subscription %s: no matching member", sub["id"])
        return "ignored: no matching member"
    user.payment_customer_id = sub.get("customer_id") or user.payment_customer_id
    if row is None:  # first event for this subscription: claim the pending checkout row if there is one
        row = db.scalar(select(Subscription).where(Subscription.user_id == user.id, Subscription.provider == "square",
                                                   Subscription.status == "pending", Subscription.provider_subscription_id.is_(None))
                        .order_by(Subscription.id.desc()))
        if row is None:
            row = Subscription(user_id=user.id, plan=plan, interval=interval, provider="square")
            db.add(row)
        row.provider_subscription_id = sub["id"]
    status = SQUARE_STATUS.get(sub.get("status", ""), "pending")
    row.plan, row.interval, row.status = plan, interval, status
    if sub.get("charged_through_date"):
        row.current_period_end = dt.datetime.fromisoformat(sub["charged_through_date"]).replace(tzinfo=dt.timezone.utc)
    if sub.get("canceled_date"):
        row.cancel_at_period_end = True
    if status in ("active", "past_due"):
        user.plan = plan
        for other in db.scalars(select(Subscription).where(Subscription.user_id == user.id, Subscription.id != row.id,
                                                          Subscription.status.in_(LIVE))):
            other.status = "canceled"  # a paid plan replaces any trial
    elif status == "canceled":
        user.plan = "free"
    db.commit()
    return f"{status}: {user.handle} {plan}/{interval}"


@router.post("/webhook/square")
async def square_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    cfg = SquareConfig.from_env()
    if not verify_signature(body, request.headers.get("x-square-hmacsha256-signature", ""),
                            cfg.webhook_signature_key, cfg.webhook_url):
        raise HTTPException(401, "Bad signature")
    event = json.loads(body)
    kind = event.get("type", "")
    if kind in ("subscription.created", "subscription.updated"):
        sub = ((event.get("data") or {}).get("object") or {}).get("subscription")
        if sub and sub.get("id"):
            return {"received": True, "result": apply_square_subscription(db, sub, square_client())}
    return {"received": True, "result": "ignored"}


def process_trials(db: Session) -> dict:
    """Worker job: email a reminder 2 days before an in-app trial ends; downgrade expired trials."""
    now = _now()
    reminded = expired = 0
    for s in db.scalars(select(Subscription).where(Subscription.provider == "internal", Subscription.status == "trialing")).all():
        end = _aware(s.trial_ends_at)
        if not end:
            continue
        u = db.get(User, s.user_id)
        if end <= now:
            s.status = "canceled"
            if u and not db.scalar(select(Subscription).where(Subscription.user_id == u.id, Subscription.id != s.id,
                                                              Subscription.status.in_(LIVE))):
                u.plan = "free"
                mail.enqueue(db, u.email, "Your Irradiance trial has ended",
                             f"Your trial ended and your account is back on the Free plan. Pick up where you left off: "
                             f"{mail.link('/pricing')}{mail.FOOTER}", "trial_ended")
            expired += 1
        elif not s.trial_reminder_sent and end - now <= dt.timedelta(hours=48) and u:
            mail.enqueue(db, u.email, "Your Irradiance trial ends in 2 days",
                         f"Your {plans()[s.plan]['name']} trial ends {end:%B %d}. Subscribe to keep full access: "
                         f"{mail.link('/pricing')}{mail.FOOTER}", "trial_reminder")
            s.trial_reminder_sent = True
            reminded += 1
    db.commit()
    return {"reminded": reminded, "expired": expired}
