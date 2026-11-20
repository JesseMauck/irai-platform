"""ADR, ETF and Fundamental RV monitors plus preset screeners, all computed from live data."""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..market import engines
from ..models import AdrPair, EtfFund, PeerGroup, User
from ..security import limits, optional_user, require_plan

router = APIRouter(prefix="/api/monitors", tags=["monitors"])


def _pairs(db: Session) -> list[dict[str, Any]]:
    return [{c.name: getattr(p, c.name) for c in AdrPair.__table__.columns}
            for p in db.scalars(select(AdrPair).where(AdrPair.active).order_by(AdrPair.id))]


def _funds(db: Session) -> list[dict[str, Any]]:
    return [{"symbol": f.symbol, "name": f.name, "category": f.category}
            for f in db.scalars(select(EtfFund).where(EtfFund.active))]


def _groups(db: Session) -> list[dict[str, Any]]:
    return [{"name": g.name, "sector": g.sector, "members": [{"symbol": m.symbol, "name": m.name} for m in g.members]}
            for g in db.scalars(select(PeerGroup).order_by(PeerGroup.id))]


def _gate(rows: list[dict], user: User | None, strip: tuple[str, ...] = ()) -> dict:
    lim = limits(user).get("monitor_rows")
    visible = rows if lim is None else rows[:lim]
    if strip and lim is not None:
        visible = [{k: v for k, v in r.items() if k not in strip} for r in visible]
    return {"rows": visible, "total": len(rows), "locked": len(rows) - len(visible),
            "plan": user.plan if user else "free"}


@router.get("/adr")
def adr(user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    rows = engines.build_adr_monitor(_pairs(db))
    return _gate([{k: v for k, v in r.items() if k != "premium_history"} for r in rows], user)


@router.get("/adr/{adr_symbol}")
def adr_pair(adr_symbol: str, db: Session = Depends(get_db)):
    p = db.scalar(select(AdrPair).where(AdrPair.adr_symbol == adr_symbol.upper()))
    if not p:
        raise HTTPException(404, "Pair not covered")
    return engines.adr_row({c.name: getattr(p, c.name) for c in AdrPair.__table__.columns})


@router.get("/etf")
def etf(user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    return _gate(engines.build_etf_monitor(_funds(db)), user)


@router.get("/fundamental")
def fundamental(user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    rows = engines.build_fundamental(_groups(db))
    return _gate(rows, user, strip=("residual", "fitted_multiple"))


PRESETS = {
    "adr-discounts": ("Largest ADR discounts vs basis", "ADR deviation below −2σ"),
    "adr-premiums": ("Largest ADR premiums vs basis", "ADR deviation above +2σ"),
    "etf-gaps": ("ETF premiums / discounts ≥ 0.5%", "|price / NAV − 1| ≥ 0.5%"),
    "cheap-for-quality": ("Cheap-for-quality", "Fundamental RV percentile ≥ 80"),
    "quality-leaders": ("Quality leaders", "Quality percentile ≥ 80"),
}


@router.get("/screeners")
def screeners():
    return [{"key": k, "title": t, "rule": r} for k, (t, r) in PRESETS.items()]


def run_screen(key: str, db: Session) -> list[dict[str, Any]]:
    if key.startswith("adr"):
        rows = engines.build_adr_monitor(_pairs(db))
        sign = -1 if key == "adr-discounts" else 1
        return [{"name": f"{r['adr_symbol']} vs {r['local_symbol']}", "symbol": r["adr_symbol"], "value": r.get("premium"),
                 "z": r.get("z"), "half_life_days": r.get("half_life_days"), "source": r["source"]}
                for r in rows if r.get("z") is not None and sign * r["z"] >= 2]
    if key == "etf-gaps":
        return [{"name": r["name"], "symbol": r["symbol"], "value": r.get("premium"), "z": None, "half_life_days": None,
                 "source": r["source"]} for r in engines.build_etf_monitor(_funds(db))
                if r.get("premium") is not None and abs(r["premium"]) >= 0.005]
    rows = engines.build_fundamental(_groups(db))
    field = "rv_percentile" if key == "cheap-for-quality" else "quality_percentile"
    return [{"name": r["name"], "symbol": r["symbol"], "value": r.get(field), "grade": r["grade"],
             "peer_group": r["peer_group"], "source": r["source"]}
            for r in rows if (r.get(field) or 0) >= 80]


@router.get("/screeners/{key}")
def screen(key: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    if key not in PRESETS:
        raise HTTPException(404, "Unknown screen")
    if user is None or user.plan == "free":
        if key not in ("adr-discounts", "cheap-for-quality"):
            raise HTTPException(402, "Free accounts get 2 preset screens; upgrade for all of them")
    return {"key": key, "title": PRESETS[key][0], "rule": PRESETS[key][1], "rows": run_screen(key, db)}


@router.get("/screeners/{key}/csv")
def screen_csv(key: str, user: User = Depends(require_plan("pro")), db: Session = Depends(get_db)):
    if key not in PRESETS:
        raise HTTPException(404, "Unknown screen")
    rows = run_screen(key, db)
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{key}.csv"'})
