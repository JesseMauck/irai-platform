"""Pattern recognition endpoints: regimes, lead-lag, market states, crypto microstructure.

Regimes and states are fitted on the nightly cleaned panel and cached for 6 hours; free members see the current regime and
state, Pro members get the full detail (transition matrix, analogues, lead-lag tables, order-book ladder).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from ..models import User
from ..security import PLAN_ORDER, current_user

router = APIRouter(prefix="/api/quant", tags=["quant"])
_cache: dict[str, tuple[float, Any]] = {}
_locks: dict[str, threading.Lock] = {}
TTL = 6 * 3600
DISCLAIMER = "Statistical patterns describe the past and can stop working. Research and education only, not a recommendation."


def _cached(key: str, fn: Callable[[], Any], ttl: float = TTL) -> Any:
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    lock = _locks.setdefault(key, threading.Lock())
    with lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        val = fn()
        _cache[key] = (time.time(), val)
        return val


def _pro(user: User) -> bool:
    return PLAN_ORDER.get(user.plan, 0) >= PLAN_ORDER["pro"] or bool(getattr(user, "is_admin", False))


@router.get("/regimes")
def regimes(symbol: str = Query("SPY", max_length=20), user: User = Depends(current_user)):
    from ..quant import patterns

    try:
        out = _cached(f"reg:{symbol.upper()}", lambda: patterns.regimes(symbol.upper()))
    except LookupError as e:
        raise HTTPException(404, str(e))
    if not _pro(user) and symbol.upper() != "SPY":
        raise HTTPException(402, "Regimes for other symbols are part of Pro")
    return {**out, "locked": not _pro(user), "disclaimer": DISCLAIMER}


@router.get("/leadlag")
def leadlag(universe: str = Query("macro", pattern="^(macro|sectors|megacaps)$"), user: User = Depends(current_user)):
    from ..quant import patterns

    out = _cached(f"ll:{universe}", lambda: patterns.leadlag(universe))
    if not _pro(user):
        sig = [p for p in out["pairs"] if p["significant"]]
        return {**out, "pairs": sig[:2], "locked": True, "hidden": max(0, len(sig) - 2), "disclaimer": DISCLAIMER}
    return {**out, "locked": False, "disclaimer": DISCLAIMER}


@router.get("/states")
def states(user: User = Depends(current_user)):
    from ..quant import patterns

    try:
        out = _cached("states", patterns.market_states)
    except LookupError as e:
        raise HTTPException(503, str(e))
    if not _pro(user):
        return {**{k: v for k, v in out.items() if k not in ("analogs",)}, "analogs": out["analogs"][:2], "locked": True, "disclaimer": DISCLAIMER}
    return {**out, "locked": False, "disclaimer": DISCLAIMER}


@router.get("/micro")
def micro(pair: str = Query("BTC-USD", max_length=12), user: User = Depends(current_user)):
    from ..quant import patterns

    try:
        out = patterns.microstructure(pair)
    except LookupError as e:
        raise HTTPException(503, str(e))
    except Exception:  # noqa: BLE001  network / provider failure
        raise HTTPException(503, "Order-book feed is unavailable right now")
    if out.get("available") and not _pro(user):
        out = {**out, "ladder": None, "recent": out.get("recent", [])[-10:], "locked": True}
    return {**out, "disclaimer": DISCLAIMER}


# ── five-step pattern engine ────────────────────────────────────────────────────────────────────
from pydantic import BaseModel, Field  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ..db import get_db  # noqa: E402
from ..models import PatternStudy  # noqa: E402

FREE_KEYS = ("pattern", "asset_class", "timeframe", "verdict", "checks_passed", "checks_total", "events", "status", "definition")


def _latest_grid(db: Session) -> PatternStudy | None:
    return db.scalar(select(PatternStudy).where(PatternStudy.kind == "grid").order_by(PatternStudy.created_at.desc()))


@router.get("/patterns")
def patterns_overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..quant import engine

    g = _latest_grid(db)
    pro = _pro(user)
    grid = None
    if g and g.results:
        rows = g.results["results"]
        grid = {"created_at": g.created_at.isoformat(), "n_tests": g.n_tests, "robust": g.passed, "source": g.source, "hurdle": g.results.get("hurdle"),
                "results": rows if pro else [{k: o.get(k) for k in FREE_KEYS} for o in rows]}
    return {"catalog": engine.catalog(), "grid": grid, "running": engine._state["running"], "progress": engine._state["progress"],
            "locked": not pro, "disclaimer": DISCLAIMER,
            "note": None if grid else "The first study runs overnight after the close; check back tomorrow, or run a single test with Pro."}


@router.get("/patterns/result")
def pattern_result(pattern: str, asset_class: str, timeframe: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not _pro(user):
        raise HTTPException(402, "Full test results are part of Pro")
    g = _latest_grid(db)
    for o in (g.results["results"] if g and g.results else []):
        if (o["pattern"], o.get("asset_class"), o.get("timeframe")) == (pattern, asset_class, timeframe):
            return {**o, "study_at": g.created_at.isoformat(), "disclaimer": DISCLAIMER}
    raise HTTPException(404, "No result for that pattern, asset class and timeframe yet")


@router.get("/patterns/live")
def patterns_live(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Which assets show a pattern on their latest bar, only for patterns that passed every stress test (Robust)."""
    g = _latest_grid(db)
    rows = [o for o in (g.results["results"] if g and g.results else []) if o.get("verdict") == "Robust" and o.get("live")]
    items = [{"pattern": o["pattern"], "asset_class": o["asset_class"], "timeframe": o["timeframe"], "verdict": o["verdict"], "symbols": o["live"]} for o in rows]
    if not _pro(user):
        return {"items": [], "locked": True, "count": sum(len(i["symbols"]) for i in items), "disclaimer": DISCLAIMER}
    return {"items": items, "locked": False, "as_of": g.created_at.isoformat() if g else None, "disclaimer": DISCLAIMER}


class PatternTest(BaseModel):
    pattern: str = Field(pattern="^(squeeze_breakout|donchian_volume|trend_pullback|shock_reversal|capitulation|breakdown)$")
    asset_class: str = Field(pattern="^(equities|etfs|rates|fx|commodities|crypto)$")
    timeframe: str = Field(pattern="^(15m|1h|1d|1wk)$")
    symbols: list[str] | None = Field(default=None, max_length=8)
    params: dict[str, float] | None = None


@router.post("/patterns/test")
def pattern_test(body: PatternTest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..quant import engine

    if not _pro(user):
        raise HTTPException(402, "Running your own pattern tests is part of Pro")
    p = engine.BY_ID[body.pattern]
    params = None
    if body.params:
        bad = set(body.params) - set(p.params)
        if bad:
            raise HTTPException(422, f"Unknown parameters: {', '.join(sorted(bad))}")
        params = {**p.params, **{k: float(v) for k, v in body.params.items()}}
    syms = [s.strip().upper()[:20] for s in body.symbols] if body.symbols else None
    key = f"pt:{body.pattern}:{body.asset_class}:{body.timeframe}:{syms}:{sorted((params or {}).items())}"
    res = _cached(key, lambda: engine.run_study([body.asset_class], [body.timeframe], [body.pattern], syms, params), ttl=3600)
    engine.save(db, res, "custom", "member", user.id)
    note = ("You changed the thresholds, so this result is no longer a clean out-of-sample test: every variant you try is another trial. "
            "Treat a pass here with extra caution.") if params else None
    return {**res, "note": note, "disclaimer": DISCLAIMER}
