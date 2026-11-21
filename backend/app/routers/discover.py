"""Discover: IRAI Premium Signals, Earnings Hub, market heatmap, macro map, options explorer, and the member's
Library and History. Every response carries its data label and source."""
from __future__ import annotations

import datetime as dt
import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import research, signals
from ..config import settings
from ..db import get_db
from ..market import service
from ..models import (AnalystReport, AssistantChat, BacktestRun, Bot, BotSignal, PaperTrade, Pin, Portfolio, PremiumSignal, SavedScreen,
                      StrategyListing, User, ValuationRun, Watchlist)
from ..security import PLAN_ORDER, current_user, optional_user

router = APIRouter(prefix="/api", tags=["discover"])
YAHOO = {"label": "Yahoo Finance", "url": "https://finance.yahoo.com"}


def _label() -> str:
    return "LIVE" if settings.live else "DEMO"


def _is_pro(u: User | None) -> bool:
    return bool(u and PLAN_ORDER.get(u.plan, 0) >= PLAN_ORDER["pro"])


# ── Premium Signals ──────────────────────────────────────────────────────────────────────────────
def _sig_out(s: PremiumSignal, now_px: float | None = None) -> dict:
    at = (s.data or {}).get("price")
    return {"id": s.id, "date": s.date, "symbol": s.symbol, "kind": s.kind, "kind_label": signals.KINDS.get(s.kind, s.kind),
            "direction": s.direction, "strength": s.strength, "title": s.title, "detail": s.detail, "price_at_signal": at,
            "since_signal": (now_px / at - 1) if now_px and at else None}


@router.get("/signals")
def premium_signals(kind: str | None = None, direction: str | None = None, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    day = db.scalar(select(func.max(PremiumSignal.date)))
    if not day:
        return {"date": None, "signals": [], "kinds": signals.KINDS, "locked": 0, "pro": _is_pro(user),
                "note": "The first scan runs after the US close."}
    q = select(PremiumSignal).where(PremiumSignal.date == day)
    if kind in signals.KINDS:
        q = q.where(PremiumSignal.kind == kind)
    if direction in ("bullish", "bearish", "neutral"):
        q = q.where(PremiumSignal.direction == direction)
    rows = db.scalars(q.order_by(PremiumSignal.strength.desc())).all()
    counts: dict[str, int] = {}
    for r in db.scalars(select(PremiumSignal).where(PremiumSignal.date == day)):
        counts[r.kind] = counts.get(r.kind, 0) + 1
    pro = _is_pro(user)
    shown = rows if pro else rows[:3]
    return {"date": day, "signals": [_sig_out(s) for s in shown], "locked": 0 if pro else max(0, len(rows) - 3), "counts": counts,
            "kinds": signals.KINDS, "pro": pro, "universe": len(signals.CORE),
            "method": "Rules-based scan after each US close: 50/200-day crosses (last 3 days), 14-day RSI below 30 or above 70, "
                      "52-week highs and lows, moves of 2.5+ standard deviations, buzz scores of 70+, and ADR dislocations.",
            "provider": {"label": "Computed by Irradiance from market data (Yahoo Finance) and the Irradiance buzz and ADR scanners"}}


@router.get("/signals/track-record")
def signal_track_record(days: int = 30, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """How past signals have moved since they fired (price at signal vs now). Pro only."""
    if not _is_pro(user):
        raise HTTPException(402, "Signal history is part of Pro")
    since = (dt.date.today() - dt.timedelta(days=min(max(days, 1), 120))).isoformat()
    rows = db.scalars(select(PremiumSignal).where(PremiumSignal.date >= since).order_by(PremiumSignal.date.desc()).limit(400)).all()
    px = service.quotes(sorted({r.symbol for r in rows})) if rows else {}
    out = [_sig_out(r, (px.get(r.symbol) or {}).get("price")) for r in rows]
    by_kind: dict[str, list[float]] = {}
    for o in out:
        if o["since_signal"] is not None and o["direction"] != "neutral":
            signed = o["since_signal"] if o["direction"] == "bullish" else -o["since_signal"]
            by_kind.setdefault(o["kind"], []).append(signed)
    summary = {k: {"label": signals.KINDS[k], "count": len(v), "hit_rate": sum(1 for x in v if x > 0) / len(v), "avg_move_in_direction": statistics.fmean(v)}
               for k, v in by_kind.items() if v}
    return {"signals": out, "summary": summary, "since": since,
            "note": "Moves are measured from the close on the signal day to the latest price, in the signal's direction. Past signals don't predict future ones."}


@router.get("/signals/{symbol}")
def symbol_signals(symbol: str, db: Session = Depends(get_db)):
    rows = db.scalars(select(PremiumSignal).where(PremiumSignal.symbol == symbol.upper()).order_by(PremiumSignal.date.desc()).limit(30)).all()
    return [_sig_out(r) for r in rows]


# ── Earnings Hub ─────────────────────────────────────────────────────────────────────────────────
def _earn_dates(sym: str) -> list[dict]:
    def fetch():
        if not settings.live:
            return []
        from ..fundamentals import _clean, _ticker
        try:
            ed = _ticker(sym).get_earnings_dates(limit=8)
        except Exception:  # noqa: BLE001
            return []
        out = []
        if ed is not None and not ed.empty:
            for d, r in ed.iterrows():
                est, act = _clean(r.get("EPS Estimate")), _clean(r.get("Reported EPS"))
                out.append({"date": d.date().isoformat(), "time": d.strftime("%H:%M"), "eps_estimate": est, "eps_actual": act,
                            "surprise_pct": _clean(r.get("Surprise(%)"))})
        return out
    return research._memo("earn_dates", sym, 12 * 3600, fetch)


@router.get("/discover/earnings")
def earnings_hub(user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    mine: list[str] = []
    if user:
        for w in db.scalars(select(Watchlist).where(Watchlist.user_id == user.id)):
            mine += [i.symbol.upper() for i in (w.items or [])]
        for p in db.scalars(select(Portfolio).where(Portfolio.user_id == user.id)):
            mine += [h.symbol for h in p.holdings]
    universe = list(dict.fromkeys([*mine, *[s for s in signals.CORE if s not in ("SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "XLE", "XLF", "XLK", "SMH")]]))[:90]
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = dict(zip(universe, ex.map(_earn_dates, universe)))
    today = dt.date.today()
    upcoming, recent = [], []
    for sym, rows in res.items():
        for r in rows:
            d = dt.date.fromisoformat(r["date"])
            row = {"symbol": sym, "mine": sym in mine, **r}
            if r["eps_actual"] is None and today <= d <= today + dt.timedelta(days=45):
                upcoming.append(row)
            elif r["eps_actual"] is not None and today - dt.timedelta(days=21) <= d <= today:
                recent.append(row)
    upcoming.sort(key=lambda r: (r["date"], r["symbol"]))
    recent.sort(key=lambda r: r["date"], reverse=True)
    beats = [r for r in recent if (r.get("surprise_pct") or 0) > 0]
    return {"upcoming": upcoming, "recent": recent, "tracked": len(universe), "mine": sorted(set(mine)),
            "beat_rate": len(beats) / len(recent) if recent else None, "source": _label(),
            "provider": {"label": "Earnings dates and EPS (Yahoo Finance)", "url": YAHOO["url"]}, "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
            "note": None if settings.live else "Earnings dates need live mode."}


# ── Heatmap ──────────────────────────────────────────────────────────────────────────────────────
HEAT_EXTRA = ["ADBE", "INTC", "QCOM", "TXN", "CSCO", "IBM", "PYPL", "UBER", "SHOP", "PLTR", "C", "MS", "SCHW", "BLK", "AXP", "TMO",
              "ABT", "DHR", "AMGN", "BMY", "GILD", "ISRG", "SLB", "EOG", "OXY", "LOW", "TGT", "SBUX", "BKNG", "PM", "MO", "CL", "MDLZ",
              "UPS", "RTX", "LMT", "DE", "UNP", "LIN", "SHW", "PLD", "AMT", "EQIX", "DUK", "SO", "CMCSA", "TMUS", "CHTR"]


@router.get("/discover/heatmap")
def heatmap(period: str = "1d"):
    syms = [s for s in signals.CORE if s not in ("SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "XLE", "XLF", "XLK", "SMH")] + HEAT_EXTRA

    def one(sym: str):
        try:
            info = service.info(sym)
        except Exception:  # noqa: BLE001
            info = {}
        ret = None
        if period != "1d":
            try:
                c = service.chart(sym, "1y")
                rr = research._returns(c["history"])
                ret = {"1m": rr.get("1m"), "3m": rr.get("3m"), "1y": rr.get("12m")}.get(period)
            except Exception:  # noqa: BLE001
                pass
        return sym, info, ret

    q = service.quotes(syms)
    with ThreadPoolExecutor(max_workers=4) as ex:
        loaded = list(ex.map(one, syms))
    tiles = []
    for sym, info, ret in loaded:
        qq = q.get(sym) or {}
        if not qq.get("price"):
            continue
        tiles.append({"symbol": sym, "name": info.get("name") or qq.get("name"), "sector": info.get("sector") or "Other",
                      "market_cap": info.get("market_cap") or 0, "change": qq.get("change_pct") if period == "1d" else ret,
                      "price": qq.get("price"), "source": qq.get("source")})
    sectors: dict[str, dict] = {}
    for t in tiles:
        s = sectors.setdefault(t["sector"], {"sector": t["sector"], "market_cap": 0.0, "tiles": []})
        s["market_cap"] += t["market_cap"] or 0
        s["tiles"].append(t)
    for s in sectors.values():
        caps = [(t["market_cap"] or 0, t["change"]) for t in s["tiles"] if t["change"] is not None]
        tot = sum(c for c, _ in caps)
        s["change"] = sum(c * ch for c, ch in caps) / tot if tot else None
        s["tiles"].sort(key=lambda t: -(t["market_cap"] or 0))
    return {"period": period, "sectors": sorted(sectors.values(), key=lambda s: -s["market_cap"]), "count": len(tiles), "source": _label(),
            "provider": {"label": "Quotes and market caps (Yahoo Finance); sized by market cap", "url": YAHOO["url"]},
            "as_of": dt.datetime.now(dt.timezone.utc).isoformat()}


# ── Macro map ────────────────────────────────────────────────────────────────────────────────────
MACRO = {
    "Americas": [("^GSPC", "United States", "S&P 500", "US"), ("^IXIC", "United States", "Nasdaq", "US"), ("^GSPTSE", "Canada", "TSX", "CA"),
                 ("^MXX", "Mexico", "IPC", "MX"), ("^BVSP", "Brazil", "Bovespa", "BR")],
    "Europe": [("^FTSE", "United Kingdom", "FTSE 100", "GB"), ("^GDAXI", "Germany", "DAX", "DE"), ("^FCHI", "France", "CAC 40", "FR"),
               ("^STOXX50E", "Euro area", "Euro Stoxx 50", "EU"), ("^SSMI", "Switzerland", "SMI", "CH")],
    "Asia-Pacific": [("^N225", "Japan", "Nikkei 225", "JP"), ("^HSI", "Hong Kong", "Hang Seng", "HK"), ("000001.SS", "China", "Shanghai Comp.", "CN"),
                     ("^KS11", "South Korea", "KOSPI", "KR"), ("^TWII", "Taiwan", "TAIEX", "TW"), ("^BSESN", "India", "Sensex", "IN"), ("^AXJO", "Australia", "ASX 200", "AU")],
}
MACRO_OTHER = {
    "Rates": [("^IRX", "US 3-month bill"), ("^FVX", "US 5-year"), ("^TNX", "US 10-year"), ("^TYX", "US 30-year")],
    "Currencies": [("DX-Y.NYB", "US dollar index"), ("EURUSD=X", "EUR/USD"), ("GBPUSD=X", "GBP/USD"), ("USDJPY=X", "USD/JPY"), ("USDCNY=X", "USD/CNY"),
                   ("USDINR=X", "USD/INR"), ("USDBRL=X", "USD/BRL"), ("USDMXN=X", "USD/MXN")],
    "Commodities": [("CL=F", "WTI crude"), ("BZ=F", "Brent crude"), ("NG=F", "Natural gas"), ("GC=F", "Gold"), ("SI=F", "Silver"), ("HG=F", "Copper")],
    "Risk": [("^VIX", "VIX volatility"), ("BTC-USD", "Bitcoin"), ("ETH-USD", "Ether"), ("HYG", "High-yield bonds"), ("TLT", "Long Treasuries")],
}


@router.get("/discover/macro")
def macro():
    def one(sym: str):
        try:
            c = service.chart(sym, "1y")
            rr = research._returns(c["history"])
            return sym, c["quote"], rr, [h["close"] for h in c["history"][-60:] if h.get("close")]
        except Exception:  # noqa: BLE001
            return sym, None, {}, []

    allsyms = [x[0] for v in MACRO.values() for x in v] + [x[0] for v in MACRO_OTHER.values() for x in v]
    with ThreadPoolExecutor(max_workers=4) as ex:
        got = {s: (q, rr, sp) for s, q, rr, sp in ex.map(one, allsyms)}

    def row(sym, label, extra=None):
        q, rr, sp = got.get(sym, (None, {}, []))
        return {"symbol": sym, "label": label, **(extra or {}), "price": (q or {}).get("price"), "change_pct": (q or {}).get("change_pct"),
                "ret_1m": rr.get("1m"), "ret_ytd": None, "ret_1y": rr.get("12m"), "source": (q or {}).get("source"), "spark": sp[::2]}

    regions = [{"region": r, "markets": [row(s, idx, {"country": c, "code": code}) for s, c, idx, code in v]} for r, v in MACRO.items()]
    groups = [{"group": g, "items": [row(s, lab) for s, lab in v]} for g, v in MACRO_OTHER.items()]
    for reg in regions:
        ch = [m["change_pct"] for m in reg["markets"] if m["change_pct"] is not None]
        reg["avg_change"] = statistics.fmean(ch) if ch else None
    return {"regions": regions, "groups": groups, "source": _label(), "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
            "provider": {"label": "Index, rate, FX and futures quotes (Yahoo Finance); some exchanges delayed 15-20 minutes", "url": YAHOO["url"]}}


# ── Options explorer ─────────────────────────────────────────────────────────────────────────────
def _f(v: Any) -> float | None:
    try:
        x = float(v)
        return None if math.isnan(x) or math.isinf(x) else x
    except (TypeError, ValueError):
        return None


@router.get("/discover/options/{symbol}")
def options(symbol: str, expiry: str | None = None):
    sym = service.normalise_symbol(symbol.upper())
    if not settings.live:
        return {"symbol": sym, "expiries": [], "calls": [], "puts": [], "source": "DEMO", "note": "Options chains need live mode."}

    def fetch():
        from ..fundamentals import _ticker
        t = _ticker(sym)
        exps = list(t.options or [])
        if not exps:
            return {"expiries": []}
        e = expiry if expiry in exps else exps[0]
        ch = t.option_chain(e)

        def rows(df):
            out = []
            for _, r in df.iterrows():
                out.append({"contract": r.get("contractSymbol"), "strike": _f(r.get("strike")), "last": _f(r.get("lastPrice")), "bid": _f(r.get("bid")),
                            "ask": _f(r.get("ask")), "change_pct": (_f(r.get("percentChange")) or 0) / 100, "volume": _f(r.get("volume")) or 0,
                            "open_interest": _f(r.get("openInterest")) or 0, "iv": _f(r.get("impliedVolatility")), "itm": bool(r.get("inTheMoney"))})
            return out
        return {"expiries": exps[:24], "expiry": e, "calls": rows(ch.calls), "puts": rows(ch.puts)}

    try:
        data = research._memo("options", f"{sym}:{expiry}", 600, fetch)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Options data unavailable: {type(e).__name__}")
    if not data.get("expiries"):
        return {"symbol": sym, "expiries": [], "calls": [], "puts": [], "source": _label(), "note": f"No listed options found for {sym}."}
    q = service.quote(sym)
    px = q.get("price")
    calls, puts = data["calls"], data["puts"]
    cv, pv = sum(c["volume"] for c in calls), sum(p["volume"] for p in puts)
    coi, poi = sum(c["open_interest"] for c in calls), sum(p["open_interest"] for p in puts)
    atm = min(calls, key=lambda c: abs((c["strike"] or 0) - (px or 0))) if calls and px else None
    atm_put = next((p for p in puts if atm and p["strike"] == atm["strike"]), None)

    def mid(o):
        return ((o["bid"] or 0) + (o["ask"] or 0)) / 2 if o and o.get("bid") and o.get("ask") else (o or {}).get("last")

    straddle = (mid(atm) or 0) + (mid(atm_put) or 0) if atm and atm_put else None
    strikes = sorted({o["strike"] for o in calls + puts if o["strike"] is not None})
    pain = None
    if strikes:
        def payout(k):
            return sum(max(0, k - c["strike"]) * c["open_interest"] for c in calls if c["strike"] is not None) + \
                   sum(max(0, p["strike"] - k) * p["open_interest"] for p in puts if p["strike"] is not None)
        pain = min(strikes, key=payout)
    unusual = sorted([{**o, "type": t} for t, lst in (("call", calls), ("put", puts)) for o in lst
                      if o["volume"] >= 500 and o["volume"] > max(o["open_interest"], 1)], key=lambda o: -o["volume"])[:15]
    days = max(1, (dt.date.fromisoformat(data["expiry"]) - dt.date.today()).days)
    return {"symbol": sym, "price": px, "price_source": q.get("source"), "expiries": data["expiries"], "expiry": data["expiry"], "days_to_expiry": days,
            "calls": calls, "puts": puts,
            "summary": {"put_call_volume": pv / cv if cv else None, "put_call_oi": poi / coi if coi else None, "call_volume": cv, "put_volume": pv,
                        "atm_strike": atm["strike"] if atm else None, "atm_iv": atm["iv"] if atm else None,
                        "expected_move": straddle, "expected_move_pct": straddle / px if straddle and px else None, "max_pain": pain},
            "unusual": unusual, "source": _label(), "provider": {"label": "Options chains (Yahoo Finance, delayed)", "url": f"https://finance.yahoo.com/quote/{sym}/options"},
            "note": "Expected move uses the at-the-money straddle mid price. Max pain is the strike where option holders' total payout at expiry is lowest."}


# ── Library and History ──────────────────────────────────────────────────────────────────────────
@router.get("/me/library")
def library(user: User = Depends(current_user), db: Session = Depends(get_db)):
    vr = db.scalars(select(ValuationRun).where(ValuationRun.user_id == user.id, ValuationRun.archived.is_not(True)).order_by(ValuationRun.created_at.desc()).limit(30)).all()
    ar = db.scalars(select(AnalystReport).where(AnalystReport.user_id == user.id, AnalystReport.status == "done").order_by(AnalystReport.created_at.desc()).limit(30)).all()
    return {
        "valuations": [{"id": v.job_id, "ticker": v.ticker, "title": v.title or v.ticker, "value_per_share": v.value_per_share, "price": v.price,
                        "pinned": v.pinned, "created_at": v.created_at.isoformat() if v.created_at else None} for v in vr],
        "analyst_reports": [{"id": r.id, "symbol": r.symbol, "headline": ((r.result or {}).get("analysis") or {}).get("headline"),
                             "created_at": r.created_at.isoformat() if r.created_at else None} for r in ar],
        "pins": [{"kind": p.kind, "ref": p.ref} for p in db.scalars(select(Pin).where(Pin.user_id == user.id).order_by(Pin.id.desc()).limit(50))],
        "screens": [{"id": s.id, "name": s.name} for s in db.scalars(select(SavedScreen).where(SavedScreen.user_id == user.id))],
        "backtests": [{"id": b.id, "symbol": b.symbol, "strategy": b.strategy, "kind": getattr(b, "kind", "backtest"),
                       "return": (b.statistics or {}).get("return"), "created_at": b.created_at.isoformat() if b.created_at else None}
                      for b in db.scalars(select(BacktestRun).where(BacktestRun.user_id == user.id).order_by(BacktestRun.created_at.desc()).limit(20))],
        "chats": [{"id": c.id, "title": c.title, "updated_at": c.updated_at.isoformat()} for c in db.scalars(select(AssistantChat).where(AssistantChat.user_id == user.id).order_by(AssistantChat.updated_at.desc()).limit(20))],
        "listings": [{"id": x.id, "title": x.title, "copies": x.copies} for x in db.scalars(select(StrategyListing).where(StrategyListing.author_id == user.id, StrategyListing.status == "active"))],
    }


@router.get("/me/history")
def history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ev: list[dict[str, Any]] = []
    for v in db.scalars(select(ValuationRun).where(ValuationRun.user_id == user.id).order_by(ValuationRun.created_at.desc()).limit(40)):
        ev.append({"at": v.created_at, "kind": "valuation", "title": f"ValueBot: {v.ticker}", "href": f"/valuebot/{v.job_id}"})
    for r in db.scalars(select(AnalystReport).where(AnalystReport.user_id == user.id).order_by(AnalystReport.created_at.desc()).limit(40)):
        ev.append({"at": r.created_at, "kind": "analyst", "title": f"Analyst Bot: {r.symbol}", "href": f"/ticker/{r.symbol}#analyst"})
    for b in db.scalars(select(BacktestRun).where(BacktestRun.user_id == user.id).order_by(BacktestRun.created_at.desc()).limit(40)):
        ev.append({"at": b.created_at, "kind": "lab", "title": f"{'Monte Carlo' if getattr(b, 'kind', '') == 'montecarlo' else 'Backtest'}: {b.symbol} {b.strategy or ''}".strip(), "href": "/lab"})
    for c in db.scalars(select(AssistantChat).where(AssistantChat.user_id == user.id).order_by(AssistantChat.updated_at.desc()).limit(40)):
        ev.append({"at": c.updated_at, "kind": "chat", "title": f"Ask IRAI: {c.title}", "href": f"#chat-{c.id}", "chat_id": c.id})
    bots = {b.id: b.name for b in db.scalars(select(Bot).where(Bot.user_id == user.id))}
    if bots:
        for t in db.scalars(select(PaperTrade).where(PaperTrade.bot_id.in_(list(bots))).order_by(PaperTrade.created_at.desc()).limit(80)):
            ev.append({"at": t.created_at, "kind": "trade", "title": f"{bots[t.bot_id]}: {t.side} {t.quantity:,.2f} {t.symbol} @ {t.price:,.2f}",
                       "detail": t.reason, "href": f"/bots/{t.bot_id}"})
        for s in db.scalars(select(BotSignal).where(BotSignal.bot_id.in_(list(bots)), BotSignal.source == "webhook").order_by(BotSignal.created_at.desc()).limit(40)):
            ev.append({"at": s.created_at, "kind": "signal", "title": f"{bots[s.bot_id]}: webhook {s.action} {s.symbol or ''}", "detail": s.status, "href": f"/bots/{s.bot_id}"})
    for e in ev:
        a = e["at"]
        e["at"] = (a.replace(tzinfo=dt.timezone.utc) if a and a.tzinfo is None else a).isoformat() if a else None
    ev.sort(key=lambda e: e["at"] or "", reverse=True)
    return ev[:200]
