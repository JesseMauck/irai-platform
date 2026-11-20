"""Subscriptions. With STRIPE_SECRET_KEY set, checkout goes through Stripe Checkout and the webhook
keeps plans in sync. Without it (local dev), checkout activates a 7-day trial directly."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Subscription, User
from ..security import current_user

router = APIRouter(prefix="/api/billing", tags=["billing"])
TRIAL_DAYS = 7


class CheckoutIn(BaseModel):
    plan: str
    interval: str = "monthly"


def _active(db: Session, user: User) -> Subscription | None:
    return db.scalar(select(Subscription).where(Subscription.user_id == user.id,
                                                Subscription.status.in_(["trialing", "active", "past_due"]))
                     .order_by(Subscription.id.desc()))


@router.get("/subscription")
def subscription(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _active(db, user)
    return {"plan": user.plan, "subscription": None if not s else {
        "plan": s.plan, "interval": s.interval, "status": s.status, "cancel_at_period_end": s.cancel_at_period_end,
        "trial_ends_at": s.trial_ends_at.isoformat() if s.trial_ends_at else None,
        "current_period_end": s.current_period_end.isoformat() if s.current_period_end else None}}


@router.post("/checkout")
def checkout(body: CheckoutIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.plan not in ("essential", "pro") or body.interval not in ("monthly", "annual"):
        raise HTTPException(422, "plan must be essential|pro and interval monthly|annual")
    if settings.stripe_secret_key:
        price = settings.stripe_prices.get(f"{body.plan}_{body.interval}")
        if not price:
            raise HTTPException(500, f"Stripe price for {body.plan}_{body.interval} is not configured")
        r = httpx.post("https://api.stripe.com/v1/checkout/sessions", auth=(settings.stripe_secret_key, ""), data={
            "mode": "subscription", "line_items[0][price]": price, "line_items[0][quantity]": 1,
            "subscription_data[trial_period_days]": TRIAL_DAYS, "client_reference_id": str(user.id),
            "customer_email": user.email, "metadata[plan]": body.plan, "metadata[interval]": body.interval,
            "success_url": f"{settings.public_url}/account?checkout=success",
            "cancel_url": f"{settings.public_url}/pricing?checkout=cancel"}, timeout=20)
        if r.status_code >= 400:
            raise HTTPException(502, f"Stripe error: {r.text[:200]}")
        return {"url": r.json()["url"]}
    # Dev mode: no payment provider configured → start the trial immediately.
    now = dt.datetime.now(dt.timezone.utc)
    old = _active(db, user)
    if old:
        old.status = "canceled"
    db.add(Subscription(user_id=user.id, plan=body.plan, interval=body.interval, status="trialing",
                        trial_ends_at=now + dt.timedelta(days=TRIAL_DAYS),
                        current_period_end=now + dt.timedelta(days=TRIAL_DAYS)))
    user.plan = body.plan
    db.commit()
    return {"url": None, "plan": user.plan, "dev_mode": True}


@router.post("/cancel")
def cancel(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _active(db, user)
    if not s:
        raise HTTPException(404, "No active subscription")
    if settings.stripe_secret_key and s.stripe_subscription_id:
        httpx.post(f"https://api.stripe.com/v1/subscriptions/{s.stripe_subscription_id}",
                   auth=(settings.stripe_secret_key, ""), data={"cancel_at_period_end": "true"}, timeout=20)
        s.cancel_at_period_end = True
    else:
        s.status, user.plan = "canceled", "free"
    db.commit()
    return {"ok": True, "plan": user.plan}


def verify_stripe_signature(payload: bytes, header: str, secret: str, tolerance: int = 300) -> bool:
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts, sig = int(parts["t"]), parts["v1"]
    except (KeyError, ValueError):
        return False
    if abs(time.time() - ts) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    if not settings.stripe_webhook_secret or not verify_stripe_signature(
            payload, request.headers.get("stripe-signature", ""), settings.stripe_webhook_secret):
        raise HTTPException(400, "Bad signature")
    event = json.loads(payload)
    obj = event["data"]["object"]
    kind = event["type"]
    if kind == "checkout.session.completed":
        user = db.get(User, int(obj["client_reference_id"]))
        if user:
            plan = obj.get("metadata", {}).get("plan", "essential")
            db.add(Subscription(user_id=user.id, plan=plan, interval=obj.get("metadata", {}).get("interval", "monthly"),
                                status="trialing", stripe_subscription_id=obj.get("subscription")))
            user.plan, user.stripe_customer_id = plan, obj.get("customer")
    elif kind in ("customer.subscription.updated", "customer.subscription.deleted"):
        s = db.scalar(select(Subscription).where(Subscription.stripe_subscription_id == obj["id"]))
        if s:
            s.status = obj["status"] if kind.endswith("updated") else "canceled"
            s.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
            if obj.get("current_period_end"):
                s.current_period_end = dt.datetime.fromtimestamp(obj["current_period_end"], dt.timezone.utc)
            u = db.get(User, s.user_id)
            if u and s.status in ("canceled", "unpaid", "incomplete_expired"):
                u.plan = "free"
    db.commit()
    return {"received": True}
