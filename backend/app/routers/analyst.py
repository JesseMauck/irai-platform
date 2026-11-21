"""Analyst Bot API: start a run (progress is polled), read a report, latest report per ticker, my history."""
from __future__ import annotations

import datetime as dt
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import analyst
from ..db import get_db
from ..models import AnalystReport, User
from ..security import current_user, limits

router = APIRouter(prefix="/api/analyst", tags=["analyst"])
REUSE_MINUTES = 120  # a finished report on the same ticker this recent is served instead of re-running


def _out(r: AnalystReport) -> dict:
    done = sum(1 for s in r.stages if s["status"] == "done")
    return {"id": r.id, "symbol": r.symbol, "status": r.status, "stages": r.stages, "progress": done / max(1, len(r.stages)),
            "result": r.result, "error": r.error, "engine": r.engine,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None}


def _sym(symbol: str) -> str:
    s = symbol.strip().upper()
    if not re.match(r"^[A-Z0-9.\-=^]{1,20}$", s):
        raise HTTPException(400, "Invalid ticker")
    return s


def _aware(t: dt.datetime | None) -> dt.datetime | None:
    return t.replace(tzinfo=dt.timezone.utc) if t is not None and t.tzinfo is None else t


@router.post("/{symbol}")
def start(symbol: str, fresh: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sym = _sym(symbol)
    now = dt.datetime.now(dt.timezone.utc)
    running = db.scalar(select(AnalystReport).where(AnalystReport.symbol == sym, AnalystReport.status.in_(("queued", "running")),
                                                    AnalystReport.created_at > now - dt.timedelta(minutes=10)).order_by(AnalystReport.created_at.desc()))
    if running:
        return _out(running)
    if not fresh:
        recent = db.scalar(select(AnalystReport).where(AnalystReport.symbol == sym, AnalystReport.status == "done",
                                                       AnalystReport.finished_at > now - dt.timedelta(minutes=REUSE_MINUTES))
                           .order_by(AnalystReport.finished_at.desc()))
        if recent:
            return {**_out(recent), "reused": True}
    cap = limits(user).get("analyst_reports_per_day")
    if cap is not None:
        used = db.scalar(select(func.count()).select_from(AnalystReport).where(
            AnalystReport.user_id == user.id, AnalystReport.created_at > now - dt.timedelta(days=1))) or 0
        if used >= cap:
            raise HTTPException(402, f"Your plan includes {cap} Analyst Bot run{'s' if cap != 1 else ''} a day. Upgrade for more, or open the latest shared report.")
    r = analyst.new_report(user.id, sym)
    db.add(r)
    db.commit()
    analyst.start(r.id)
    return _out(r)


@router.get("/reports/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db)):
    r = db.get(AnalystReport, report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    if r.status in ("queued", "running") and _aware(r.created_at) < dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=15):
        r.status, r.error = "error", "Timed out"
        db.commit()
    return _out(r)


@router.get("/{symbol}/latest")
def latest(symbol: str, db: Session = Depends(get_db)):
    r = db.scalar(select(AnalystReport).where(AnalystReport.symbol == _sym(symbol), AnalystReport.status == "done")
                  .order_by(AnalystReport.finished_at.desc()))
    return _out(r) if r else None


@router.get("")
def mine(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AnalystReport).where(AnalystReport.user_id == user.id).order_by(AnalystReport.created_at.desc()).limit(50)).all()
    return [{"id": r.id, "symbol": r.symbol, "status": r.status, "engine": r.engine, "headline": (r.result or {}).get("analysis", {}).get("headline"),
             "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]



