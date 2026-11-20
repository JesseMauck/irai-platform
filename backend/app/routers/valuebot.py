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
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from valuebot import pipeline
from valuebot.api import JobRequest
from valuebot.api import router as valuebot_router

from .. import mail
from ..db import SessionLocal, get_db
from ..models import ValuationRun, User
from ..security import current_user, limits

router = APIRouter(prefix="/api/valuebot", tags=["valuebot"])


def _month() -> str:
    return dt.date.today().strftime("%Y-%m")


def _run(r: ValuationRun) -> dict:
    return {"id": r.job_id, "ticker": r.ticker, "stance": r.stance, "status": r.status, "method": r.method,
            "title": r.title or f"{r.ticker} — {r.stance} valuation", "pinned": bool(r.pinned),
            "archived": bool(r.archived), "has_notes": bool(r.notes_md),
            "scenario_count": len(r.scenarios or []),
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
        want = (job.get("request") or {}).get("email")
        owner = db.get(User, r.user_id) if r.user_id else None
        if want and owner:
            verdict = (f"value {r.value_per_share:,.2f} vs price {r.price:,.2f}" if r.status == "done" and r.value_per_share
                       else f"status {r.status}")
            mail.enqueue(db, owner.email, f"Your {r.ticker} valuation is ready",
                         f"ValueBot finished {r.ticker}: {verdict}.\n\n{mail.link('/valuebot/' + r.job_id)}{mail.FOOTER}",
                         "valuebot_done")
        db.commit()


if record_finished not in pipeline.on_finish:
    pipeline.on_finish.append(record_finished)

# ── report library: the member's saved reports, their own notes, saved scenarios and exports ─────
class MetaIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    notes_md: str | None = Field(default=None, max_length=50_000)
    pinned: bool | None = None
    archived: bool | None = None


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    assumptions: dict[str, float]


def _owned(db: Session, user: User, job_id: str) -> ValuationRun:
    r = db.scalar(select(ValuationRun).where(ValuationRun.job_id == job_id))
    if not r or r.user_id != user.id:
        raise HTTPException(404, "Report not found")
    return r


def _detail(r: ValuationRun) -> dict:
    return {**_run(r), "notes_md": r.notes_md or "", "scenarios": r.scenarios or [],
            "notes_updated_at": r.notes_updated_at.isoformat() if r.notes_updated_at else None}


@router.get("/library")
def library(archived: bool = False, q: str | None = None, user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    """Saved reports: pinned first, then newest. `q` filters by ticker or title."""
    stmt = select(ValuationRun).where(ValuationRun.user_id == user.id, ValuationRun.archived.is_(archived))
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(func.lower(ValuationRun.ticker).like(like) | func.lower(func.coalesce(ValuationRun.title, "")).like(like))
    runs = db.scalars(stmt.order_by(ValuationRun.pinned.desc(), ValuationRun.created_at.desc()).limit(500))
    return [_run(r) for r in runs]


@router.get("/jobs/{job_id}/meta")
def get_meta(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _detail(_owned(db, user, job_id))


@router.patch("/jobs/{job_id}/meta")
def update_meta(job_id: str, body: MetaIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _owned(db, user, job_id)
    if body.title is not None:
        r.title = body.title.strip() or None
    if body.notes_md is not None:
        r.notes_md = body.notes_md
        r.notes_updated_at = dt.datetime.now(dt.timezone.utc)
    if body.pinned is not None:
        r.pinned = body.pinned
    if body.archived is not None:
        r.archived = body.archived
    db.commit()
    return _detail(r)


@router.post("/jobs/{job_id}/scenarios")
def save_scenario(job_id: str, body: ScenarioIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Recompute with edited drivers (same engine as what-if) and keep the result with the report."""
    from valuebot.api import RevalueRequest, revalue

    r = _owned(db, user, job_id)
    if r.status != "done":
        raise HTTPException(409, "The valuation hasn't finished yet")
    if len(r.scenarios or []) >= 20:
        raise HTTPException(400, "A report can keep up to 20 scenarios")
    out = revalue(job_id, RevalueRequest(assumptions=body.assumptions))
    sc = {"name": body.name.strip(), "assumptions": body.assumptions, "value_per_share": out["value_per_share"],
          "upside": out["upside"], "warnings": out.get("warnings") or [],
          "saved_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    r.scenarios = [*(r.scenarios or []), sc]  # reassign so the JSON change is persisted
    db.commit()
    return _detail(r)


@router.delete("/jobs/{job_id}/scenarios/{index}")
def delete_scenario(job_id: str, index: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _owned(db, user, job_id)
    items = list(r.scenarios or [])
    if not 0 <= index < len(items):
        raise HTTPException(404, "Scenario not found")
    items.pop(index)
    r.scenarios = items
    db.commit()
    return _detail(r)


def _notes_html(r: ValuationRun) -> str:
    import html

    import markdown as md

    parts = ['<section style="page-break-before:always;font-family:Inter,Arial,sans-serif">',
             f"<h1>{html.escape(r.title or r.ticker)} — member notes</h1>"]
    if r.notes_md:
        parts.append(md.markdown(html.escape(r.notes_md), extensions=["tables", "sane_lists"]))
    if r.scenarios:
        parts.append("<h2>Saved scenarios</h2><table border=1 cellpadding=6 style='border-collapse:collapse'>"
                     "<tr><th>Scenario</th><th>Value / share</th><th>vs price</th><th>Changed drivers</th></tr>")
        for sc in r.scenarios:
            up = f"{sc['upside'] * 100:+.1f}%" if sc.get("upside") is not None else "—"
            drv = ", ".join(f"{html.escape(k)} = {v:g}" for k, v in sc["assumptions"].items())
            parts.append(f"<tr><td>{html.escape(sc['name'])}</td><td>{sc['value_per_share']:,.2f}</td><td>{up}</td><td>{drv}</td></tr>")
        parts.append("</table>")
    parts.append("<p style='color:#666;font-size:10px'>Member notes are the author's own views. Research and education only — not investment advice.</p></section>")
    return "".join(parts)


@router.get("/jobs/{job_id}/export.pdf")
def export_pdf(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The ValueBot report as PDF, with the member's notes and saved scenarios appended."""
    import tempfile
    from pathlib import Path

    from fastapi.responses import FileResponse
    from valuebot.output import report

    r = _owned(db, user, job_id)
    src = pipeline.job_dir(job_id) / "report.html"
    if not src.exists():
        raise HTTPException(409, "The report isn't ready yet")
    page = src.read_text()
    extra = _notes_html(r) if (r.notes_md or r.scenarios) else ""
    page = page.replace("</body>", extra + "</body>") if "</body>" in page else page + extra
    tmp = Path(tempfile.mkdtemp(prefix="vbexport-"))
    (tmp / "report.html").write_text(page)
    # Images referenced relatively (tornado chart etc.) must sit next to the HTML.
    for img in pipeline.job_dir(job_id).glob("*.png"):
        (tmp / img.name).write_bytes(img.read_bytes())
    if not report.write_pdf(tmp / "report.html", tmp / "report.pdf"):
        raise HTTPException(503, "PDF rendering is unavailable on this server")
    return FileResponse(tmp / "report.pdf", filename=f"{r.ticker}_valuebot_report.pdf", media_type="application/pdf")


@router.get("/jobs/{job_id}/export.xlsx")
def export_xlsx(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The live-formula model workbook plus a 'My notes' sheet with the member's notes and scenarios."""
    import io

    from fastapi.responses import StreamingResponse
    from openpyxl import load_workbook
    from openpyxl.styles import Font

    r = _owned(db, user, job_id)
    src = pipeline.job_dir(job_id) / "model.xlsx"
    if not src.exists():
        raise HTTPException(409, "The model isn't ready yet")
    wb = load_workbook(src)
    ws = wb.create_sheet("My notes")
    ws["A1"] = r.title or f"{r.ticker} valuation"
    ws["A1"].font = Font(bold=True, size=14)
    row = 3
    for line in (r.notes_md or "(No notes yet)").splitlines():
        ws.cell(row=row, column=1, value=line)
        row += 1
    if r.scenarios:
        row += 1
        for c, h in enumerate(["Scenario", "Value / share", "vs price", "Changed drivers"], 1):
            ws.cell(row=row, column=c, value=h).font = Font(bold=True)
        for sc in r.scenarios:
            row += 1
            ws.cell(row=row, column=1, value=sc["name"])
            ws.cell(row=row, column=2, value=sc["value_per_share"])
            ws.cell(row=row, column=3, value=sc.get("upside"))
            ws.cell(row=row, column=4, value=", ".join(f"{k} = {v:g}" for k, v in sc["assumptions"].items()))
    ws.column_dimensions["A"].width = 60
    ws.column_dimensions["D"].width = 60
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{r.ticker}_valuebot_model.xlsx"'})


# ValueBot's own routes come after ours so the overrides above win.
router.include_router(valuebot_router)
