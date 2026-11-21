"""Congress Trading and Smart Money Trackers endpoints."""
from __future__ import annotations

import datetime as dt
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..market import service
from ..models import CongressTrade, DisclosureDoc, Filing13F, User
from ..security import PLAN_ORDER, optional_user

router = APIRouter(prefix="/api", tags=["disclosures"])
NOTE_CONGRESS = ("Members of Congress must disclose trades over $1,000 within 45 days (STOCK Act). Sizes are reported as ranges. "
                 "Price change since the trade uses daily closes and the trade date, not the actual fill. Research and education only.")
NOTE_13F = ("13F reports are filed up to 45 days after each quarter and show long US-listed positions on the last day of the quarter. "
            "They don't show shorts, most non-US holdings, or trades made since. Research and education only.")
_cache: dict[str, tuple[float, Any]] = {}
_busy: set[str] = set()


def _pro(u: User | None) -> bool:
    return bool(u) and (PLAN_ORDER.get(u.plan, 0) >= PLAN_ORDER["pro"] or bool(getattr(u, "is_admin", False)))


def _closes(sym: str) -> dict[str, float]:
    try:
        return {h["date"]: h["close"] for h in service.chart(sym, "2y")["history"] if h.get("close")}
    except Exception:  # noqa: BLE001
        return {}


def _px_on(closes: dict[str, float], d: dt.date | None, after_days: int = 0) -> float | None:
    if not closes or not d:
        return None
    target = (d + dt.timedelta(days=after_days)).isoformat()
    for k in sorted(closes):
        if k >= target:
            return closes[k]
    return None


def _moves(trades: list[CongressTrade]) -> dict[int, dict[str, float | None]]:
    syms = sorted({t.ticker for t in trades if t.ticker})
    with ThreadPoolExecutor(max_workers=8) as ex:
        hist = dict(zip(syms, ex.map(_closes, syms)))
    out = {}
    for t in trades:
        h = hist.get(t.ticker or "", {})
        p0 = _px_on(h, t.traded)
        last = h[max(h)] if h else None
        p30 = _px_on(h, t.traded, 30)
        sign = -1 if t.tx_type.startswith("sell") else 1
        out[t.id] = {"since": (last / p0 - 1) if p0 and last else None, "after_30d": (p30 / p0 - 1) if p0 and p30 and t.traded and (dt.date.today() - t.traded).days >= 30 else None,
                     "sign": sign}
    return out


def _row(t: CongressTrade, mv: dict[str, Any] | None = None) -> dict[str, Any]:
    lag = (t.filed - t.traded).days if t.filed and t.traded else None
    return {"id": t.id, "chamber": t.chamber, "member": t.member, "party": t.party, "state": t.state, "district": t.district, "owner": t.owner,
            "ticker": t.ticker, "asset": t.asset, "asset_type": t.asset_type, "type": t.tx_type, "amount": t.amount, "amount_low": t.amount_low,
            "amount_high": t.amount_high, "traded": t.traded.isoformat() if t.traded else None, "filed": t.filed.isoformat() if t.filed else None,
            "disclosure_lag_days": lag, "url": t.url, **({"price_change_since": mv.get("since"), "after_30d": mv.get("after_30d")} if mv else {})}


@router.get("/congress/trades")
def congress_trades(symbol: str | None = Query(None, max_length=16), member: str | None = Query(None, max_length=80), chamber: str | None = Query(None, pattern="^(house|senate)$"),
                    party: str | None = Query(None, pattern="^(Democrat|Republican|Independent)$"), type: str | None = Query(None, pattern="^(buy|sell)$"),
                    min_amount: float | None = None, stocks_only: bool = True, page: int = Query(1, ge=1, le=200), per: int = Query(50, ge=10, le=100),
                    user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    q = select(CongressTrade)
    if symbol:
        q = q.where(CongressTrade.ticker == symbol.upper().replace(".", "-"))
    if member:
        q = q.where(CongressTrade.member.ilike(f"%{member}%"))
    if chamber:
        q = q.where(CongressTrade.chamber == chamber)
    if party:
        q = q.where(CongressTrade.party == party)
    if type:
        q = q.where(CongressTrade.tx_type.like(f"{type}%"))
    if min_amount:
        q = q.where(CongressTrade.amount_low >= min_amount)
    if stocks_only:
        q = q.where(CongressTrade.ticker.is_not(None))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    pro = _pro(user)
    lim = per if pro else min(per, 15)
    if not pro:
        page = 1
    rows = db.scalars(q.order_by(CongressTrade.traded.desc().nullslast(), CongressTrade.filed.desc(), CongressTrade.id).offset((page - 1) * lim).limit(lim)).all()
    mv = _moves(rows)
    last = db.scalar(select(func.max(DisclosureDoc.processed_at)))
    return {"trades": [_row(t, mv.get(t.id)) for t in rows], "total": total, "page": page, "per": lim, "locked": not pro,
            "hidden": max(0, (total or 0) - lim) if not pro else 0, "updated_at": last.isoformat() if last else None, "note": NOTE_CONGRESS,
            "source": "LIVE" if last else None, "provider": {"label": "U.S. House Clerk financial disclosures and Senate eFD", "url": "https://disclosures-clerk.house.gov/FinancialDisclosure"}}


def _summary(db: Session) -> dict[str, Any]:
    since = dt.date.today() - dt.timedelta(days=365)
    rows = db.scalars(select(CongressTrade).where(CongressTrade.ticker.is_not(None), or_(CongressTrade.traded >= since, CongressTrade.traded.is_(None)))).all()
    d30 = dt.date.today() - dt.timedelta(days=30)
    mid = lambda t: ((t.amount_low or 0) + (t.amount_high or t.amount_low or 0)) / 2  # noqa: E731
    by_t: dict[str, dict[str, Any]] = defaultdict(lambda: {"buys": 0, "sells": 0, "members": set(), "volume": 0.0})
    by_m: dict[str, dict[str, Any]] = defaultdict(lambda: {"trades": 0, "buys": 0, "sells": 0, "volume": 0.0, "party": None, "chamber": None, "state": None, "last": None, "rows": []})
    for t in rows:
        b = t.tx_type == "buy"
        x = by_t[t.ticker]
        x["buys" if b else "sells"] += 1
        x["members"].add(t.member)
        x["volume"] += mid(t)
        m = by_m[t.member]
        m["trades"] += 1
        m["buys" if b else "sells"] += 1
        m["volume"] += mid(t)
        m.update(party=t.party, chamber=t.chamber, state=t.state)
        if t.traded and (not m["last"] or t.traded > m["last"]):
            m["last"] = t.traded
        m["rows"].append(t)
    top_members = sorted(by_m.items(), key=lambda kv: -kv[1]["volume"])[:25]
    scored = [t for _, m in top_members for t in sorted(m["rows"], key=lambda r: r.traded or dt.date.min, reverse=True)[:12]]
    recent = sorted([t for t in rows if t.traded and t.traded >= dt.date.today() - dt.timedelta(days=210)], key=lambda r: r.traded, reverse=True)[:350]
    mv = _moves(list({t.id: t for t in scored + recent}.values()))
    leaders = []
    for name, m in top_members:
        ch = [mv[t.id]["since"] * mv[t.id]["sign"] for t in m["rows"] if t.id in mv and mv[t.id]["since"] is not None]
        leaders.append({"member": name, "party": m["party"], "chamber": m["chamber"], "state": m["state"], "trades": m["trades"], "buys": m["buys"], "sells": m["sells"],
                        "est_volume": m["volume"], "last_trade": m["last"].isoformat() if m["last"] else None,
                        "avg_directional_move": sum(ch) / len(ch) if ch else None, "scored_trades": len(ch)})
    big = []
    for t in recent:
        a = mv.get(t.id, {}).get("after_30d")
        if a is not None and a * mv[t.id]["sign"] >= 0.15:
            big.append({**_row(t), "move_30d": a, "directional_move_30d": a * mv[t.id]["sign"]})
    big.sort(key=lambda r: -r["directional_move_30d"])
    notable = sorted([t for t in rows if t.traded and t.traded >= d30 - dt.timedelta(days=30)], key=lambda t: (-(t.amount_low or 0), t.traded), reverse=False)[:12]
    return {"period_days": 365, "trades": len(rows), "trades_30d": sum(1 for t in rows if t.traded and t.traded >= d30),
            "buys": sum(1 for t in rows if t.tx_type == "buy"), "sells": sum(1 for t in rows if t.tx_type.startswith("sell")),
            "members": len(by_m), "most_traded": sorted([{"ticker": k, "buys": v["buys"], "sells": v["sells"], "members": len(v["members"]), "est_volume": v["volume"]}
                                                        for k, v in by_t.items()], key=lambda r: -(r["buys"] + r["sells"]))[:15],
            "leaderboard": leaders, "large_moves_after_trade": big[:20], "notable": [_row(t) for t in notable],
            "computed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "note": NOTE_CONGRESS,
            "method": "Directional move = price change since the trade date for buys, and its opposite for sells, averaged over each member's recent "
                      "trades with a ticker. Large moves = trades followed within 30 days by a 15%+ move in the traded direction. These are "
                      "descriptive statistics; they do not imply anything about any member's knowledge or intent."}


def _cached(key: str, ttl: float, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    if hit:  # serve stale, refresh in the background
        if key not in _busy:
            _busy.add(key)

            def go():
                try:
                    with SessionLocal() as db:
                        _cache[key] = (time.time(), fn(db))
                finally:
                    _busy.discard(key)
            threading.Thread(target=go, daemon=True).start()
        return hit[1]
    with SessionLocal() as db:
        val = fn(db)
    _cache[key] = (time.time(), val)
    return val


@router.get("/congress/summary")
def congress_summary(user: User | None = Depends(optional_user)):
    s = _cached("congress:summary", 3 * 3600, _summary)
    if not _pro(user):
        return {**s, "leaderboard": s["leaderboard"][:5], "large_moves_after_trade": s["large_moves_after_trade"][:3], "locked": True}
    return {**s, "locked": False}


# ── smart money ──────────────────────────────────────────────────────────────────────────────────
def _fund_card(db: Session, key: str) -> dict[str, Any] | None:
    from ..disclosures import thirteenf as tf

    cur, prev = tf.latest_pair(db, key)
    if not cur:
        return None
    meta = tf.FUNDS[key]
    top = next((h for h in cur.holdings if h.get("put_call") is None), cur.holdings[0] if cur.holdings else None)
    stale = (dt.date.today() - cur.period).days > 200
    return {"key": key, **{k: meta[k] for k in ("manager", "fund", "style")}, "cik": meta["cik"], "period": cur.period.isoformat(), "filed": cur.filed.isoformat(),
            "aum_13f": cur.total_value, "positions": cur.positions, "prev_aum_13f": prev.total_value if prev else None,
            "top_holding": {"ticker": top.get("ticker"), "name": top["name"], "weight": top.get("weight")} if top else None,
            "top5_weight": sum(h.get("weight") or 0 for h in cur.holdings[:5]), "stale": stale,
            "sec_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={meta['cik']}&type=13F-HR"}


@router.get("/smart-money/funds")
def smart_funds(db: Session = Depends(get_db)):
    from ..disclosures import thirteenf as tf

    cards = [c for c in (_fund_card(db, k) for k in tf.FUNDS) if c]
    cards.sort(key=lambda c: (c["stale"], -c["aum_13f"]))
    return {"funds": cards, "note": NOTE_13F, "provider": {"label": "SEC EDGAR Form 13F-HR", "url": "https://www.sec.gov/edgar/search/"},
            "tracked": len(tf.FUNDS), "loaded": len(cards)}


@router.get("/smart-money/funds/{key}")
def smart_fund(key: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    from ..disclosures import thirteenf as tf

    if key not in tf.FUNDS:
        raise HTTPException(404, "Unknown fund")
    card = _fund_card(db, key)
    if not card:
        raise HTTPException(404, "This fund's filings haven't been loaded yet")
    cur, prev = tf.latest_pair(db, key)
    rows = tf.compare(cur, prev)
    pro = _pro(user)
    eq = [r for r in rows if not r.get("put_call")]
    buys = sorted([r for r in eq if r["status"] in ("new", "added")], key=lambda r: -(r["value"] - (r.get("prev_weight") or 0) * cur.total_value))[:10]
    sells = sorted([r for r in eq if r["status"] in ("reduced", "sold_out")], key=lambda r: (r.get("weight") or 0) - (r.get("prev_weight") or 0))[:10]
    return {**card, "holdings": rows if pro else rows[:10], "hidden": 0 if pro else max(0, len(rows) - 10), "locked": not pro,
            "top_buys": buys if pro else buys[:3], "top_sells": sells if pro else sells[:3],
            "counts": Counter(r["status"] for r in eq), "prev_period": prev.period.isoformat() if prev else None, "note": NOTE_13F}


def _consensus(db: Session) -> dict[str, Any]:
    from ..disclosures import thirteenf as tf

    agg: dict[str, dict[str, Any]] = defaultdict(lambda: {"holders": [], "value": 0.0, "new": [], "added": [], "reduced": [], "sold_out": [], "name": None})
    periods = Counter()
    for k in tf.FUNDS:
        cur, prev = tf.latest_pair(db, k)
        if not cur or (dt.date.today() - cur.period).days > 200:
            continue
        periods[cur.period.isoformat()] += 1
        for r in tf.compare(cur, prev):
            if r.get("put_call") or not r.get("ticker"):
                continue
            a = agg[r["ticker"]]
            a["name"] = a["name"] or r["name"]
            if r["status"] != "sold_out":
                a["holders"].append({"fund": k, "manager": tf.FUNDS[k]["manager"], "weight": r.get("weight"), "value": r["value"]})
                a["value"] += r["value"]
            if r["status"] in ("new", "added", "reduced", "sold_out"):
                a[r["status"]].append(tf.FUNDS[k]["fund"])
    rows = [{"ticker": t, "name": a["name"], "holders": len(a["holders"]), "value": a["value"], "new": a["new"], "added": a["added"], "reduced": a["reduced"],
             "sold_out": a["sold_out"], "net_buyers": len(a["new"]) + len(a["added"]) - len(a["reduced"]) - len(a["sold_out"]),
             "top_holders": sorted(a["holders"], key=lambda h: -(h["weight"] or 0))[:5]} for t, a in agg.items()]
    return {"most_held": sorted(rows, key=lambda r: (-r["holders"], -r["value"]))[:25], "most_bought": sorted(rows, key=lambda r: -r["net_buyers"])[:20],
            "most_sold": sorted(rows, key=lambda r: r["net_buyers"])[:20], "new_positions": sorted([r for r in rows if r["new"]], key=lambda r: -len(r["new"]))[:20],
            "period": periods.most_common(1)[0][0] if periods else None, "by_ticker": {r["ticker"]: r for r in rows}}


@router.get("/smart-money/consensus")
def smart_consensus(user: User | None = Depends(optional_user)):
    c = _cached("13f:consensus", 6 * 3600, _consensus)
    out = {k: v for k, v in c.items() if k != "by_ticker"}
    if not _pro(user):
        out = {**out, **{k: v[:5] for k, v in out.items() if isinstance(v, list)}, "locked": True}
    return {**out, "note": NOTE_13F}


@router.get("/smart-money/symbol/{symbol}")
def smart_symbol(symbol: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    sym = symbol.upper().replace(".", "-")
    c = _cached("13f:consensus", 6 * 3600, _consensus)
    r = c["by_ticker"].get(sym)
    trades = db.scalars(select(CongressTrade).where(CongressTrade.ticker == sym).order_by(CongressTrade.traded.desc()).limit(10)).all()
    return {"symbol": sym, "smart_money": r, "congress": [_row(t) for t in trades], "period": c.get("period"), "note": NOTE_13F}
