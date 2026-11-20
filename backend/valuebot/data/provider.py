"""Single entry point that assembles a company snapshot from all data sources."""
from __future__ import annotations

import copy
import os
import threading
import time
from typing import Any

from ..config import settings
from . import fixtures

# Short-lived cache: the company preview, thesis draft and the job itself all need the same snapshot,
# and SEC/Yahoo rate-limit. TTL in seconds via VALUEBOT_SNAPSHOT_TTL (0 disables).
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


def _ttl() -> float:
    try:
        return float(os.environ.get("VALUEBOT_SNAPSHOT_TTL", "900"))
    except ValueError:
        return 900.0


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def search(query: str) -> list[dict[str, Any]]:
    if settings.offline:
        return fixtures.search(query)
    from . import sec

    try:
        hits = sec.search(query)
    except Exception:  # noqa: BLE001
        hits = []
    # Demo tickers are always available so people can try the app without data access.
    return hits + fixtures.search(query)


def snapshot(ticker: str, log=lambda msg: None) -> dict[str, Any]:
    """Return the company snapshot used by every downstream stage (cached for a few minutes)."""
    t = ticker.upper().strip()
    if settings.offline or t in fixtures.FIXTURES:
        return fixtures.get(t)
    ttl = _ttl()
    with _CACHE_LOCK:
        hit = _CACHE.get(t)
    if hit and ttl > 0 and time.time() - hit[0] < ttl:
        log("Using cached market data and filings")
        return copy.deepcopy(hit[1])
    snap = _live_snapshot(t, log)
    with _CACHE_LOCK:
        _CACHE[t] = (time.time(), snap)
    return copy.deepcopy(snap)


def _live_snapshot(t: str, log) -> dict[str, Any]:

    from . import market, sec

    log("Fetching market data")
    q = market.quote(t)
    sources = [q["source"]]

    log("Fetching SEC filings")
    try:
        fin = sec.fetch_financials(t)
    except LookupError:
        log("Not an SEC filer; using Yahoo Finance statements")
        fin = market.financials_fallback(t)
    sources.append(fin["source"])
    if not fin["history"]:
        raise LookupError(f"No financial statements found for {t}")

    rf, rf_src = market.riskfree_rate()
    sources.append({"label": rf_src, "url": "https://finance.yahoo.com/quote/%5ETNX"})

    shares = q.get("shares_outstanding") or fin.get("shares_outstanding")
    if not shares:
        raise LookupError(f"Could not determine shares outstanding for {t}")
    if q.get("financial_currency") and q["financial_currency"] != q["currency"]:
        # Statements and price in different currencies (common for ADRs); flag it.
        sources.append({"label": f"Warning: statements in {q['financial_currency']}, price in {q['currency']}", "url": None})

    return {
        "ticker": t,
        "name": fin.get("name") or q["name"],
        "cik": fin.get("cik"),
        "sector": q.get("sector") or fin.get("sic_description"),
        "industry": q.get("industry") or fin.get("sic_description"),
        "country": q.get("country"),
        "currency": q.get("currency", "USD"),
        "price": q["price"],
        "shares": shares,
        "market_cap": q.get("market_cap") or q["price"] * shares,
        "beta": q.get("beta"),
        "summary": q.get("summary"),
        "dividend_rate": q.get("dividend_rate"),
        "payout_ratio": q.get("payout_ratio"),
        "consensus": q.get("consensus", {}),
        "history": fin["history"],
        "filings": fin.get("filings", []),
        "news": market.news(t),
        "riskfree": rf,
        "riskfree_source": rf_src,
        "sources": sources + [{"label": f"{f['form']} filed {f['date']}", "url": f["url"]} for f in fin.get("filings", [])[:5]],
        "demo": False,
    }
