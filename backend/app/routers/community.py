"""Forum, trade feed (entry prices captured from live data, immutable) and leaderboards."""
from __future__ import annotations

import datetime as dt
import statistics

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..market import service
from ..market.source import SourceError
from ..models import Community, Post, Thread, TradePost, User, Vote
from ..security import current_user, limits

router = APIRouter(prefix="/api/community", tags=["community"])


def _can_post(user: User) -> None:
    if not limits(user)["post"]:
        raise HTTPException(402, "Posting needs the Essential plan")


def _thread(t: Thread) -> dict:
    return {"id": t.id, "title": t.title, "community": t.community.name, "community_slug": t.community.slug,
            "author": t.author.handle, "score": t.score, "replies": t.reply_count, "tickers": t.tickers,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "last_activity_at": t.last_activity_at.isoformat() if t.last_activity_at else None}


def _trade(t: TradePost) -> dict:
    return {"id": t.id, "author": t.author.handle, "long": t.long_symbol, "short": t.short_symbol, "thesis": t.thesis,
            "entry_long": t.entry_long, "entry_short": t.entry_short, "entry_source": t.entry_source,
            "verification": t.verification, "status": t.status, "exit_long": t.exit_long, "exit_short": t.exit_short,
            "return_pct": t.return_pct, "score": t.score,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "closed_at": t.closed_at.isoformat() if t.closed_at else None}


@router.get("/communities")
def communities(db: Session = Depends(get_db)):
    out = []
    for c in db.scalars(select(Community).order_by(Community.id)):
        n = db.scalar(select(func.count()).select_from(Thread).where(Thread.community_id == c.id)) or 0
        out.append({"slug": c.slug, "name": c.name, "description": c.description, "members": c.member_count,
                    "threads": n, "pro_only": c.pro_only})
    return out


@router.get("/threads")
def threads(community: str | None = None, db: Session = Depends(get_db)):
    q = select(Thread).join(Community).order_by(Thread.last_activity_at.desc()).limit(50)
    if community:
        q = q.where(Community.slug == community)
    return [_thread(t) for t in db.scalars(q)]


class ThreadIn(BaseModel):
    community: str
    title: str = Field(min_length=5, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    tickers: list[str] = Field(default_factory=list, max_length=10)


@router.post("/threads")
def create_thread(body: ThreadIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _can_post(user)
    c = db.scalar(select(Community).where(Community.slug == body.community))
    if not c:
        raise HTTPException(404, "No such community")
    if c.pro_only and user.plan != "pro":
        raise HTTPException(402, "Pro room")
    t = Thread(community_id=c.id, author_id=user.id, title=body.title.strip(), body_md=body.body,
               tickers=[s.upper()[:20] for s in body.tickers])
    db.add(t)
    db.commit()
    return _thread(t)


@router.get("/threads/{thread_id}")
def get_thread(thread_id: int, db: Session = Depends(get_db)):
    t = db.get(Thread, thread_id)
    if not t:
        raise HTTPException(404)
    posts = db.scalars(select(Post).where(Post.thread_id == t.id).order_by(Post.created_at)).all()
    return {**_thread(t), "body": t.body_md,
            "posts": [{"id": p.id, "author": p.author.handle, "body": p.body_md,
                       "created_at": p.created_at.isoformat() if p.created_at else None} for p in posts]}


class PostIn(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


@router.post("/threads/{thread_id}/posts")
def reply(thread_id: int, body: PostIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _can_post(user)
    t = db.get(Thread, thread_id)
    if not t:
        raise HTTPException(404)
    p = Post(thread_id=t.id, author_id=user.id, body_md=body.body)
    t.reply_count += 1
    t.last_activity_at = dt.datetime.now(dt.timezone.utc)
    db.add(p)
    db.commit()
    return {"id": p.id}


class VoteIn(BaseModel):
    value: int = Field(ge=-1, le=1)


@router.post("/{target_type}/{target_id}/vote")
def vote(target_type: str, target_id: int, body: VoteIn, user: User = Depends(current_user),
         db: Session = Depends(get_db)):
    _can_post(user)
    model = {"threads": Thread, "trades": TradePost}.get(target_type)
    if not model:
        raise HTTPException(404)
    obj = db.get(model, target_id)
    if not obj:
        raise HTTPException(404)
    kind = target_type[:-1]
    v = db.scalar(select(Vote).where(Vote.user_id == user.id, Vote.target_type == kind, Vote.target_id == target_id))
    old = v.value if v else 0
    if v:
        v.value = body.value
    else:
        db.add(Vote(user_id=user.id, target_type=kind, target_id=target_id, value=body.value))
    obj.score += body.value - old
    db.commit()
    return {"score": obj.score}


# ── trades ────────────────────────────────────────────────────────────────────────────────────────
@router.get("/trades")
def trades(status: str | None = None, db: Session = Depends(get_db)):
    q = select(TradePost).order_by(TradePost.created_at.desc()).limit(100)
    if status in ("open", "closed"):
        q = q.where(TradePost.status == status)
    return [_trade(t) for t in db.scalars(q)]


class TradeIn(BaseModel):
    long: str = Field(min_length=1, max_length=20)
    short: str | None = Field(None, max_length=20)
    thesis: str = Field(min_length=10, max_length=2000)


def _live_price(sym: str) -> tuple[float, str]:
    try:
        q = service.quote(sym)
    except SourceError as e:
        raise HTTPException(422, f"No price for {sym}: {e}")
    return q["price"], q.get("source", "LIVE")


@router.post("/trades")
def create_trade(body: TradeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Entry prices come from the market feed at this moment, not from the user."""
    _can_post(user)
    long_px, src = _live_price(body.long.upper())
    short_px, src2 = (_live_price(body.short.upper()) if body.short else (None, src))
    source = "DEMO" if "DEMO" in (src, src2) else ("STALE" if "STALE" in (src, src2) else "LIVE")
    t = TradePost(author_id=user.id, long_symbol=body.long.upper(), short_symbol=body.short.upper() if body.short else None,
                  thesis=body.thesis, entry_long=long_px, entry_short=short_px, entry_source=source,
                  verification="timestamp-verified" if source == "LIVE" else "self-reported")
    db.add(t)
    db.commit()
    return _trade(t)


@router.post("/trades/{trade_id}/close")
def close_trade(trade_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.get(TradePost, trade_id)
    if not t:
        raise HTTPException(404)
    if t.author_id != user.id:
        raise HTTPException(403, "Only the author can close a trade")
    if t.status == "closed":
        raise HTTPException(409, "Already closed")
    t.exit_long, _ = _live_price(t.long_symbol)
    ret = t.exit_long / t.entry_long - 1
    if t.short_symbol:
        t.exit_short, _ = _live_price(t.short_symbol)
        ret -= t.exit_short / t.entry_short - 1
    t.return_pct, t.status, t.closed_at = ret, "closed", dt.datetime.now(dt.timezone.utc)
    db.commit()
    return _trade(t)


@router.get("/leaderboard")
def leaderboard(min_trades: int | None = None, db: Session = Depends(get_db)):
    """Risk-adjusted score = mean return / stdev of returns, over verified closed trades only."""
    need = settings.leaderboard_min_trades if min_trades is None else max(1, min_trades)
    closed = db.scalars(select(TradePost).where(TradePost.status == "closed",
                                                TradePost.verification.in_(["timestamp-verified", "broker-verified"]))).all()
    by: dict[int, list[TradePost]] = {}
    for t in closed:
        by.setdefault(t.author_id, []).append(t)
    rows = []
    for uid, ts in by.items():
        if len(ts) < need:
            continue
        rets = [t.return_pct for t in ts if t.return_pct is not None]
        sd = statistics.pstdev(rets) if len(rets) > 1 else 0
        u = ts[0].author
        rows.append({"handle": u.handle, "name": u.display_name, "verification": ts[0].verification,
                     "closed_trades": len(ts), "win_rate": sum(r > 0 for r in rets) / len(rets),
                     "avg_return": statistics.mean(rets), "risk_adjusted": statistics.mean(rets) / sd if sd else None})
    rows.sort(key=lambda r: -(r["risk_adjusted"] or -1e9))
    return {"min_trades": need, "rows": [{"rank": i + 1, **r} for i, r in enumerate(rows)]}
