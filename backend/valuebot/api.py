"""ValueBot HTTP routes as a reusable APIRouter.

Mounted at /api by the standalone server (valuebot.server) and at /api/valuebot by the IRAI platform.
"""
from __future__ import annotations

import json
import re
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, field_validator

from . import analysis, pipeline
from .config import settings
from .data import provider
from .engine import registry
from .llm import agent

ALLOWED_FILES = {"model.xlsx", "model_bear.xlsx", "model_bull.xlsx", "model_market.xlsx", "report.html", "report.pdf"}
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-^=]{0,14}$")
JOB_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")

router = APIRouter(tags=["valuebot"])


def clean_ticker(v: str) -> str:
    t = (v or "").upper().strip()
    if not TICKER_RE.match(t):
        raise ValueError("Ticker must be 1-15 characters: letters, digits, '.', '-', '^' or '='")
    return t


class ThesisRequest(BaseModel):
    ticker: str
    stance: Literal["bullish", "bearish", "neutral"] = "neutral"

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: str) -> str:
        return clean_ticker(v)


class Stories(BaseModel):
    growth: str = ""
    profitability: str = ""
    efficiency: str = ""
    risk: str = ""
    moat: str = ""


class Market(BaseModel):
    tam: float | None = Field(None, ge=0, description="Total addressable market today, in reporting currency")
    tam_growth: float | None = Field(None, ge=-0.5, le=1.0)
    target_share: float | None = Field(None, ge=0, le=1.0)


class Adjustments(BaseModel):
    capitalize_rnd: Literal["auto", "yes", "no"] = "auto"
    rnd_life: int | None = Field(None, ge=1, le=20)
    lease_adjust: bool = True
    one_time_addback: float | None = None
    normalize_margins: bool = False


class Region(BaseModel):
    region: str
    weight: float = Field(ge=0)
    crp: float | None = Field(None, ge=0, le=0.5)


class Segment(BaseModel):
    name: str
    weight: float = Field(ge=0)
    unlevered_beta: float | None = Field(None, ge=0, le=5)
    revenue_y10: float | None = Field(None, ge=0, description="Year-10 revenue target for this business")
    target_margin: float | None = Field(None, ge=-1, le=1)


class Risk(BaseModel):
    regions: list[Region] = []
    segments: list[Segment] = []
    inflation: float | None = Field(None, ge=-0.05, le=1.0)
    riskfree_override: float | None = Field(None, ge=-0.05, le=0.5)


class Extras(BaseModel):
    nol: float | None = Field(None, ge=0)
    options_count: float | None = Field(None, ge=0)
    options_strike: float | None = Field(None, ge=0)
    options_maturity: float | None = Field(None, gt=0, le=15)
    volatility: float | None = Field(None, gt=0, le=3)
    non_operating_assets: float | None = None


class JobRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    thesis: str = ""
    questions: list[str] = []
    stance: Literal["bullish", "bearish", "neutral"] = "neutral"
    method: Literal["auto", "fcff", "ddm", "excess_return"] = "auto"
    email: str | None = None
    stories: Stories = Stories()
    market: Market = Market()
    overrides: dict[str, float] = {}
    adjustments: Adjustments = Adjustments()
    risk: Risk = Risk()
    extras: Extras = Extras()

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: str) -> str:
        return clean_ticker(v)


class RevalueRequest(BaseModel):
    assumptions: dict[str, float]


@router.get("/health")
def health():
    return {"ok": True, "llm": settings.llm_enabled, "offline": settings.offline, "model": settings.model,
            "methods": {k: m.TITLE for k, m in registry.METHODS.items()}}


@router.get("/search")
def search(q: str):
    if not q.strip():
        return []
    return provider.search(q[:64])[:10]


@router.get("/company/{ticker}")
def company(ticker: str):
    """Quick preview for step 1: name, price, sector and the method auto-selection would pick."""
    try:
        ticker = clean_ticker(ticker)
    except ValueError as e:
        raise HTTPException(422, str(e))
    try:
        snap = provider.snapshot(ticker)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Data source error: {e}")
    metrics = analysis.history_metrics(snap)
    last = metrics[-1]
    method, reason = registry.choose_method(
        sector=snap.get("sector"), industry=snap.get("industry"), payout_ratio=snap.get("payout_ratio"),
        pays_dividends=bool(snap.get("dividend_rate")), has_revenue=bool(last.get("revenue")))
    return {"ticker": snap["ticker"], "name": snap["name"], "price": snap["price"], "currency": snap["currency"],
            "sector": snap.get("sector"), "industry": snap.get("industry"), "market_cap": snap.get("market_cap"),
            "demo": snap.get("demo", False), "suggested_method": method, "method_reason": reason,
            "latest": {k: last.get(k) for k in ("fiscal_year", "revenue", "revenue_growth", "operating_margin",
                                                "gross_margin", "sales_to_capital", "roic", "roe")},
            "rnd_intensity": (last.get("rnd") or 0) / last["revenue"] if last.get("revenue") else 0,
            "has_leases": bool(snap["history"][-1].get("lease_liabilities")),
            "options_outstanding": snap["history"][-1].get("options_outstanding"),
            "nol": snap["history"][-1].get("nol"),
            "drivers": {k: [{"key": d.key, "label": d.label, "unit": d.unit} for d in m.DRIVERS]
                        for k, m in registry.METHODS.items()}}


@router.post("/thesis")
def draft_thesis(req: ThesisRequest):
    try:
        snap = provider.snapshot(req.ticker)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Data source error: {e}")
    return agent.draft_thesis(snap, analysis.history_metrics(snap), req.stance)


@router.post("/jobs")
def create_job(req: JobRequest):
    job = pipeline.create_job(req.model_dump())
    pipeline.start_job(job)
    return {"id": job["id"]}


@router.get("/jobs")
def jobs():
    return pipeline.list_jobs()


def _job_or_404(job_id: str) -> dict:
    if not JOB_ID_RE.match(job_id) or not (pipeline.job_dir(job_id) / "job.json").exists():
        raise HTTPException(404, "No such job")
    return pipeline.load_job(job_id)


@router.get("/jobs/{job_id}")
def job(job_id: str):
    j = _job_or_404(job_id)
    j.pop("traceback", None)
    return j


@router.get("/jobs/{job_id}/result")
def result(job_id: str):
    _job_or_404(job_id)
    f = pipeline.job_dir(job_id) / "result.json"
    if not f.exists():
        raise HTTPException(409, "Not finished")
    return json.loads(f.read_text())


@router.get("/jobs/{job_id}/files/{name}")
def file(job_id: str, name: str):
    _job_or_404(job_id)
    if name not in ALLOWED_FILES:
        raise HTTPException(404)
    f = pipeline.job_dir(job_id) / name
    if not f.exists():
        raise HTTPException(404)
    j = pipeline.load_job(job_id)
    download = f"{j['ticker']}_{name}"
    if name.endswith(".html"):
        return HTMLResponse(f.read_text())
    return FileResponse(f, filename=download)


@router.post("/jobs/{job_id}/revalue")
def revalue(job_id: str, req: RevalueRequest):
    """What-if: recompute value per share with edited drivers (nothing is saved)."""
    data = result(job_id)
    allowed = {d.key for d in registry.drivers_for(data["method"])}
    inputs = {**data["inputs"], **{k: v for k, v in req.assumptions.items() if k in allowed}}
    r = registry.run(data["method"], inputs)
    return {"value_per_share": r.value_per_share, "upside": r.upside, "warnings": r.warnings}


@router.get("/share/{token}")
def shared(token: str):
    job_id = pipeline.find_by_share_token(token)
    if not job_id:
        raise HTTPException(404, "Link not found")
    data = result(job_id)
    data["job_id"] = job_id
    data["read_only"] = True
    return data


@router.get("/share/{token}/files/{name}")
def shared_file(token: str, name: str):
    job_id = pipeline.find_by_share_token(token)
    if not job_id:
        raise HTTPException(404)
    return file(job_id, name)
