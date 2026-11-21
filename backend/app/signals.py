"""IRAI Premium Signals: a daily, rules-based scan of the coverage universe.

Each signal is a factual technical or attention event (a trend cross, an RSI extreme, a 52-week breakout, an
unusual move, a buzz spike, an ADR dislocation), scored 0-100 for strength. Signals describe what happened;
they are not recommendations, and their history is kept so members can judge them.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .market import service
from .models import BuzzSnapshot, PremiumSignal

log = logging.getLogger("irai.signals")
CORE = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "ORCL", "AMD", "NFLX", "CRM",
        "JPM", "BAC", "WFC", "GS", "V", "MA", "BRK-B", "UNH", "JNJ", "LLY", "MRK", "PFE", "ABBV", "XOM", "CVX", "COP", "HD", "WMT",
        "COST", "PG", "KO", "PEP", "MCD", "NKE", "CAT", "GE", "BA", "HON", "VZ", "T", "NEE", "DIS", "TLT", "GLD", "XLE", "XLF", "XLK", "SMH"]
KINDS = {"golden_cross": "Golden cross", "death_cross": "Death cross", "rsi_oversold": "RSI oversold", "rsi_overbought": "RSI overbought",
         "breakout_high": "52-week high breakout", "breakdown_low": "52-week low breakdown", "unusual_move": "Unusual move",
         "buzz_spike": "Buzz spike", "adr_dislocation": "ADR dislocation"}
_lock = threading.Lock()


def _sma(xs: list[float], n: int, end: int | None = None) -> float | None:
    end = len(xs) if end is None else end
    return sum(xs[end - n:end]) / n if end >= n else None


def _rsi(xs: list[float], n: int = 14) -> float | None:
    if len(xs) <= n:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = xs[i] - xs[i - 1]
        gains, losses = gains + max(d, 0), losses + max(-d, 0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(xs)):
        d = xs[i] - xs[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def detect(symbol: str, closes: list[float], dates: list[str]) -> list[dict[str, Any]]:
    """Technical events on the latest bar (crosses within the last 3 bars)."""
    out: list[dict[str, Any]] = []
    if len(closes) < 60:
        return out
    px = closes[-1]
    if len(closes) >= 205:
        for back in range(0, 3):
            e = len(closes) - back
            s50, s200, p50, p200 = _sma(closes, 50, e), _sma(closes, 200, e), _sma(closes, 50, e - 1), _sma(closes, 200, e - 1)
            if None in (s50, s200, p50, p200):
                continue
            if p50 <= p200 and s50 > s200:
                out.append({"kind": "golden_cross", "direction": "bullish", "strength": 60 + min(30, abs(px / s200 - 1) * 300),
                            "title": f"{symbol}: 50-day average crossed above the 200-day", "data": {"sma50": s50, "sma200": s200, "bars_ago": back},
                            "detail": f"50-day {s50:.2f} vs 200-day {s200:.2f}, {back} trading day(s) ago. Price {px:.2f}."})
                break
            if p50 >= p200 and s50 < s200:
                out.append({"kind": "death_cross", "direction": "bearish", "strength": 60 + min(30, abs(px / s200 - 1) * 300),
                            "title": f"{symbol}: 50-day average crossed below the 200-day", "data": {"sma50": s50, "sma200": s200, "bars_ago": back},
                            "detail": f"50-day {s50:.2f} vs 200-day {s200:.2f}, {back} trading day(s) ago. Price {px:.2f}."})
                break
    r = _rsi(closes[-120:])
    if r is not None and (r < 30 or r > 70):
        low = r < 30
        out.append({"kind": "rsi_oversold" if low else "rsi_overbought", "direction": "bullish" if low else "bearish",
                    "strength": min(100, 50 + abs(r - 50) * 1.5), "title": f"{symbol}: 14-day RSI {'oversold' if low else 'overbought'} at {r:.0f}",
                    "detail": f"RSI {r:.1f}; readings below 30 or above 70 often mark stretched short-term moves.", "data": {"rsi14": r}})
    window = closes[-253:-1]
    if len(window) >= 200:
        hi, lo = max(window), min(window)
        if px > hi:
            out.append({"kind": "breakout_high", "direction": "bullish", "strength": 55 + min(40, (px / hi - 1) * 1000),
                        "title": f"{symbol}: closed at a new 52-week high", "detail": f"{px:.2f} vs prior 52-week high {hi:.2f}.", "data": {"prior_high": hi}})
        elif px < lo:
            out.append({"kind": "breakdown_low", "direction": "bearish", "strength": 55 + min(40, (1 - px / lo) * 1000),
                        "title": f"{symbol}: closed at a new 52-week low", "detail": f"{px:.2f} vs prior 52-week low {lo:.2f}.", "data": {"prior_low": lo}})
    rets = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - 60, len(closes)) if closes[i - 1]]
    if len(rets) > 30:
        sd = statistics.pstdev(rets[:-1])
        z = rets[-1] / sd if sd else 0
        if abs(z) >= 2.5:
            out.append({"kind": "unusual_move", "direction": "bullish" if z > 0 else "bearish", "strength": min(100, 40 + abs(z) * 12),
                        "title": f"{symbol}: {rets[-1]:+.1%} move, {abs(z):.1f} standard deviations",
                        "detail": f"Today's move is {abs(z):.1f}x the typical daily move of the past three months.", "data": {"z": z, "ret": rets[-1]}})
    for s in out:
        s["strength"] = round(max(0.0, min(100.0, s["strength"])), 1)
    return out


def scan(db: Session, universe: list[str] | None = None, day: str | None = None) -> dict[str, Any]:
    day = day or dt.date.today().isoformat()
    syms = universe or CORE

    def one(sym: str):
        try:
            c = service.chart(sym, "2y")
            h = [x for x in c["history"] if x.get("close")]
            sigs = detect(sym, [x["close"] for x in h], [x["date"] for x in h])
            for sg in sigs:
                sg.setdefault("data", {})["price"] = h[-1]["close"] if h else None
            return sym, sigs, c["quote"].get("source")
        except Exception as e:  # noqa: BLE001
            log.debug("signal scan %s failed: %s", sym, e)
            return sym, [], None

    with ThreadPoolExecutor(max_workers=4) as ex:
        found = list(ex.map(one, syms))
    rows: list[dict[str, Any]] = []
    for sym, sigs, src in found:
        for s in sigs:
            rows.append({**s, "symbol": sym, "data": {**(s.get("data") or {}), "data_label": src}})
    # attention: buzz spikes from the buzz scanner
    for b in db.scalars(select(BuzzSnapshot)):
        if (b.score or 0) >= 70:
            rows.append({"symbol": b.symbol, "kind": "buzz_spike", "direction": "neutral", "strength": round(float(b.score), 1),
                         "title": f"{b.symbol}: media attention {b.level.lower() if b.level else 'high'} ({b.score:.0f}/100)",
                         "detail": "News volume, filings and trading activity are well above normal. Attention is not direction.", "data": {"buzz": b.score}})
    # ADR dislocations from the continuous scanner
    try:
        from .routers.monitors import latest_scan, opportunity_score
        for r in latest_scan(db, max_age_minutes=24 * 60):
            sc = opportunity_score(r)
            if sc >= 2 and r.get("premium") is not None:
                prem = r["premium"]
                rows.append({"symbol": r.get("adr_symbol") or r.get("symbol"), "kind": "adr_dislocation", "direction": "bearish" if prem > 0 else "bullish",
                             "strength": round(min(100, 40 + sc * 12), 1),
                             "title": f"{r.get('adr_symbol')}: ADR {'premium' if prem > 0 else 'discount'} of {abs(prem):.1%} to its local line",
                             "detail": f"z-score {r.get('z') or 0:+.1f}, confidence {r.get('confidence') or 0:.0f}. Check FX, hours and the ratio before acting.",
                             "data": {"premium": prem, "z": r.get("z")}})
    except Exception:  # noqa: BLE001
        pass
    db.execute(delete(PremiumSignal).where(PremiumSignal.date == day))
    for s in rows:
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in [s["strength"]]):
            continue
        db.add(PremiumSignal(date=day, symbol=s["symbol"], kind=s["kind"], direction=s["direction"], strength=s["strength"],
                             title=s["title"][:160], detail=(s.get("detail") or "")[:600], data=s.get("data")))
    db.commit()
    return {"date": day, "signals": len(rows), "universe": len(syms)}


def due(db: Session, now_et: dt.datetime) -> bool:
    """After the US close on weekdays (16:20 ET), once per day; also on first start if there's nothing yet."""
    today = now_et.date().isoformat()
    has_today = db.scalar(select(PremiumSignal.id).where(PremiumSignal.date == today).limit(1)) is not None
    if has_today:
        return False
    any_signal = db.scalar(select(PremiumSignal.id).limit(1)) is not None
    return (now_et.weekday() < 5 and now_et.time() >= dt.time(16, 20)) or not any_signal


def start_background() -> bool:
    if _lock.locked():
        return False

    def run():
        with _lock, SessionLocal() as db:
            try:
                log.info("signals %s", scan(db))
            except Exception:  # noqa: BLE001
                log.exception("signal scan failed")

    threading.Thread(target=run, daemon=True, name="signals").start()
    return True
