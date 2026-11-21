"""Strategy Lab: backtest and optimise StockSharp-style strategies on live daily history for any ticker."""
from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..algo import emulator, optimizer
from ..algo.strategies import REGISTRY, Candle
from ..db import get_db
from ..market import service
from ..market.source import SourceError
from ..models import BacktestRun, User
from ..security import current_user, limits, optional_user

router = APIRouter(prefix="/api/lab", tags=["strategy-lab"])
RANGES = {"1y", "2y", "5y"}


class SettingsIn(BaseModel):
    initial_capital: float = Field(100_000, gt=0, le=1e10)
    commission_bps: float = Field(1.0, ge=0, le=100)
    slippage_bps: float = Field(2.0, ge=0, le=200)
    allow_short: bool = False


class BacktestIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9^=.\-]+$")
    strategy: str
    params: dict[str, float] = {}
    range: str = "5y"
    settings: SettingsIn = SettingsIn()


class OptimizeIn(BacktestIn):
    grid: dict[str, list[float]]  # key -> [min, max, step]
    metric: str = "sharpe"
    in_sample: float = Field(0.7, ge=0.4, le=0.9)


def _candles(symbol: str, range_: str) -> tuple[list[Candle], str]:
    if range_ not in RANGES:
        raise HTTPException(422, f"range must be one of {sorted(RANGES)}")
    try:
        c = service.chart(symbol.upper(), range_)
    except SourceError as e:
        raise HTTPException(404, str(e))
    hist = c["history"]
    if len(hist) < 60:
        raise HTTPException(422, f"Only {len(hist)} daily bars available for {symbol.upper()}; need at least 60")
    return [Candle(h["date"], h["close"]) for h in hist], c["quote"].get("source", "LIVE")


def _quota(db: Session, user: User | None) -> None:
    cap = limits(user)["backtests_per_day"]
    if cap is None:
        return
    if user is None:
        raise HTTPException(401, "Sign in to run backtests")
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    n = db.scalar(select(func.count()).select_from(BacktestRun).where(BacktestRun.user_id == user.id,
                                                                     BacktestRun.created_at >= since)) or 0
    if n >= cap:
        raise HTTPException(402, f"Your plan allows {cap} backtests a day. Upgrade for more.")


def _series(r: emulator.EmulationResult, step: int) -> dict[str, Any]:
    eq = r.equity
    first_close, cap = eq[0]["close"], eq[0]["equity"]
    peak, dd = cap, []
    for e in eq:
        peak = max(peak, e["equity"])
        dd.append(e["equity"] / peak - 1)
    idx = list(range(0, len(eq), step)) + ([len(eq) - 1] if (len(eq) - 1) % step else [])
    return {"dates": [eq[i]["date"] for i in idx], "equity": [eq[i]["equity"] for i in idx],
            "benchmark": [cap * eq[i]["close"] / first_close for i in idx], "drawdown": [dd[i] for i in idx],
            "close": [eq[i]["close"] for i in idx], "exposure": [eq[i]["exposure"] for i in idx],
            "indicators": [r.indicators[i] for i in idx]}


@router.get("/strategies")
def strategies():
    return [cls.schema() for cls in REGISTRY.values()]


@router.post("/backtest")
def backtest(body: BacktestIn, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    cls = REGISTRY.get(body.strategy)
    if not cls:
        raise HTTPException(404, "Unknown strategy")
    _quota(db, user)
    candles, source = _candles(body.symbol, body.range)
    st = emulator.EmulationSettings(**body.settings.model_dump())
    strat = cls(allow_short=st.allow_short, **body.params)
    r = emulator.run(strat, candles, st)
    run_id = None
    if user:
        row = BacktestRun(user_id=user.id, symbol=body.symbol.upper(), strategy=cls.KEY, params=strat.params,
                          settings=body.settings.model_dump(), range=body.range, statistics=r.statistics,
                          data_source=source)
        db.add(row)
        db.commit()
        run_id = row.id
    return {"run_id": run_id, "symbol": body.symbol.upper(), "strategy": cls.schema(), "params": strat.params, "data_source": source,
            "statistics": r.statistics, "series": _series(r, max(1, len(candles) // 600)),
            "fills": [f.__dict__ for f in r.fills[-200:]], "roundtrips": [x.__dict__ for x in r.roundtrips[-200:]]}


@router.post("/optimize")
def optimize(body: OptimizeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not limits(user)["optimize"]:
        raise HTTPException(402, "Parameter optimisation is a Pro feature")
    cls = REGISTRY.get(body.strategy)
    if not cls:
        raise HTTPException(404, "Unknown strategy")
    if body.metric not in {"sharpe", "return", "max_relative_drawdown", "win_rate"}:
        raise HTTPException(422, "metric must be sharpe, return, max_relative_drawdown or win_rate")
    candles, source = _candles(body.symbol, body.range)
    grid = {}
    for k, v in body.grid.items():
        p = next((p for p in cls.PARAMS if p.key == k), None)
        if not p or len(v) != 3 or v[2] <= 0:
            raise HTTPException(422, f"grid.{k} must be [min, max, step] for a parameter of {cls.KEY}")
        grid[k] = [p.clamp(x) for x in optimizer.frange(v[0], v[1], v[2])]
    try:
        out = optimizer.optimize(cls.KEY, candles, grid, emulator.EmulationSettings(**body.settings.model_dump()),
                                 metric=body.metric, in_sample=body.in_sample, fixed=body.params)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if body.metric == "max_relative_drawdown":  # lower is better
        out["results"].sort(key=lambda r: r["max_relative_drawdown"])
        out["best"] = out["results"][0]
    db.add(BacktestRun(user_id=user.id, kind="optimize", symbol=body.symbol.upper(), strategy=cls.KEY,
                       params=out["best"]["params"], settings=body.settings.model_dump(), range=body.range,
                       statistics={k: out[k] for k in ("best", "out_of_sample", "combinations")}, data_source=source))
    db.commit()
    return {**out, "data_source": source, "symbol": body.symbol.upper()}


@router.get("/runs")
def runs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(BacktestRun).where(BacktestRun.user_id == user.id)
                      .order_by(BacktestRun.created_at.desc()).limit(50))
    return [{"id": r.id, "kind": r.kind, "symbol": r.symbol, "strategy": r.strategy, "params": r.params, "range": r.range,
             "return": (r.statistics or {}).get("return"), "sharpe": (r.statistics or {}).get("sharpe"),
             "data_source": r.data_source, "created_at": r.created_at.isoformat()} for r in rows]


# ── Monte Carlo ──────────────────────────────────────────────────────────────────────────────────
class Holding(BaseModel):
    symbol: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9^=.\-]+$")
    weight: float = Field(1.0, gt=0)


class MonteCarloIn(BaseModel):
    holdings: list[Holding] = Field(min_length=1, max_length=10)
    method: str = Field("bootstrap", pattern="^(bootstrap|gbm|student_t)$")
    drift: str = Field("historical", pattern="^(historical|zero)$")
    horizon_days: int = Field(252, ge=5, le=1260)
    paths: int = Field(2000, ge=100, le=20000)
    range: str = "5y"
    start_value: float | None = Field(None, gt=0)
    target: float | None = Field(None, gt=0)
    stop: float | None = Field(None, gt=0)
    seed: int = 7


@router.post("/montecarlo")
def montecarlo(body: MonteCarloIn, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    """Simulate future values of one ticker (price) or a weighted portfolio (value of start_value)."""
    import numpy as np

    from ..algo.montecarlo import simulate

    _quota(db, user)
    cap_paths = 2000 if limits(user)["backtests_per_day"] is not None else 20000
    paths = min(body.paths, cap_paths)
    if body.range not in RANGES:
        raise HTTPException(422, f"range must be one of {sorted(RANGES)}")
    series, sources, prices = {}, set(), {}
    for h in body.holdings:
        sym = h.symbol.upper()
        try:
            c = service.chart(sym, body.range)
        except SourceError as e:
            raise HTTPException(404, str(e))
        series[sym] = {x["date"]: x["close"] for x in c["history"]}
        sources.add(c["quote"].get("source", "LIVE"))
        prices[sym] = c["quote"]["price"]
    dates = sorted(set.intersection(*[set(v) for v in series.values()]))
    if len(dates) < 61:
        raise HTTPException(422, "Not enough overlapping daily history (need 60+ shared days)")
    px = np.array([[series[s][d] for s in series] for d in dates], dtype=float)
    rets = px[1:] / px[:-1] - 1
    w = np.array([h.weight for h in body.holdings], dtype=float)
    single = len(body.holdings) == 1
    start = prices[next(iter(series))] if single and not body.start_value else (body.start_value or 10_000.0)
    try:
        out = simulate(rets, w, start_value=start, horizon=body.horizon_days, paths=paths, method=body.method,
                       drift=body.drift, seed=body.seed, target=body.target, stop=body.stop)
    except ValueError as e:
        raise HTTPException(422, str(e))
    src = "DEMO" if "DEMO" in sources else ("STALE" if "STALE" in sources else "LIVE")
    row = BacktestRun(user_id=user.id if user else None, kind="montecarlo", symbol=",".join(series)[:20], strategy=body.method,
                      params=body.model_dump(), settings={"paths": paths, "horizon_days": body.horizon_days}, range=body.range,
                      statistics={k: out[k] for k in ("prob_gain", "var_95", "cvar_95", "expected_terminal")}, data_source=src)
    db.add(row)
    db.commit()
    out["run_id"] = row.id
    return {**out, "symbols": list(series), "weights": (w / w.sum()).round(4).tolist(), "mode": "price" if single and not body.start_value else "portfolio",
            "history_days": len(dates), "history_start": dates[0], "history_end": dates[-1], "source": src, "paths_capped": paths < body.paths,
            "note": "Simulated outcomes from historical behaviour; not a forecast. Past volatility and correlation may not persist."}
