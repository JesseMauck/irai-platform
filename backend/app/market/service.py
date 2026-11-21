"""Market data service: one place that every page and engine reads prices from.

* Picks the live source (Yahoo) or demo source from IRAI_MARKET_MODE.
* Caches in memory (quotes ~30 s, history ~1 h, fundamentals ~6 h) and persists the latest quote per
  symbol to the `quotes` table so a restart, or a feed outage, still has a last-known price (served
  with source "STALE").
* If a live fetch fails and there is no stored quote, falls back to demo data labelled DEMO
  (IRAI_DEMO_FALLBACK=0 turns that off and returns an error instead).
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any

from ..config import settings
from ..db import SessionLocal
from .opendata import OpenDataSource
from .source import DemoSource, MarketSource, RateLimited, SourceError, YahooSource, parallel

_lock = threading.Lock()
_mem: dict[tuple[str, str], tuple[float, Any]] = {}
_inflight: dict[tuple[str, str], threading.Lock] = {}
_live_slots = threading.BoundedSemaphore(4)  # at most 4 concurrent requests to the live feed
FALLBACK_TTL = 60.0  # retry the live feed a minute after serving a stored/demo fallback

# Back-off when the feed rate-limits us: no live calls until _cooldown_until, doubling up to 10 minutes.
_cooldown_until = 0.0
_cooldown_s = 0.0
_COOLDOWN_MIN, _COOLDOWN_MAX = 30.0, 600.0


def _note_rate_limited() -> None:
    global _cooldown_until, _cooldown_s
    with _lock:
        _cooldown_s = min(_COOLDOWN_MAX, max(_COOLDOWN_MIN, _cooldown_s * 2))
        _cooldown_until = time.time() + _cooldown_s


def _note_live_ok() -> None:
    global _cooldown_s
    with _lock:
        _cooldown_s = 0.0


def cooling_down() -> bool:
    return time.time() < _cooldown_until


def _live_call(fn):
    """Run one live-feed call under the concurrency cap and circuit breaker."""
    if cooling_down():
        raise RateLimited("feed cooling down after rate limit")
    with _live_slots:
        try:
            out = fn()
        except RateLimited:
            _note_rate_limited()
            raise
    _note_live_ok()
    return out
_source: MarketSource | None = None
_demo = DemoSource()
_open = OpenDataSource()


def get_source() -> MarketSource:
    global _source
    if _source is None:
        _source = YahooSource() if settings.live else _demo
    return _source


def demo_source() -> DemoSource:
    return _demo


def set_source(src: MarketSource | None) -> None:
    """Swap the source (tests, or a licensed vendor feed later) and clear caches."""
    global _source
    _source = src
    with _lock:
        _mem.clear()


def _cached(kind: str, key: str, ttl: float, fn):
    """Memoise fn() for ttl seconds. Concurrent callers for the same key share one fetch.
    fn may return (value, ttl_override) via _Short to cache a fallback for less time."""
    k = (kind, key)

    def fresh():
        with _lock:
            hit = _mem.get(k)
        if hit and time.time() < hit[0]:
            return True, hit[1]
        return False, None

    ok, val = fresh()
    if ok:
        return val
    with _lock:
        gate = _inflight.setdefault(k, threading.Lock())
    with gate:
        ok, val = fresh()  # another caller may have filled it while we waited
        if ok:
            return val
        val = fn()
        life = ttl
        if isinstance(val, _Short):
            val, life = val.value, min(ttl, FALLBACK_TTL)
        with _lock:
            _mem[k] = (time.time() + life, val)
        return val


class _Short:
    """Wrapper marking a fallback value that should be cached briefly."""
    def __init__(self, value: Any):
        self.value = value


def _persist(quote: dict[str, Any], history: list[dict[str, Any]] | None = None) -> None:
    from ..models import QuoteCache

    try:
        with SessionLocal() as db:
            row = db.get(QuoteCache, quote["symbol"])
            payload = dict(quote)
            if history:
                payload["_history"] = history[-260:]  # ~1y of daily closes so charts survive outages
            elif row is not None and row.payload.get("_history"):
                payload["_history"] = row.payload["_history"]
            if row is None:
                db.add(QuoteCache(symbol=quote["symbol"], payload=payload, fetched_at=dt.datetime.now(dt.timezone.utc)))
            else:
                row.payload = payload
                row.fetched_at = dt.datetime.now(dt.timezone.utc)
            db.commit()
    except Exception:  # noqa: BLE001  (cache persistence must never break a request)
        pass


def _stored(symbol: str) -> dict[str, Any] | None:
    from ..models import QuoteCache

    try:
        with SessionLocal() as db:
            row = db.get(QuoteCache, symbol)
            if row:
                q = dict(row.payload)
                q.pop("_history", None)
                q["source"] = "STALE"
                q["fetched_at"] = row.fetched_at.isoformat() if row.fetched_at else None
                return q
    except Exception:  # noqa: BLE001
        pass
    return None


def _stored_history(symbol: str) -> list[dict[str, Any]]:
    from ..models import QuoteCache

    try:
        with SessionLocal() as db:
            row = db.get(QuoteCache, symbol)
            return list((row.payload or {}).get("_history") or []) if row else []
    except Exception:  # noqa: BLE001
        return []


def normalise_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def chart(symbol: str, range_: str = "1y") -> dict[str, Any]:
    """{quote, history} for one symbol, with fallbacks. Raises SourceError only if nothing is available."""
    symbol = normalise_symbol(symbol)
    src = get_source()

    def fetch():
        try:
            data = _live_call(lambda: src.chart(symbol, range_)) if src is not _demo else src.chart(symbol, range_)
            if data["quote"].get("source") != "DEMO":
                _persist(data["quote"], data["history"] if range_ == "1y" else None)
            return data
        except SourceError:
            if src is _demo:
                raise
            if settings.live and _open.supports(symbol):
                try:
                    data = _open.chart(symbol, range_)
                    _persist(data["quote"], data["history"])
                    return _Short(data)
                except SourceError:
                    pass
            stored = _stored(symbol)
            if stored:
                return _Short({"quote": stored, "history": _stored_history(symbol)})
            if settings.demo_fallback:
                return _Short(_demo.chart(symbol, range_))
            raise

    ttl = settings.quote_ttl if range_ in ("1d", "5d") else min(settings.quote_ttl * 2, settings.history_ttl)
    return _cached("chart:" + range_, symbol, ttl, fetch)


TIMEFRAMES = {"15m": ("60d", "15m"), "1h": ("730d", "60m"), "1d": ("10y", "1d"), "1wk": ("max", "1wk")}


def bars(symbol: str, timeframe: str = "1d") -> dict[str, Any]:
    """OHLCV bars with UTC timestamps for one timeframe: {"bars": [...], "source": LIVE|DEMO}. Never labels demo as live."""
    from .source import SourceError as _SE

    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {sorted(TIMEFRAMES)}")
    symbol = normalise_symbol(symbol)
    range_, interval = TIMEFRAMES[timeframe]
    src = get_source()

    def fetch():
        if src is _demo or not hasattr(src, "bars"):
            return {"bars": _demo.bars(symbol, range_, interval), "source": "DEMO"}
        try:
            b = _live_call(lambda: src.bars(symbol, range_, interval))
            if len(b) < 50:
                raise _SE(f"{symbol}: only {len(b)} bars")
            return {"bars": b, "source": "LIVE"}
        except _SE:
            if settings.demo_fallback:
                return _Short({"bars": _demo.bars(symbol, range_, interval), "source": "DEMO"})
            raise

    ttl = 900 if timeframe in ("15m", "1h") else 6 * 3600
    return _cached("bars:" + timeframe, symbol, ttl, fetch)


def quote(symbol: str) -> dict[str, Any]:
    return chart(symbol, "1y")["quote"]


def quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    res = parallel(quote, [normalise_symbol(s) for s in symbols])
    return {k: v for k, v in res.items() if not isinstance(v, Exception)}


def history(symbol: str, range_: str = "1y") -> list[dict[str, Any]]:
    return chart(symbol, range_)["history"]


def info(symbol: str) -> dict[str, Any]:
    symbol = normalise_symbol(symbol)
    src = get_source()

    def fetch():
        try:
            if src is _demo:
                return {**src.info(symbol), "source": "DEMO"}
            return {**_live_call(lambda: src.info(symbol)), "source": "LIVE"}
        except SourceError:
            if src is not _demo and settings.demo_fallback:
                return _Short({**_demo.info(symbol), "source": "DEMO"})
            raise

    return _cached("info", symbol, settings.info_ttl, fetch)


def search(q: str) -> list[dict[str, Any]]:
    q = q.strip()[:40]
    if not q:
        return []
    src = get_source()

    def fetch():
        try:
            return _live_call(lambda: src.search(q)) if src is not _demo else src.search(q)
        except SourceError:
            return _Short(_demo.search(q) if settings.demo_fallback else [])

    return _cached("search", q.lower(), 3600, fetch)


def status() -> dict[str, Any]:
    src = get_source()
    return {"mode": settings.market_mode, "source": src.name, "demo_fallback": settings.demo_fallback,
            "cache_entries": len(_mem), "cooling_down": cooling_down(),
            "cooldown_seconds_left": max(0, round(_cooldown_until - time.time()))}
