"""Watchlists and alerts (plan-limited), plus the alert evaluator."""
from __future__ import annotations

import datetime as dt

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import mail
from ..db import get_db
from ..market import engines, service
from ..models import AdrPair, Alert, AlertEvent, ApiKey, SavedScreen, User, Watchlist, WatchlistItem
from ..security import current_user, limits, new_api_key

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
        elif a.channel == "email":
            owner = db.get(User, a.user_id)
            if owner and not owner.disabled:
                mail.enqueue(db, owner.email, f"Alert: {a.symbol}",
                             f"{msg}\n\nOpen {a.symbol}: {mail.link('/ticker/' + a.symbol)}\n"
                             f"Manage alerts: {mail.link('/account')}{mail.FOOTER}", "alert")
        fired.append({"alert_id": a.id, "message": msg})
    db.commit()
    return fired


@router.get("/alerts/events")
def alert_events(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(AlertEvent, Alert).join(Alert).where(Alert.user_id == user.id)
                      .order_by(AlertEvent.triggered_at.desc()).limit(50)).all()
    return [{"symbol": al.symbol, "message": ev.message, "value": ev.value, "triggered_at": ev.triggered_at.isoformat()}
            for ev, al in rows]


# ── API keys (Pro) ────────────────────────────────────────────────────────────────────────────────
class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


def _key(k: ApiKey) -> dict:
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "created_at": k.created_at.isoformat(),
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None}


@router.get("/api-keys")
def api_keys(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_key(k) for k in db.scalars(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None)))]


@router.post("/api-keys")
def create_api_key(body: ApiKeyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not limits(user)["api"]:
        raise HTTPException(402, "The read-only API is a Pro feature")
    active = db.scalar(select(func.count()).select_from(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None))) or 0
    if active >= 5:
        raise HTTPException(409, "Revoke a key first (maximum 5 active)")
    plain, digest = new_api_key()
    k = ApiKey(user_id=user.id, name=body.name, prefix=plain[:12], key_hash=digest)
    db.add(k)
    db.commit()
    return {**_key(k), "key": plain, "note": "Copy this key now. It is shown only once."}


@router.delete("/api-keys/{kid}")
def revoke_api_key(kid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    k = db.get(ApiKey, kid)
    if not k or k.user_id != user.id:
        raise HTTPException(404)
    k.revoked_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    return {"ok": True}


# ── saved screens ─────────────────────────────────────────────────────────────────────────────────
SCREEN_FILTERS = {
    "fundamental": {"rv_min", "quality_min", "multiple_max", "peer_group", "roe_min"},
    "adr": {"z_abs_min", "premium_min", "premium_max", "tradable_only", "country"},
    "etf": {"premium_abs_min", "category"},
}


class ScreenIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    universe: str
    filters: dict[str, float | str | bool] = {}
    alert_on_new: bool = False


def run_custom_screen(db: Session, universe: str, f: dict) -> list[dict]:
    from .monitors import _funds, _groups, _pairs
    if universe == "fundamental":
        rows = engines.build_fundamental(_groups(db))
        out = [r for r in rows
               if (f.get("rv_min") is None or (r["rv_percentile"] or -1) >= float(f["rv_min"]))
               and (f.get("quality_min") is None or r["quality_percentile"] >= float(f["quality_min"]))
               and (f.get("multiple_max") is None or (r["multiple"] is not None and r["multiple"] <= float(f["multiple_max"])))
               and (f.get("roe_min") is None or (r["roe"] is not None and r["roe"] >= float(f["roe_min"])))
               and (not f.get("peer_group") or r["peer_group"] == f["peer_group"])]
        return [{"symbol": r["symbol"], "name": r["name"], "detail": f"{r['grade']} · {r['peer_group']}",
                 "value": r["rv_percentile"], "source": r["source"]} for r in out]
    if universe == "adr":
        rows = engines.build_adr_monitor(_pairs(db))
        out = [r for r in rows if r.get("z") is not None
               and (f.get("z_abs_min") is None or abs(r["z"]) >= float(f["z_abs_min"]))
               and (f.get("premium_min") is None or r["premium"] >= float(f["premium_min"]))
               and (f.get("premium_max") is None or r["premium"] <= float(f["premium_max"]))
               and (not f.get("tradable_only") or r["tradable"])
               and (not f.get("country") or r["country"] == f["country"])]
        return [{"symbol": r["adr_symbol"], "name": f"{r['adr_symbol']} vs {r['local_symbol']}",
                 "detail": f"z {r['z']:+.1f}", "value": r["premium"], "source": r["source"]} for r in out]
    rows = engines.build_etf_monitor(_funds(db))
    out = [r for r in rows if r.get("premium") is not None
           and (f.get("premium_abs_min") is None or abs(r["premium"]) >= float(f["premium_abs_min"]))
           and (not f.get("category") or r["category"] == f["category"])]
    return [{"symbol": r["symbol"], "name": r["name"], "detail": r["category"], "value": r["premium"], "source": r["source"]}
            for r in out]


def _screen(sc: SavedScreen) -> dict:
    return {"id": sc.id, "name": sc.name, "universe": sc.universe, "filters": sc.filters, "alert_on_new": sc.alert_on_new,
            "created_at": sc.created_at.isoformat() if sc.created_at else None}


def _validate_screen(body: ScreenIn) -> None:
    if body.universe not in SCREEN_FILTERS:
        raise HTTPException(422, f"universe must be one of {sorted(SCREEN_FILTERS)}")
    bad = set(body.filters) - SCREEN_FILTERS[body.universe]
    if bad:
        raise HTTPException(422, f"Unknown filters for {body.universe}: {sorted(bad)}")


@router.post("/screens/preview")
def preview_screen(body: ScreenIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.plan == "free":
        raise HTTPException(402, "Custom screens need the Essential plan")
    _validate_screen(body)
    return {"rows": run_custom_screen(db, body.universe, body.filters)}


@router.get("/screens")
def screens(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_screen(s) for s in db.scalars(select(SavedScreen).where(SavedScreen.user_id == user.id).order_by(SavedScreen.id))]


@router.post("/screens")
def save_screen(body: ScreenIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cap = limits(user)["saved_screens"]
    n = db.scalar(select(func.count()).select_from(SavedScreen).where(SavedScreen.user_id == user.id)) or 0
    if cap is not None and n >= cap:
        raise HTTPException(402, "Your plan doesn't include saved screens" if cap == 0 else f"Your plan allows {cap} saved screens")
    _validate_screen(body)
    sc = SavedScreen(user_id=user.id, name=body.name, universe=body.universe, filters=body.filters,
                     alert_on_new=body.alert_on_new and (limits(user)["alerts"] is None or limits(user)["alerts"] > 0),
                     last_symbols=[r["symbol"] for r in run_custom_screen(db, body.universe, body.filters)])
    db.add(sc)
    db.commit()
    return _screen(sc)


@router.get("/screens/{sid}/run")
def run_saved_screen(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sc = db.get(SavedScreen, sid)
    if not sc or sc.user_id != user.id:
        raise HTTPException(404)
    return {**_screen(sc), "rows": run_custom_screen(db, sc.universe, sc.filters)}


@router.delete("/screens/{sid}")
def delete_screen(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sc = db.get(SavedScreen, sid)
    if not sc or sc.user_id != user.id:
        raise HTTPException(404)
    db.delete(sc)
    db.commit()
    return {"ok": True}


def check_screen_alerts(db: Session) -> int:
    """Worker job: email members when a saved screen with alert_on_new gains names."""
    sent = 0
    for sc in db.scalars(select(SavedScreen).where(SavedScreen.alert_on_new)).all():
        owner = db.get(User, sc.user_id)
        if not owner or owner.disabled:
            continue
        try:
            now_syms = [r["symbol"] for r in run_custom_screen(db, sc.universe, sc.filters)]
        except Exception:  # noqa: BLE001
            continue
        new = [x for x in now_syms if x not in (sc.last_symbols or [])]
        if new:
            mail.enqueue(db, owner.email, f"New names in your screen “{sc.name}”",
                         f"{', '.join(new)} now match “{sc.name}”.\n\n{mail.link('/screeners')}{mail.FOOTER}", "screen_alert")
            sent += 1
        sc.last_symbols = now_syms
    db.commit()
    return sent


# ── your data: export and account deletion (Privacy Policy §4, §6) ──────────────────────────────────
def _rows(db: Session, model, col, uid: int, drop: tuple[str, ...] = ()) -> list[dict]:
    out = []
    for r in db.scalars(select(model).where(getattr(model, col) == uid)):
        d = {}
        for c in model.__table__.columns:
            if c.name in drop:
                continue
            v = getattr(r, c.name)
            d[c.name] = v.isoformat() if isinstance(v, (dt.datetime, dt.date)) else v
        out.append(d)
    return out


@router.get("/export")
def export_my_data(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Everything we hold that is linked to your account, as JSON (secrets excluded)."""
    from ..models import (AnalystReport, BacktestRun, Bot, PaperAccount, PaperTrade, Portfolio, Post, Subscription, Thread, TradePost,
                          ValuationRun, Vote)

    secret = ("password_hash", "hashed_password", "key_hash", "token_hash")
    profile = {c.name: getattr(user, c.name) for c in User.__table__.columns if c.name not in secret}
    profile = {k: (v.isoformat() if isinstance(v, (dt.datetime, dt.date)) else v) for k, v in profile.items()}
    wls = [{**_wl(w), "created_at": w.created_at.isoformat() if getattr(w, "created_at", None) else None}
           for w in db.scalars(select(Watchlist).where(Watchlist.user_id == user.id))]
    return {
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(), "profile": profile, "watchlists": wls,
        "alerts": _rows(db, Alert, "user_id", user.id), "saved_screens": _rows(db, SavedScreen, "user_id", user.id),
        "api_keys": _rows(db, ApiKey, "user_id", user.id, drop=secret),
        "valuebot_reports": _rows(db, ValuationRun, "user_id", user.id),
        "lab_runs": _rows(db, BacktestRun, "user_id", user.id),
        "threads": _rows(db, Thread, "author_id", user.id), "posts": _rows(db, Post, "author_id", user.id),
        "trade_posts": _rows(db, TradePost, "author_id", user.id), "votes": _rows(db, Vote, "user_id", user.id),
        "subscriptions": _rows(db, Subscription, "user_id", user.id),
        "analyst_reports": _rows(db, AnalystReport, "user_id", user.id),
        "portfolios": [{"name": p.name, "source": p.source, "cash": p.cash, "benchmark": p.benchmark,
                        "holdings": [{"symbol": h.symbol, "quantity": h.quantity, "cost_basis": h.cost_basis} for h in p.holdings]}
                       for p in db.scalars(select(Portfolio).where(Portfolio.user_id == user.id))],
        "paper_accounts": _rows(db, PaperAccount, "user_id", user.id),
        "bots": _rows(db, Bot, "user_id", user.id, drop=("webhook_token",)),
        "paper_trades": [r for b in db.scalars(select(Bot.id).where(Bot.user_id == user.id)) for r in _rows(db, PaperTrade, "bot_id", b)],
    }


class DeleteIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    confirm: str


@router.post("/delete")
def delete_account(body: DeleteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Permanently delete the account and its private data. Cancels any Square subscription first."""
    from sqlalchemy import delete

    from ..models import Subscription, ValuationRun
    from ..payments.square import SquareClient, SquareConfig, SquareError
    from ..security import verify_password

    if body.confirm != "DELETE":
        raise HTTPException(400, 'Type DELETE to confirm')
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(403, "Password is incorrect")
    cfg = SquareConfig.from_env()
    for s in db.scalars(select(Subscription).where(Subscription.user_id == user.id, Subscription.provider == "square",
                                                   Subscription.status.in_(("active", "past_due", "pending")))):
        if s.provider_subscription_id and cfg.access_token:
            try:
                SquareClient(cfg).cancel_subscription(s.provider_subscription_id)
            except SquareError as e:
                raise HTTPException(502, f"Couldn't cancel your Square subscription ({e}). Nothing was deleted; please try again.")
    uid = user.id
    db.execute(delete(ValuationRun).where(ValuationRun.user_id == uid))  # reports are private: remove, don't orphan
    db.delete(user)
    db.commit()
    return {"ok": True}


# ── customization ────────────────────────────────────────────────────────────────────────────────
from typing import Literal  # noqa: E402

TICKER_TABS = Literal["summary", "analyst", "chart", "financials", "earnings", "dividends", "peers-ratios", "technicals", "filings", "news", "analysis", "preferreds"]
LANDINGS = Literal["/", "/terminal", "/research", "/monitor/adr", "/valuebot/reports", "/account", "/community", "/lab"]


class Preferences(BaseModel):
    theme: Literal["system", "light", "dark"] = "system"
    accent: Literal["solar", "ocean", "emerald", "violet", "mono"] = "solar"
    density: Literal["comfortable", "compact"] = "comfortable"
    landing: LANDINGS = "/"
    ticker_bar: list[str] = Field(default_factory=list, max_length=20)
    default_ticker_tab: TICKER_TABS = "summary"
    chart_range: Literal["1mo", "3mo", "6mo", "1y", "5y"] = "1y"
    benchmark: Literal["SPY", "QQQ", "IWM", "DIA", "ACWI", "VT"] = "SPY"
    show_tab_guides: bool = True
    show_ticker_bar: bool = True


@router.get("/preferences")
def get_preferences(user: User = Depends(current_user)):
    return Preferences(**(user.preferences or {})).model_dump()


@router.put("/preferences")
def put_preferences(body: Preferences, user: User = Depends(current_user), db: Session = Depends(get_db)):
    import re

    syms, seen = [], set()
    for s in body.ticker_bar:
        s = s.strip().upper()
        if re.match(r"^[A-Z0-9.\-=^]{1,20}$", s) and s not in seen:
            seen.add(s)
            syms.append(s)
    body.ticker_bar = syms
    user.preferences = body.model_dump()
    db.commit()
    return user.preferences
