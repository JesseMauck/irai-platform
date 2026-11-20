"""Per-symbol research panels (quant ratings, consensus, SEC filings & financials, buzz) and buzz rankings."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import research
from ..db import get_db
from ..market.source import SourceError
from ..models import BuzzSnapshot

router = APIRouter(prefix="/api/insight", tags=["insight"])
SYM = r"^[A-Za-z0-9.\-=^]{1,20}$"


def _guard(fn, symbol: str):
    import re

    if not re.match(SYM, symbol):
        raise HTTPException(422, "Invalid symbol")
    try:
        return fn(symbol)
    except SourceError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/{symbol}/ratings")
def ratings(symbol: str):
    return _guard(research.ratings, symbol)


@router.get("/{symbol}/consensus")
def consensus(symbol: str):
    return _guard(research.consensus, symbol)


@router.get("/{symbol}/filings")
def filings(symbol: str):
    return research.filings(symbol)


@router.get("/{symbol}/financials")
def financials(symbol: str):
    return research.financials(symbol)


@router.get("/{symbol}/buzz")
def buzz(symbol: str):
    return _guard(research.buzz, symbol)


@router.get("/{symbol}/headlines")
def headlines(symbol: str):
    return research.headlines(symbol.upper())


buzz_router = APIRouter(prefix="/api/buzz", tags=["insight"])


@buzz_router.get("/trending")
def trending(limit: int = Query(25, ge=1, le=100), kind: str | None = None, db: Session = Depends(get_db)):
    """Latest buzz readings from the scanner, loudest first."""
    q = select(BuzzSnapshot).order_by(BuzzSnapshot.score.desc()).limit(limit)
    if kind:
        q = q.where(BuzzSnapshot.kind == kind)
    return [{"symbol": b.symbol, "name": b.name, "kind": b.kind, "score": b.score, "level": b.level,
             "components": b.components, "as_of": b.as_of.isoformat() if b.as_of else None} for b in db.scalars(q)]
