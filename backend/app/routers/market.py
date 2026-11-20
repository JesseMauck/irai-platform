"""Live market data: any ticker the user types (stocks, ETFs, indices, FX, crypto)."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..market import engines, service
from ..market.source import SourceError
from ..models import GradeSnapshot, Instrument, PeerMember

router = APIRouter(prefix="/api/market", tags=["market"])
SYMBOL_RE = re.compile(r"^[A-Za-z0-9^=.\-]{1,20}$")
RANGES = {"1mo", "3mo", "6mo", "1y", "2y", "5y"}


def _sym(s: str) -> str:
    s = s.strip()
    if not SYMBOL_RE.match(s):
        raise HTTPException(422, "Invalid symbol")
    return s.upper()


@router.get("/status")
def status():
    return service.status()


@router.get("/tickerbar")
def tickerbar(db: Session = Depends(get_db)):
    rows = db.scalars(select(Instrument).where(Instrument.in_ticker_bar).order_by(Instrument.sort_order)).all()
    q = service.quotes([r.symbol for r in rows])
    return [{"symbol": r.symbol, "label": r.ticker_bar_label or r.symbol, "price": q[r.symbol]["price"],
             "change_pct": q[r.symbol].get("change_pct"), "source": q[r.symbol].get("source")}
            for r in rows if r.symbol in q]


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=40)):
    return service.search(q)


@router.get("/quote/{symbol}")
def quote(symbol: str):
    try:
        return service.quote(_sym(symbol))
    except SourceError as e:
        raise HTTPException(404, str(e))


@router.get("/quotes")
def quotes(symbols: str = Query(max_length=400)):
    syms = [_sym(s) for s in symbols.split(",") if s.strip()][:50]
    return service.quotes(syms)


@router.get("/chart/{symbol}")
def chart(symbol: str, range: str = "1y"):  # noqa: A002
    if range not in RANGES:
        raise HTTPException(422, f"range must be one of {sorted(RANGES)}")
    try:
        return service.chart(_sym(symbol), range)
    except SourceError as e:
        raise HTTPException(404, str(e))


@router.get("/ticker/{symbol}")
def ticker(symbol: str, db: Session = Depends(get_db)):
    """Everything the ticker page needs in one call: quote, 1y history, fundamentals, peer grade."""
    sym = _sym(symbol)
    try:
        c = service.chart(sym, "1y")
    except SourceError as e:
        raise HTTPException(404, str(e))
    try:
        info = service.info(sym)
    except SourceError:
        info = {}
    grade = None
    member = db.scalar(select(PeerMember).where(PeerMember.symbol == sym))
    if member:
        grp = member.group
        rows = engines.score_peer_group(grp.name, [{"symbol": m.symbol, "name": m.name} for m in grp.members],
                                        {m.symbol: _safe_info(m.symbol) for m in grp.members})
        mine = next((r for r in rows if r["symbol"] == sym), None)
        if mine:
            grade = {**mine, "peers": [{"symbol": r["symbol"], "grade": r["grade"], "multiple": r["multiple"],
                                         "rv_percentile": r["rv_percentile"]} for r in rows]}
            if mine["rv_percentile"] is not None:
                db.add(GradeSnapshot(symbol=sym, peer_group=grp.name, grade=mine["grade"],
                                     rv_percentile=mine["rv_percentile"], quality_percentile=mine["quality_percentile"],
                                     multiple=mine["multiple"], multiple_name=mine["multiple_name"],
                                     residual=mine["residual"], source=mine["source"]))
                db.commit()
    hist = db.scalars(select(GradeSnapshot).where(GradeSnapshot.symbol == sym)
                      .order_by(GradeSnapshot.as_of.desc()).limit(30)).all()
    return {"quote": c["quote"], "history": c["history"], "info": info, "grade": grade,
            "grade_history": [{"as_of": h.as_of.isoformat(), "grade": h.grade, "rv_percentile": h.rv_percentile}
                              for h in reversed(hist)]}


def _safe_info(sym: str) -> dict:
    try:
        return service.info(sym)
    except SourceError:
        return {}
