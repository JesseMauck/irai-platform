"""Portfolio workspace (Pro): holdings entered by hand or imported from a broker CSV, full analytics and an AI review.
Broker connections (IRAI AlgoTrader) will populate the same tables."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import portfolio as pf
from ..db import get_db
from ..models import Holding, Portfolio, User
from ..security import require_plan

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])
pro = require_plan("pro")
MAX_PORTFOLIOS = 10
BENCHMARKS = "^(SPY|QQQ|IWM|DIA|ACWI|VT|AGG)$"


class HoldingIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    quantity: float = Field(gt=-1e12, lt=1e12)
    cost_basis: float | None = Field(None, ge=0, lt=1e9)


class PortfolioIn(BaseModel):
    name: str = Field("My portfolio", min_length=1, max_length=80)
    cash: float = Field(0, ge=0, lt=1e12)
    benchmark: str = Field("SPY", pattern=BENCHMARKS)
    holdings: list[HoldingIn] = Field(default_factory=list, max_length=pf.MAX_HOLDINGS)


class PortfolioPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    cash: float | None = Field(None, ge=0, lt=1e12)
    benchmark: str | None = Field(None, pattern=BENCHMARKS)


class ImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=400_000)
    mode: str = Field("replace", pattern="^(replace|merge)$")


def _own(db: Session, pid: int, user: User) -> Portfolio:
    p = db.get(Portfolio, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Portfolio not found")
    return p


def _clean(items: list[HoldingIn]) -> list[dict]:
    out: dict[str, dict] = {}
    for h in items:
        s = h.symbol.strip().upper()
        if not pf.SYM_RE.match(s):
            raise HTTPException(422, f"Invalid symbol: {h.symbol}")
        if h.quantity == 0:
            continue
        out[s] = {"symbol": s, "quantity": h.quantity, "cost_basis": h.cost_basis}
    return list(out.values())


def _set_holdings(p: Portfolio, rows: list[dict]) -> None:
    """Replace the holdings, updating rows in place so the (portfolio, symbol) unique key never collides mid-flush."""
    want = {r["symbol"]: r for r in rows[: pf.MAX_HOLDINGS]}
    for h in list(p.holdings):
        if h.symbol in want:
            r = want.pop(h.symbol)
            h.quantity, h.cost_basis = r["quantity"], r.get("cost_basis")
        else:
            p.holdings.remove(h)
    for r in want.values():
        p.holdings.append(Holding(symbol=r["symbol"], quantity=r["quantity"], cost_basis=r.get("cost_basis")))


def _out(p: Portfolio) -> dict:
    return {"id": p.id, "name": p.name, "source": p.source, "cash": p.cash, "benchmark": p.benchmark,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "holdings": [{"symbol": h.symbol, "quantity": h.quantity, "cost_basis": h.cost_basis} for h in p.holdings]}


@router.get("")
def list_portfolios(user: User = Depends(pro), db: Session = Depends(get_db)):
    rows = db.scalars(select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.id)).all()
    return [{"id": p.id, "name": p.name, "source": p.source, "positions": len(p.holdings)} for p in rows]


@router.post("")
def create(body: PortfolioIn, user: User = Depends(pro), db: Session = Depends(get_db)):
    n = db.scalar(select(func.count()).select_from(Portfolio).where(Portfolio.user_id == user.id)) or 0
    if n >= MAX_PORTFOLIOS:
        raise HTTPException(400, f"Up to {MAX_PORTFOLIOS} portfolios")
    p = Portfolio(user_id=user.id, name=body.name.strip(), cash=body.cash, benchmark=body.benchmark, source="manual")
    _set_holdings(p, _clean(body.holdings))
    db.add(p)
    db.commit()
    return _out(p)


@router.get("/{pid}")
def get(pid: int, user: User = Depends(pro), db: Session = Depends(get_db)):
    return _out(_own(db, pid, user))


@router.patch("/{pid}")
def patch(pid: int, body: PortfolioPatch, user: User = Depends(pro), db: Session = Depends(get_db)):
    p = _own(db, pid, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v.strip() if isinstance(v, str) and k == "name" else v)
    db.commit()
    return _out(p)


@router.delete("/{pid}")
def delete(pid: int, user: User = Depends(pro), db: Session = Depends(get_db)):
    db.delete(_own(db, pid, user))
    db.commit()
    return {"ok": True}


@router.put("/{pid}/holdings")
def put_holdings(pid: int, body: list[HoldingIn], user: User = Depends(pro), db: Session = Depends(get_db)):
    if len(body) > pf.MAX_HOLDINGS:
        raise HTTPException(422, f"Up to {pf.MAX_HOLDINGS} holdings")
    p = _own(db, pid, user)
    _set_holdings(p, _clean(body))
    db.commit()
    return _out(p)


@router.post("/{pid}/import")
def import_csv(pid: int, body: ImportIn, user: User = Depends(pro), db: Session = Depends(get_db)):
    p = _own(db, pid, user)
    rows, warnings = pf.parse_csv(body.csv)
    if not rows:
        raise HTTPException(422, warnings[0] if warnings else "No holdings found in the file")
    if body.mode == "merge":
        cur = {h.symbol: {"symbol": h.symbol, "quantity": h.quantity, "cost_basis": h.cost_basis} for h in p.holdings}
        for r in rows:
            cur[r["symbol"]] = r
        rows = list(cur.values())
    _set_holdings(p, rows)
    p.source = "csv"
    db.commit()
    return {**_out(p), "imported": len(rows), "warnings": warnings}


def _analysis(p: Portfolio) -> dict:
    if not p.holdings:
        raise HTTPException(400, "Add holdings first")
    return pf.analyze([{"symbol": h.symbol, "quantity": h.quantity, "cost_basis": h.cost_basis} for h in p.holdings],
                      cash=p.cash, benchmark=p.benchmark)


@router.get("/{pid}/analysis")
def analysis(pid: int, user: User = Depends(pro), db: Session = Depends(get_db)):
    return {"portfolio": _out(_own(db, pid, user)), **_analysis(_own(db, pid, user))}


@router.post("/{pid}/review")
def ai_review(pid: int, user: User = Depends(pro), db: Session = Depends(get_db)):
    a = _analysis(_own(db, pid, user))
    return {**pf.review(a), "disclaimer": "Written from the figures shown. Research and education only, not personalized "
                                          "investment advice; it does not consider your goals, taxes or circumstances."}
