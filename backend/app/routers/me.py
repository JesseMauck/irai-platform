"""Watchlists and alerts (plan-limited), plus the alert evaluator."""
from __future__ import annotations

import datetime as dt

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..market import engines, service
from ..models import AdrPair, Alert, AlertEvent, User, Watchlist, WatchlistItem
from ..security import current_user, limits

router = APIRouter(prefix="/api/me", tags=["me"])


def _wl(w: Watchlist, with_quotes: bool = False) -> dict:
    syms = [i.symbol for i in w.items]
    out = {"id": w.id, "name": w.name, "symbols": syms}
    if with_quotes:
        out["quotes"] = service.quotes(syms)
    return out


@router.get("/watchlists")
def watchlists(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.watchlists:  # every account has at least one list
        db.add(Watchlist(user_id=user.id, name="My watchlist"))
        db.commit()
        db.refresh(user)
    return [_wl(w, with_quotes=True) for w in user.watchlists]


class WatchlistIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.post("/watchlists")
def create_watchlist(body: WatchlistIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cap = limits(user)["watchlists"]
    if cap is not None and len(user.watchlists) >= cap:
        raise HTTPException(402, f"Your plan allows {cap} watchlist(s)")
    w = Watchlist(user_id=user.id, name=body.name)
    db.add(w)
    db.commit()
    return _wl(w)


def _own(db: Session, user: User, wid: int) -> Watchlist:
    w = db.get(Watchlist, wid)
    if not w or w.user_id != user.id:
        raise HTTPException(404)
    return w


class SymbolIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9^=.\-]+$")


@router.post("/watchlists/{wid}/items")
def add_item(wid: int, body: SymbolIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = _own(db, user, wid)
    cap = limits(user)["watchlist_size"]
    if cap is not None and len(w.items) >= cap:
        raise HTTPException(402, f"Your plan allows {cap} tickers per watchlist")
    sym = body.symbol.upper()
    service.quote(sym)  # validates the symbol exists (or falls back to demo)
    if sym not in [i.symbol for i in w.items]:
        db.add(WatchlistItem(watchlist_id=w.id, symbol=sym))
        db.commit()
    db.refresh(w)
    return _wl(w)


@router.delete("/watchlists/{wid}/items/{symbol}")
def remove_item(wid: int, symbol: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = _own(db, user, wid)
    for i in w.items:
        if i.symbol == symbol.upper():
            db.delete(i)
    db.commit()
    db.refresh(w)
    return _wl(w)


@router.delete("/watchlists/{wid}")
def delete_watchlist(wid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own(db, user, wid))
    db.commit()
    return {"ok": True}


# ── alerts ────────────────────────────────────────────────────────────────────────────────────────
KINDS = {"price_above", "price_below", "change_pct_abs", "adr_z_abs"}


class AlertIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9^=.\-]+$")
    kind: str
    threshold: float
    channel: str = "email"
    webhook_url: HttpUrl | None = None


def _alert(a: Alert) -> dict:
    return {"id": a.id, "symbol": a.symbol, "kind": a.kind, "threshold": a.threshold, "channel": a.channel,
            "webhook_url": a.webhook_url, "active": a.active,
            "last_triggered_at": a.last_triggered_at.isoformat() if a.last_triggered_at else None}


@router.get("/alerts")
def alerts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_alert(a) for a in db.scalars(select(Alert).where(Alert.user_id == user.id))]


@router.post("/alerts")
def create_alert(body: AlertIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cap = limits(user)["alerts"]
    n = db.scalar(select(func.count()).select_from(Alert).where(Alert.user_id == user.id, Alert.active)) or 0
    if cap is not None and n >= cap:
        raise HTTPException(402, f"Your plan allows {cap} active alerts")
    if body.kind not in KINDS:
        raise HTTPException(422, f"kind must be one of {sorted(KINDS)}")
    if body.channel not in ("email", "webhook", "push"):
        raise HTTPException(422, "channel must be email, webhook or push")
    if body.channel != "email" and user.plan != "pro":
        raise HTTPException(402, "Webhook and push alerts need Pro")
    if body.channel == "webhook" and not body.webhook_url:
        raise HTTPException(422, "webhook_url required")
    a = Alert(user_id=user.id, symbol=body.symbol.upper(), kind=body.kind, threshold=body.threshold,
              channel=body.channel, webhook_url=str(body.webhook_url) if body.webhook_url else None)
    db.add(a)
    db.commit()
    return _alert(a)


@router.delete("/alerts/{aid}")
def delete_alert(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Alert, aid)
    if not a or a.user_id != user.id:
        raise HTTPException(404)
    db.delete(a)
    db.commit()
    return {"ok": True}


def evaluate_alerts(db: Session, cooldown_minutes: int = 60) -> list[dict]:
    """Check every active alert against live data; record and deliver triggers. Run on a schedule
    (e.g. `python -m app.jobs alerts` from cron every minute)."""
    fired = []
    now = dt.datetime.now(dt.timezone.utc)
    pairs = {p.adr_symbol: p for p in db.scalars(select(AdrPair))}
    for a in db.scalars(select(Alert).where(Alert.active)).all():
        last = a.last_triggered_at
        if last and last.tzinfo is None:
            last = last.replace(tzinfo=dt.timezone.utc)
        if last and (now - last).total_seconds() < cooldown_minutes * 60:
            continue
        try:
            if a.kind == "adr_z_abs":
                p = pairs.get(a.symbol)
                if not p:
                    continue
                row = engines.adr_row({c.name: getattr(p, c.name) for c in AdrPair.__table__.columns})
                value = row.get("z")
                hit = value is not None and abs(value) >= a.threshold
            else:
                q = service.quote(a.symbol)
                value = q["price"] if a.kind.startswith("price") else (q.get("change_pct") or 0) * 100
                hit = ((a.kind == "price_above" and value >= a.threshold) or
                       (a.kind == "price_below" and value <= a.threshold) or
                       (a.kind == "change_pct_abs" and abs(value) >= a.threshold))
        except Exception:  # noqa: BLE001
            continue
        if not hit:
            continue
        msg = f"{a.symbol}: {a.kind.replace('_', ' ')} {a.threshold:g} triggered at {value:,.4g}"
        db.add(AlertEvent(alert_id=a.id, value=float(value), message=msg))
        a.last_triggered_at = now
        if a.channel == "webhook" and a.webhook_url:
            try:
                httpx.post(a.webhook_url, json={"symbol": a.symbol, "kind": a.kind, "threshold": a.threshold,
                                                "value": value, "message": msg}, timeout=5)
            except httpx.HTTPError:
                pass
        fired.append({"alert_id": a.id, "message": msg})
    db.commit()
    return fired


@router.get("/alerts/events")
def alert_events(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(AlertEvent, Alert).join(Alert).where(Alert.user_id == user.id)
                      .order_by(AlertEvent.triggered_at.desc()).limit(50)).all()
    return [{"symbol": al.symbol, "message": ev.message, "value": ev.value, "triggered_at": ev.triggered_at.isoformat()}
            for ev, al in rows]
