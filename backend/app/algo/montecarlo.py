"""Monte Carlo price/portfolio simulation from daily history.

Methods
  gbm        geometric Brownian motion with drift and volatility estimated from log returns
  bootstrap  resample historical daily return *vectors* (keeps cross-asset correlation and fat tails)
  student_t  GBM with Student-t shocks (df=4) scaled to the historical volatility — fatter tails than normal

Outputs percentile fan, terminal-value distribution, probabilities of touching a target or a stop,
and Value-at-Risk / Conditional VaR at the horizon. Deterministic for a given seed.
"""
from __future__ import annotations

from typing import Any

import numpy as np

PCTS = (5, 10, 25, 50, 75, 90, 95)


def simulate(returns: np.ndarray, weights: np.ndarray, *, start_value: float, horizon: int, paths: int,
             method: str = "bootstrap", drift: str = "historical", seed: int = 7,
             target: float | None = None, stop: float | None = None, bins: int = 40) -> dict[str, Any]:
    """`returns`: (T, N) simple daily returns; `weights`: (N,) summing to 1 (rebalanced daily)."""
    rng = np.random.default_rng(seed)
    T, N = returns.shape
    if T < 60:
        raise ValueError("Need at least 60 days of history")
    weights = weights / weights.sum()
    logr = np.log1p(returns)
    if method == "bootstrap":
        idx = rng.integers(0, T, size=(paths, horizon))
        port = np.log1p(returns[idx] @ weights)                               # (paths, horizon)
        if drift == "zero":  # zero arithmetic expected return ⇒ log drift of −σ²/2
            port = port - port.mean() - 0.5 * port.var()
    else:
        cov = np.cov(logr, rowvar=False).reshape(N, N)
        # Drift in LOG space. The sample mean of log returns already contains the −σ²/2 (Itô) term, so it is
        # used as-is. "zero" means zero *arithmetic* expected return, i.e. a log drift of −σ²/2.
        mu = logr.mean(axis=0) if drift == "historical" else -0.5 * np.diag(cov)
        chol = np.linalg.cholesky(cov + 1e-12 * np.eye(N))
        if method == "student_t":
            df = 4.0
            z = rng.standard_t(df, size=(paths, horizon, N)) / np.sqrt(df / (df - 2))
        elif method == "gbm":
            z = rng.standard_normal(size=(paths, horizon, N))
        else:
            raise ValueError(f"Unknown method {method}")
        shocks = z @ chol.T + mu                                             # (paths, horizon, N) log returns
        port = np.log1p((np.expm1(shocks)) @ weights)
    cum = np.cumsum(port, axis=1)
    values = start_value * np.exp(cum)                                       # (paths, horizon)
    terminal = values[:, -1]
    fan = {str(p): np.percentile(values, p, axis=0).round(4).tolist() for p in PCTS}
    rets = terminal / start_value - 1
    var95 = float(-np.percentile(rets, 5))
    cvar95 = float(-rets[rets <= np.percentile(rets, 5)].mean())
    hist, edges = np.histogram(terminal, bins=bins)
    out: dict[str, Any] = {
        "horizon_days": horizon, "paths": paths, "method": method, "drift": drift, "start_value": start_value,
        "fan": fan, "terminal": {str(p): float(np.percentile(terminal, p)) for p in PCTS},
        "expected_terminal": float(terminal.mean()), "prob_gain": float((terminal > start_value).mean()),
        "var_95": var95, "cvar_95": cvar95,
        "ann_vol_hist": float(np.std(returns @ weights) * np.sqrt(252)),
        "ann_return_hist": float(np.expm1(np.log1p(returns @ weights).mean() * 252)),
        "histogram": {"counts": hist.tolist(), "edges": edges.round(4).tolist()},
        "sample_paths": values[: min(25, paths)].round(4).tolist(),
    }
    if target:
        out["prob_touch_target"] = float((values.max(axis=1) >= target).mean())
        out["prob_end_above_target"] = float((terminal >= target).mean())
    if stop:
        out["prob_touch_stop"] = float((values.min(axis=1) <= stop).mean())
    return out
