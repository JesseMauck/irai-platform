"""Structured findings, fingerprinting (dedup) and persistence into qa_issues."""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import QaIssue

CATEGORIES = {"bug", "trading_logic", "data", "latency", "ux"}
SEVERITIES = {"high", "medium", "low"}
MAX_EXAMPLE_TICKERS = 20


@dataclass
class Finding:
    issue_type: str  # e.g. server_error, accounting_mismatch, position_over_cap, stale_quote, slow_response
    category: str
    severity: str
    flow: str  # cohort / flow name, e.g. webhook_trader
    endpoint: str  # METHOD path as called (normalized for the fingerprint)
    title: str
    expected: str
    actual: str
    ticker: str | None = None
    strategy: str | None = None
    step: str | None = None
    error: str = ""  # the error text used for dedup (status + message)
    trace: dict[str, Any] | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        assert self.category in CATEGORIES, self.category
        assert self.severity in SEVERITIES, self.severity

    @property
    def fingerprint(self) -> str:
        key = "|".join([self.issue_type, self.flow, normalize_endpoint(self.endpoint, self.ticker), normalize_error(self.error, self.ticker)])
        return hashlib.sha256(key.encode()).hexdigest()[:32]


_NUM = re.compile(r"[-+]?\$?\d[\d,]*(?:\.\d+)?%?")
_HEX = re.compile(r"\b[0-9a-f]{8,}\b|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_TOKEN = re.compile(r"[A-Za-z0-9_\-]{20,}")


def normalize_endpoint(endpoint: str, ticker: str | None = None) -> str:
    e = endpoint.split("?", 1)[0]
    e = re.sub(r"/api/bots/hook/[^/\s]+", "/api/bots/hook/{token}", e)
    if ticker:
        e = re.sub(rf"/{re.escape(ticker)}(?=/|$)", "/{symbol}", e, flags=re.I)
    return re.sub(r"/\d+(?=/|$)", "/{id}", e)


def normalize_error(err: str, ticker: str | None = None) -> str:
    s = (err or "").strip()
    if ticker:
        s = re.sub(rf"\b{re.escape(ticker)}\b", "{symbol}", s, flags=re.I)
    s = _HEX.sub("{hex}", s)
    s = _TOKEN.sub("{tok}", s)
    s = _NUM.sub("{n}", s)
    return re.sub(r"\s+", " ", s)[:300].lower()


def record(db: Session, f: Finding, run_id: int | None) -> tuple[QaIssue, bool]:
    """Upsert by fingerprint. Returns (issue, is_new). A reappearing fixed issue becomes 'regressed'."""
    now = dt.datetime.now(dt.timezone.utc)
    fp = f.fingerprint
    row = db.scalar(select(QaIssue).where(QaIssue.fingerprint == fp))
    if row is None:
        row = QaIssue(fingerprint=fp, issue_type=f.issue_type, category=f.category, severity=f.severity, status="new",
                      flow=f.flow, endpoint=normalize_endpoint(f.endpoint, f.ticker)[:200], strategy=f.strategy, step=f.step,
                      title=f.title[:300], expected=f.expected, actual=f.actual, tickers=[f.ticker] if f.ticker else [],
                      trace=f.trace, context=f.context, occurrences=1, first_run_id=run_id, last_run_id=run_id,
                      first_seen=now, last_seen=now)
        db.add(row)
        db.flush()
        return row, True
    row.occurrences += 1
    row.last_seen, row.last_run_id = now, run_id
    row.actual, row.trace, row.context = f.actual, f.trace, f.context
    if f.ticker:
        tickers = [t for t in (row.tickers or []) if t != f.ticker] + [f.ticker]
        row.tickers = tickers[-MAX_EXAMPLE_TICKERS:]
    if row.status == "fixed":
        row.status = "regressed"
    if _rank(f.severity) > _rank(row.severity):
        row.severity = f.severity
    return row, False


def _rank(sev: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(sev, 0)
