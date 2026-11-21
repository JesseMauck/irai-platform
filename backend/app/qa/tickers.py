"""Ticker sampler: random coverage symbols (least-recently-tested first), a targeted edge-case pool, and
regression rechecks of tickers attached to open issues."""
from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import QaIssue, QaTickerLedger


@dataclass(frozen=True)
class Pick:
    symbol: str
    kind: str  # universe | edge | regression
    tag: str = ""  # edge-case tag; tells the trader what behavior to expect
    expect: str = "ok"  # ok | reject (4xx expected, never 5xx) | any (either is acceptable; 5xx never is)


# Edge cases that liquid large-caps never hit. `expect` is what correct behavior looks like.
EDGE_POOL: list[Pick] = [
    Pick("BRK.B", "edge", "share_class_dot"), Pick("BRK-B", "edge", "share_class_dash"), Pick("BF.B", "edge", "share_class_dot"),
    Pick("brk.b", "edge", "lowercase"), Pick("^GSPC", "edge", "index"), Pick("^VIX", "edge", "index"),
    Pick("EURUSD=X", "edge", "fx"), Pick("USDJPY=X", "edge", "fx"), Pick("BTC-USD", "edge", "crypto"), Pick("ETH-USD", "edge", "crypto"),
    Pick("TCEHY", "edge", "otc_adr"), Pick("NSRGY", "edge", "otc_adr"), Pick("SIRI", "edge", "low_price"),
    Pick("GME", "edge", "high_volatility"), Pick("AMC", "edge", "high_volatility"), Pick("BRK.A", "edge", "high_price"),
    Pick("NVR", "edge", "high_price"), Pick("TWTR", "edge", "delisted", "any"), Pick("SIVB", "edge", "delisted", "any"),
    Pick("FRC", "edge", "delisted", "any"), Pick("ZZZZZZ", "edge", "nonexistent", "any"), Pick("QQQQQ", "edge", "nonexistent", "any"),
    Pick("AAPL$", "edge", "bad_charset", "reject"), Pick("A" * 21, "edge", "too_long", "reject"),
    Pick("AA PL", "edge", "whitespace", "reject"),
]
FALLBACK_UNIVERSE = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "JPM", "XOM", "KO", "PFE", "DIS",
                     "T", "INTC", "BA", "NKE", "COST", "TLT", "GLD", "XLE", "XLF", "SMH", "BABA", "TSM", "ASML", "SHOP", "PLTR"]


def universe(db: Session) -> list[str]:
    from .. import signals
    from ..jobs import coverage_symbols

    syms = list(coverage_symbols(db)) + list(signals.CORE)
    out, seen = [], set()
    for s in syms + FALLBACK_UNIVERSE:
        if s and s not in seen and not s.endswith("=X") and not s.startswith("^"):
            seen.add(s)
            out.append(s)
    return out


def sample(db: Session, n: int, rng: random.Random | None = None) -> list[Pick]:
    """~60% universe (preferring least-recently tested), ~25% edge pool, ~15% regression rechecks."""
    rng = rng or random.Random()
    n_reg = max(0, round(n * 0.15))
    n_edge = max(1, round(n * 0.25)) if n >= 2 else 0
    picks: list[Pick] = []

    open_issues = db.scalars(select(QaIssue).where(QaIssue.status.in_(["new", "valid", "regressed", "needs_more_data"]))
                             .order_by(QaIssue.last_seen.desc()).limit(50)).all()
    reg = list(dict.fromkeys(t for i in open_issues for t in (i.tickers or [])[-3:]))
    rng.shuffle(reg)
    edge_by_sym = {p.symbol: p for p in EDGE_POOL}
    for s in reg[:n_reg]:
        e = edge_by_sym.get(s)
        picks.append(Pick(s, "regression", e.tag if e else "", e.expect if e else "ok"))

    picks += rng.sample(EDGE_POOL, min(n_edge, len(EDGE_POOL)))

    taken = {p.symbol for p in picks}
    ledger = {r.symbol: r.last_tested_at for r in db.scalars(select(QaTickerLedger))}
    epoch = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    pool = [s for s in universe(db) if s not in taken]
    rng.shuffle(pool)  # random tie-break among never-tested symbols
    pool.sort(key=lambda s: _aware(ledger.get(s)) or epoch)
    stale_half = pool[: max(n * 3, 1)]  # random draw from the least-recently tested slice, not strictly oldest-first
    picks += [Pick(s, "universe") for s in rng.sample(stale_half, min(n - len(picks), len(stale_half)))]
    return picks[:n]


def _aware(t: dt.datetime | None) -> dt.datetime | None:
    if t is not None and t.tzinfo is None:
        return t.replace(tzinfo=dt.timezone.utc)  # SQLite returns naive datetimes
    return t


def mark(db: Session, symbol: str, cohort: str, result: str) -> None:
    row = db.get(QaTickerLedger, symbol[:24]) or QaTickerLedger(symbol=symbol[:24], runs=0)
    row.runs = (row.runs or 0) + 1
    row.last_tested_at = dt.datetime.now(dt.timezone.utc)
    row.last_cohort, row.last_result = cohort, result
    db.merge(row)
