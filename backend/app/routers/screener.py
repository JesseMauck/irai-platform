"""Market screener endpoints: catalog with the Daily Spotlight, preset results, custom screens and CSV export."""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import screener
from ..models import User
from ..security import PLAN_ORDER, current_user, optional_user

router = APIRouter(prefix="/api/screener", tags=["screener"])
NOTE = "Screens surface things to research; they are not recommendations. Prices may be delayed; every row shows its data source."
BASE = ["price", "change_pct", "rel_volume", "ret_1m", "vs_sma50"]


def _rank(u: User | None) -> int:
    return PLAN_ORDER.get(u.plan, 0) if u else -1


def _slim(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in r.items() if k not in ("beta_calc",)} for r in rows]


@router.get("")
def catalog():
    c = screener.catalog()
    return {**c, "note": NOTE}


@router.get("/presets/{pid}")
def preset(pid: str, user: User | None = Depends(optional_user)):
    if pid not in screener.BY_ID:
        raise HTTPException(404, "Unknown screen")
    r = screener.run_preset(pid)
    lim = None if _rank(user) >= 1 else 10  # Essential and Pro see every match; free and visitors see the top 10
    rows = r["rows"] if lim is None else r["rows"][:lim]
    cols = list(dict.fromkeys(r["preset"]["columns"] + BASE))[:7]
    return {**r, "rows": _slim(rows), "columns": cols, "locked": lim is not None and r["matches"] > len(rows), "hidden": max(0, min(r["matches"], screener.BY_ID[pid]["limit"]) - len(rows)),
            "as_of": screener.snapshot()["at"], "source": screener.snapshot()["source"], "note": NOTE}


class Custom(BaseModel):
    filters: list[list[Any]] = Field(default_factory=list, max_length=15)
    sort: str = "dollar_volume"
    desc: bool = True
    kind: str | None = None
    limit: int = Field(100, ge=10, le=400)
    columns: list[str] | None = None


@router.post("/run")
def run_custom(body: Custom, user: User = Depends(current_user)):
    if _rank(user) < 1:
        raise HTTPException(402, "Custom screens are part of Essential and Pro")
    screener.validate(body.model_dump())
    r = screener.run([tuple(x) for x in body.filters], body.sort, body.desc, body.kind, body.limit)
    cols = [c for c in (body.columns or []) if c in screener.FIELDS] or list(dict.fromkeys([body.sort] + [f[0] for f in body.filters if f[0] in screener.FIELDS] + BASE))[:8]
    return {**r, "rows": _slim(r["rows"]), "columns": cols, "as_of": screener.snapshot()["at"], "source": screener.snapshot()["source"], "note": NOTE}


@router.post("/export")
def export(body: Custom, user: User = Depends(current_user)):
    if _rank(user) < 2:
        raise HTTPException(402, "CSV export is part of Pro")
    screener.validate(body.model_dump())
    r = screener.run([tuple(x) for x in body.filters], body.sort, body.desc, body.kind, 400)
    cols = ["symbol", "name", "kind", "sector", "category"] + [c for c in screener.FIELDS]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for row in r["rows"]:
        w.writerow([row.get(c) for c in cols])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=irai-screen.csv"})
