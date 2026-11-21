"""Admin → QA: synthetic-trader run health and the issue queue. Admins only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import QaIssue, User
from .admin import require_admin

router = APIRouter(prefix="/api/admin/qa", tags=["admin"])
STATUSES = "^(new|needs_more_data|valid|false_positive|fixed|regressed|wontfix)$"


class IssuePatch(BaseModel):
    status: str | None = Field(None, pattern=STATUSES)
    fix_ref: str | None = Field(None, max_length=300)
    note: str | None = Field(None, max_length=2000)


def _out(i: QaIssue, full: bool = False) -> dict:
    d = {"id": i.id, "fingerprint": i.fingerprint, "title": i.title, "issue_type": i.issue_type, "category": i.category,
         "severity": i.severity, "status": i.status, "flow": i.flow, "step": i.step, "strategy": i.strategy, "endpoint": i.endpoint,
         "tickers": i.tickers, "occurrences": i.occurrences, "first_seen": i.first_seen.isoformat(), "last_seen": i.last_seen.isoformat(),
         "verdict": (i.triage or {}).get("verdict"), "fix_ref": i.fix_ref}
    if full:
        d.update(expected=i.expected, actual=i.actual, trace=i.trace, context=i.context, triage=i.triage)
    return d


@router.get("/status")
def status(_: User = Depends(require_admin)):
    from ..qa.__main__ import status_report

    return status_report()


@router.get("/issues")
def issues(status: str | None = None, category: str | None = None, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(QaIssue).order_by(QaIssue.last_seen.desc()).limit(200)
    if status:
        stmt = stmt.where(QaIssue.status == status)
    if category:
        stmt = stmt.where(QaIssue.category == category)
    return [_out(i) for i in db.scalars(stmt)]


@router.get("/issues/{iid}")
def issue(iid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    i = db.get(QaIssue, iid)
    if not i:
        raise HTTPException(404, "Issue not found")
    return _out(i, full=True)


@router.patch("/issues/{iid}")
def patch_issue(iid: int, body: IssuePatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    i = db.get(QaIssue, iid)
    if not i:
        raise HTTPException(404, "Issue not found")
    if body.status:
        i.status = body.status
    if body.fix_ref is not None:
        i.fix_ref = body.fix_ref or None
    if body.note:
        i.triage = {**(i.triage or {}), "admin_note": body.note, "admin": admin.handle}
    db.commit()
    return _out(i, full=True)
