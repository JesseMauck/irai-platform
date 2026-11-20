"""ValueBot inside IRAI: the valuation engine's routes under /api/valuebot, plus accounts and quotas.

The platform overrides two of ValueBot's routes:
  POST /api/valuebot/jobs   requires sign-in, enforces the plan's monthly run quota, records the run
  GET  /api/valuebot/jobs   lists only the signed-in user's runs (ValueBot's own lists every job)
Everything else (company preview, thesis draft, job progress, result, files, what-if revalue, share
links) is ValueBot's router unchanged.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from valuebot import pipeline
from valuebot.api import JobRequest
from valuebot.api import router as valuebot_router

from ..db import SessionLocal, get_db
from ..models import ValuationRun, User
from ..security import current_user, limits

router = APIRouter(prefix="/api/valuebot", tags=["valuebot"])


def _month() -> str:
    return dt.date.today().strftime("%Y-%m")


def _run(r: ValuationRun) -> dict:
    return {"id": r.job_id, "ticker": r.ticker, "stance": r.stance, "status": r.status, "method": r.method,
            "value_per_share": r.value_per_share, "price": r.price, "upside": r.upside,
            "prob_undervalued": r.prob_undervalued, "share_token": r.share_token, "error": r.error,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None}


def usage(db: Session, user: User) -> dict:
    used = db.scalar(select(func.count()).select_from(ValuationRun).where(
        ValuationRun.user_id == user.id, ValuationRun.month == _month())) or 0
    cap = limits(user)["valuebot_runs_per_month"]
    return {"used": used, "limit": cap, "remaining": None if cap is None else max(0, cap - used)}


@router.get("/usage")
def get_usage(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return usage(db, user)


@router.post("/jobs")
def create_job(req: JobRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    u = usage(db, user)
    if u["remaining"] == 0:
        raise HTTPException(402, f"You've used your {u['limit']} ValueBot run(s) this month. Upgrade for more.")
    data = req.model_dump()
    data["email"] = data.get("email") or None
    job = pipeline.create_job(data)
    db.add(ValuationRun(job_id=job["id"], user_id=user.id, ticker=job["ticker"], stance=req.stance,
                        status="queued", share_token=job["share_token"], month=_month()))
    db.commit()
    pipeline.start_job(job)
    return {"id": job["id"], "usage": usage(db, user)}


@router.get("/jobs")
def my_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    runs = db.scalars(select(ValuationRun).where(ValuationRun.user_id == user.id)
                      .order_by(ValuationRun.created_at.desc()).limit(100))
    return [_run(r) for r in runs]


def record_finished(job: dict) -> None:
    """pipeline.on_finish hook: copy the outcome of a finished job into valuation_runs."""
    with SessionLocal() as db:
        r = db.scalar(select(ValuationRun).where(ValuationRun.job_id == job["id"]))
        if not r:
            return
        s = job.get("summary") or {}
        r.status = job.get("status", "error")
        r.value_per_share, r.price, r.upside = s.get("value_per_share"), s.get("price"), s.get("upside")
        r.method, r.prob_undervalued = s.get("method"), s.get("prob_undervalued")
        r.error = (job.get("error") or "")[:500] or None
        r.finished_at = dt.datetime.now(dt.timezone.utc)
        db.commit()


if record_finished not in pipeline.on_finish:
    pipeline.on_finish.append(record_finished)

# ValueBot's own routes come after ours so the overrides above win.
router.include_router(valuebot_router)
