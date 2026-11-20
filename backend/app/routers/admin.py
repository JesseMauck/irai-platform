"""Admin console API: business metrics, users, articles, coverage and moderation. Admins only."""
from __future__ import annotations

import datetime as dt
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..market import service
from ..models import (AdrPair, Article, BacktestRun, EmailOutbox, EtfFund, ModerationLog, PeerGroup, PeerMember, Post,
                      Subscription, Thread, TradePost, User, ValuationRun)
from ..security import current_user, plans

router = APIRouter(prefix="/api/admin", tags=["admin"])
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,150}$")


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admins only")
    return user


@router.get("/stats")
def stats(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    by_plan = dict(db.execute(select(User.plan, func.count()).group_by(User.plan)).all())
    subs = db.execute(select(Subscription.plan, Subscription.interval, Subscription.status, func.count())
                      .where(Subscription.status.in_(["trialing", "active", "past_due"]))
                      .group_by(Subscription.plan, Subscription.interval, Subscription.status)).all()
    p = plans()
    mrr = sum(n * (p[pl]["annual"] / 12 if iv == "annual" else p[pl]["monthly"]) for pl, iv, st, n in subs if st == "active")
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    return {
        "users": {"total": sum(by_plan.values()), "by_plan": by_plan,
                  "new_30d": db.scalar(select(func.count()).select_from(User).where(User.created_at >= since)) or 0},
        "subscriptions": [{"plan": a, "interval": b, "status": c, "count": n} for a, b, c, n in subs],
        "mrr_active": mrr,
        "valuebot_runs_30d": db.scalar(select(func.count()).select_from(ValuationRun).where(ValuationRun.created_at >= since)) or 0,
        "backtests_30d": db.scalar(select(func.count()).select_from(BacktestRun).where(BacktestRun.created_at >= since)) or 0,
        "threads": db.scalar(select(func.count()).select_from(Thread)) or 0,
        "trades": db.scalar(select(func.count()).select_from(TradePost)) or 0,
        "outbox": dict(db.execute(select(EmailOutbox.status, func.count()).group_by(EmailOutbox.status)).all()),
        "market": service.status(),
    }


# ── users ─────────────────────────────────────────────────────────────────────────────────────────
@router.get("/users")
def users(q: str = "", _: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(User).order_by(User.created_at.desc()).limit(100)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.email).like(like), func.lower(User.handle).like(like)))
    return [{"id": u.id, "email": u.email, "handle": u.handle, "display_name": u.display_name, "plan": u.plan,
             "is_admin": u.is_admin, "disabled": u.disabled, "verified_trader": u.verified_trader,
             "created_at": u.created_at.isoformat() if u.created_at else None} for u in db.scalars(stmt)]


class UserPatch(BaseModel):
    plan: str | None = None
    disabled: bool | None = None
    verified_trader: bool | None = None
    is_admin: bool | None = None


@router.patch("/users/{uid}")
def patch_user(uid: int, body: UserPatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404)
    if body.plan is not None:
        if body.plan not in plans():
            raise HTTPException(422, "Unknown plan")
        u.plan = body.plan
    if body.disabled is not None:
        if u.id == admin.id and body.disabled:
            raise HTTPException(409, "You can't disable your own account")
        u.disabled = body.disabled
        if body.disabled:
            u.tokens_valid_after = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    if body.verified_trader is not None:
        u.verified_trader = body.verified_trader
    if body.is_admin is not None:
        if u.id == admin.id and not body.is_admin:
            raise HTTPException(409, "You can't remove your own admin rights")
        u.is_admin = body.is_admin
    db.commit()
    return {"ok": True}


# ── articles ──────────────────────────────────────────────────────────────────────────────────────
class ArticleIn(BaseModel):
    slug: str
    title: str = Field(min_length=5, max_length=200)
    category: str
    tickers: list[str] = Field(default_factory=list, max_length=12)
    summary: str = Field(min_length=10, max_length=600)
    body_md: str = Field(min_length=20)
    author: str = Field(min_length=2, max_length=80)
    read_minutes: int = Field(5, ge=1, le=90)
    premium: bool = False
    published_at: dt.date | None = None


def _check_article(body: ArticleIn) -> None:
    if not SLUG_RE.match(body.slug):
        raise HTTPException(422, "slug: lowercase letters, digits and hyphens")
    if body.category not in ("ADR", "ETF", "Fundamental", "Methodology"):
        raise HTTPException(422, "category must be ADR, ETF, Fundamental or Methodology")


def _published(d: dt.date | None) -> dt.datetime:
    d = d or dt.date.today()
    return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)


@router.get("/articles")
def list_articles(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [{"id": a.id, "slug": a.slug, "title": a.title, "category": a.category, "tickers": a.tickers, "summary": a.summary,
             "body_md": a.body_md, "author": a.author, "read_minutes": a.read_minutes, "premium": a.premium,
             "published_at": a.published_at.date().isoformat() if a.published_at else None}
            for a in db.scalars(select(Article).order_by(Article.published_at.desc()))]


@router.post("/articles")
def create_article(body: ArticleIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    _check_article(body)
    if db.scalar(select(Article).where(Article.slug == body.slug)):
        raise HTTPException(409, "Slug already used")
    a = Article(**{**body.model_dump(exclude={"published_at"}), "tickers": [t.upper() for t in body.tickers]},
                published_at=_published(body.published_at))
    db.add(a)
    db.commit()
    return {"id": a.id}


@router.put("/articles/{aid}")
def update_article(aid: int, body: ArticleIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    _check_article(body)
    a = db.get(Article, aid)
    if not a:
        raise HTTPException(404)
    clash = db.scalar(select(Article).where(Article.slug == body.slug, Article.id != aid))
    if clash:
        raise HTTPException(409, "Slug already used")
    for k, v in body.model_dump(exclude={"published_at"}).items():
        setattr(a, k, [t.upper() for t in v] if k == "tickers" else v)
    a.published_at = _published(body.published_at)
    db.commit()
    return {"ok": True}


@router.delete("/articles/{aid}")
def delete_article(aid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    a = db.get(Article, aid)
    if not a:
        raise HTTPException(404)
    db.delete(a)
    db.commit()
    return {"ok": True}


# ── coverage ──────────────────────────────────────────────────────────────────────────────────────
class AdrIn(BaseModel):
    adr_symbol: str = Field(min_length=1, max_length=20)
    local_symbol: str = Field(min_length=1, max_length=20)
    name: str
    country: str
    local_currency: str = Field(min_length=3, max_length=3)
    ratio: float = Field(gt=0, le=10000)
    shortable_local: bool = True
    round_trip_cost_bps: float = Field(35, ge=0, le=1000)
    active: bool = True


@router.get("/coverage")
def coverage(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {
        "adr_pairs": [{c.name: getattr(p, c.name) for c in AdrPair.__table__.columns if c.name != "created_at"}
                      for p in db.scalars(select(AdrPair).order_by(AdrPair.id))],
        "etf_funds": [{"symbol": f.symbol, "name": f.name, "category": f.category, "active": f.active}
                      for f in db.scalars(select(EtfFund))],
        "peer_groups": [{"id": g.id, "name": g.name, "sector": g.sector,
                         "members": [{"id": m.id, "symbol": m.symbol, "name": m.name} for m in g.members]}
                        for g in db.scalars(select(PeerGroup).order_by(PeerGroup.id))],
    }


@router.put("/coverage/adr")
def upsert_adr(body: AdrIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    data = {**body.model_dump(), "adr_symbol": body.adr_symbol.upper(), "local_symbol": body.local_symbol.upper(),
            "local_currency": body.local_currency.upper()}
    p = db.scalar(select(AdrPair).where(AdrPair.adr_symbol == data["adr_symbol"]))
    if p:
        for k, v in data.items():
            setattr(p, k, v)
    else:
        db.add(AdrPair(**data))
    db.commit()
    return {"ok": True}


class EtfIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    name: str
    category: str
    active: bool = True


@router.put("/coverage/etf")
def upsert_etf(body: EtfIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    f = db.get(EtfFund, body.symbol.upper())
    if f:
        f.name, f.category, f.active = body.name, body.category, body.active
    else:
        db.add(EtfFund(symbol=body.symbol.upper(), name=body.name, category=body.category, active=body.active))
    db.commit()
    return {"ok": True}


class PeerIn(BaseModel):
    group: str = Field(min_length=2, max_length=80)
    sector: str = "Other"
    symbol: str = Field(min_length=1, max_length=20)
    name: str


@router.post("/coverage/peers")
def add_peer(body: PeerIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    g = db.scalar(select(PeerGroup).where(PeerGroup.name == body.group))
    if not g:
        g = PeerGroup(name=body.group, sector=body.sector)
        db.add(g)
        db.flush()
    if any(m.symbol == body.symbol.upper() for m in g.members):
        raise HTTPException(409, "Already in the group")
    db.add(PeerMember(group_id=g.id, symbol=body.symbol.upper(), name=body.name))
    db.commit()
    return {"ok": True}


@router.delete("/coverage/peers/{member_id}")
def remove_peer(member_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    m = db.get(PeerMember, member_id)
    if not m:
        raise HTTPException(404)
    db.delete(m)
    db.commit()
    return {"ok": True}


# ── moderation ────────────────────────────────────────────────────────────────────────────────────
class ModerateIn(BaseModel):
    action: str  # hide | unhide
    reason: str = Field(min_length=3, max_length=300)


MODELS = {"thread": Thread, "post": Post, "trade": TradePost}


@router.post("/moderate/{target_type}/{target_id}")
def moderate(target_type: str, target_id: int, body: ModerateIn, admin: User = Depends(require_admin),
             db: Session = Depends(get_db)):
    model = MODELS.get(target_type)
    if not model or body.action not in ("hide", "unhide"):
        raise HTTPException(422, "target_type thread|post|trade, action hide|unhide")
    obj = db.get(model, target_id)
    if not obj:
        raise HTTPException(404)
    obj.hidden = body.action == "hide"
    db.add(ModerationLog(moderator_id=admin.id, target_type=target_type, target_id=target_id, action=body.action,
                         reason=body.reason))
    db.commit()
    return {"ok": True, "hidden": obj.hidden}


@router.get("/moderation-log")
def moderation_log(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [{"id": m.id, "target_type": m.target_type, "target_id": m.target_id, "action": m.action, "reason": m.reason,
             "created_at": m.created_at.isoformat()}
            for m in db.scalars(select(ModerationLog).order_by(ModerationLog.id.desc()).limit(200))]


# ── payments (Square) ─────────────────────────────────────────────────────────────────────────────
@router.get("/billing/square")
def square_status(_: User = Depends(require_admin)):
    """What is configured, without revealing any secret."""
    from ..payments.square import SquareConfig
    cfg = SquareConfig.from_env()
    out = {"token_set": bool(cfg.access_token), "environment": cfg.environment, "location_id": cfg.location_id or None,
           "plans": {k: bool(v) for k, v in cfg.plan_variations.items()},
           "webhook_signature_key_set": bool(cfg.webhook_signature_key), "webhook_url": cfg.webhook_url or None,
           "expected_webhook_url": f"{settings_public_api()}/api/billing/webhook/square",
           "webhook_events": ["subscription.created", "subscription.updated"]}
    out["ready"] = out["token_set"] and bool(cfg.location_id) and all(out["plans"].values()) and out["webhook_signature_key_set"]
    return out


def settings_public_api() -> str:
    import os
    return os.environ.get("PUBLIC_API_URL", "https://api.irradiance.ai")


def _square():
    from ..payments.square import SquareClient, SquareConfig
    cfg = SquareConfig.from_env()
    if not cfg.access_token:
        raise HTTPException(409, "Set SQUARE_ACCESS_TOKEN on the API service first")
    return SquareClient(cfg)


@router.get("/billing/square/locations")
def square_locations(_: User = Depends(require_admin)):
    from ..payments.square import SquareError
    try:
        return [{"id": loc["id"], "name": loc.get("name"), "status": loc.get("status"), "currency": loc.get("currency")}
                for loc in _square().list_locations()]
    except SquareError as e:
        raise HTTPException(502, f"Square: {e}")


@router.post("/billing/square/setup")
def square_setup(_: User = Depends(require_admin)):
    """Create the membership plan + 4 variations in Square from plans.json prices. Returns the variation IDs to
    set as SQUARE_PLAN_* (they are identifiers, not secrets). Refuses to run twice once plans are configured."""
    from ..payments.square import SquareError
    sq = _square()
    if all(sq.cfg.plan_variations.values()):
        raise HTTPException(409, "Square plans are already configured")
    p = plans()
    prices = {f"{k}_monthly": int(p[k]["monthly"] * 100) for k in ("essential", "pro")}
    prices.update({f"{k}_annual": int(p[k]["annual"] * 100) for k in ("essential", "pro")})
    try:
        ids = sq.create_plans(prices)
    except SquareError as e:
        raise HTTPException(502, f"Square: {e}")
    return {"variables": {f"SQUARE_PLAN_{k.upper()}": v for k, v in ids.items()}}
