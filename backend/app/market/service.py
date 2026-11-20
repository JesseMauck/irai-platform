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
from .source import DemoSource, MarketSource, SourceError, YahooSource, parallel

_lock = threading.Lock()
_mem: dict[tuple[str, str], tuple[float, Any]] = {}
_source: MarketSource | None = None
_demo = DemoSource()


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
    now = time.time()
    with _lock:
        hit = _mem.get((kind, key))
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    with _lock:
        _mem[(kind, key)] = (now, val)
    return val


def _persist(quote: dict[str, Any]) -> None:
    from ..models import QuoteCache

    try:
        with SessionLocal() as db:
            row = db.get(QuoteCache, quote["symbol"])
            if row is None:
                db.add(QuoteCache(symbol=quote["symbol"], payload=quote))
            else:
                row.payload = quote
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
                q["source"] = "STALE"
                q["fetched_at"] = row.fetched_at.isoformat() if row.fetched_at else None
                return q
    except Exception:  # noqa: BLE001
        pass
    return None


def normalise_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def chart(symbol: str, range_: str = "1y") -> dict[str, Any]:
    """{quote, history} for one symbol, with fallbacks. Raises SourceError only if nothing is available."""
    symbol = normalise_symbol(symbol)
    src = get_source()

    def fetch():
        try:
            data = src.chart(symbol, range_)
            if data["quote"].get("source") != "DEMO":
                _persist(data["quote"])
            return data
        except SourceError:
            if src is _demo:
                raise
            stored = _stored(symbol)
            if stored:
                return {"quote": stored, "history": []}
            if settings.demo_fallback:
                return _demo.chart(symbol, range_)
            raise

    ttl = settings.quote_ttl if range_ in ("1d", "5d") else min(settings.quote_ttl * 2, settings.history_ttl)
    return _cached("chart:" + range_, symbol, ttl, fetch)


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
            return {**src.info(symbol), "source": "DEMO" if src is _demo else "LIVE"}
        except SourceError:
            if src is not _demo and settings.demo_fallback:
                return {**_demo.info(symbol), "source": "DEMO"}
            raise

    return _cached("info", symbol, settings.info_ttl, fetch)


def search(q: str) -> list[dict[str, Any]]:
    q = q.strip()[:40]
    if not q:
        return []
    src = get_source()

    def fetch():
        try:
            return src.search(q)
        except SourceError:
            return _demo.search(q) if settings.demo_fallback else []

    return _cached("search", q.lower(), 3600, fetch)


def status() -> dict[str, Any]:
    src = get_source()
    return {"mode": settings.market_mode, "source": src.name, "demo_fallback": settings.demo_fallback,
            "cache_entries": len(_mem)}
