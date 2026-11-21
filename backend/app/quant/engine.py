"""IRAI testable pattern-recognition engine, built as five explicit steps.

Step 1  Concrete, measurable patterns: every pattern is a rule on bar-close data with numeric parameters, a direction,
        a holding horizon and a triple-barrier outcome, so "did it work" has one answer.
Step 2  Scale-invariant features: returns in units of trailing volatility, distances to moving averages in sigma units,
        volume as a trailing z-score, compression as a trailing percentile. A pattern means the same thing on a 15-minute
        Bitcoin chart and a weekly Treasury chart, so events can be pooled across assets and timeframes.
Step 3  Point-in-time dataset and labels: features at bar t use data up to t only; entries happen at the NEXT bar's open;
        labels look forward from there with profit, stop and time barriers; events are spaced so their outcome windows
        never overlap. Every study records which bars it used (source + content hash).
Step 4  Interpretable baselines before any deep model: random-entry base rate, the rule itself, and an L2 logistic
        regression on the same features with readable coefficients. A pattern has to beat the base rate.
Step 5  Stress tests: untouched chronological holdout with an embargo, purged walk-forward folds, a permutation test
        against random entries, Benjamini-Hochberg across every test in the study, a deflated hurdle for the number of
        trials, regime and year stability, parameter sensitivity, and trading costs.

Research and education only: a pattern that passes describes the past, not the future.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..market import service

log = logging.getLogger("irai.patterns")

# ── universe: every asset class, four timeframes ─────────────────────────────────────────────────
ASSET_CLASSES: dict[str, dict[str, Any]] = {
    "equities": {"label": "US stocks", "symbols": ["AAPL", "MSFT", "NVDA", "AMZN", "JPM", "XOM", "UNH", "WMT"], "cost_bps": 3},
    "etfs": {"label": "Index & sector ETFs", "symbols": ["SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "EEM", "SMH"], "cost_bps": 2},
    "rates": {"label": "Rates & credit", "symbols": ["TLT", "IEF", "HYG", "LQD", "^TNX"], "cost_bps": 2},
    "fx": {"label": "Currencies", "symbols": ["EURUSD=X", "USDJPY=X", "GBPUSD=X", "AUDUSD=X", "USDCAD=X"], "cost_bps": 1.5},
    "commodities": {"label": "Commodities", "symbols": ["CL=F", "GC=F", "SI=F", "HG=F", "NG=F", "ZC=F"], "cost_bps": 4},
    "crypto": {"label": "Crypto", "symbols": ["BTC-USD", "ETH-USD", "SOL-USD"], "cost_bps": 10},
}
TIMEFRAMES = {"15m": {"label": "15-minute", "horizon": 16}, "1h": {"label": "Hourly", "horizon": 12},
              "1d": {"label": "Daily", "horizon": 10}, "1wk": {"label": "Weekly", "horizon": 6}}
MIN_BARS = 260
FEATURES = ["z_ret", "dist_20", "dist_50", "dist_200", "squeeze_pct", "vol_z", "clv", "rsi_3"]
FEATURE_LABELS = {"z_ret": "Bar return in sigma units", "dist_20": "Distance to 20-bar average (sigma)", "dist_50": "Distance to 50-bar average (sigma)",
                  "dist_200": "Distance to 200-bar average (sigma)", "squeeze_pct": "Volatility percentile (trailing 252 bars)",
                  "vol_z": "Volume z-score (trailing 50 bars)", "clv": "Close location in bar range (0 low, 1 high)", "rsi_3": "3-bar RSI"}


# ── Step 2: scale-invariant, point-in-time features ──────────────────────────────────────────────
def _ewm_var(x: np.ndarray, halflife: float) -> np.ndarray:
    a = 1 - 0.5 ** (1 / halflife)
    out = np.empty_like(x)
    v = np.nanvar(x[: min(len(x), 30)]) or 1e-8
    for i, xi in enumerate(x):
        if np.isfinite(xi):
            v = (1 - a) * v + a * xi * xi
        out[i] = v
    return out


def _sma(x: np.ndarray, n: int) -> np.ndarray:
    o = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.insert(x, 0, 0.0))
        o[n - 1:] = (cs[n:] - cs[:-n]) / n
    return o


def _trailing_rank(x: np.ndarray, window: int = 252, min_obs: int = 60) -> np.ndarray:
    """Percentile of x[t] among x[t-window..t-1]; uses only the past."""
    o = np.full(len(x), np.nan)
    for t in range(min_obs, len(x)):
        past = x[max(0, t - window):t]
        past = past[np.isfinite(past)]
        if past.size >= min_obs and np.isfinite(x[t]):
            o[t] = float((past < x[t]).mean())
    return o


def normalise(bars: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    o = np.array([b["o"] for b in bars], float)
    h = np.array([b["h"] for b in bars], float)
    lo = np.array([b["l"] for b in bars], float)
    c = np.array([b["c"] for b in bars], float)
    v = np.array([b.get("v") or 0.0 for b in bars], float)
    lr = np.concatenate([[np.nan], np.diff(np.log(c))])
    var = _ewm_var(np.nan_to_num(lr), 20)
    sigma = np.sqrt(var)  # per-bar volatility known at the close of bar t
    prev_sigma = np.concatenate([[np.nan], sigma[:-1]])
    f: dict[str, np.ndarray] = {"o": o, "h": h, "l": lo, "c": c, "sigma": sigma}
    f["z_ret"] = lr / prev_sigma
    for n in (20, 50, 200):
        f[f"dist_{n}"] = np.log(c / _sma(c, n)) / (sigma * math.sqrt(n))
    rv20 = np.sqrt(_sma(np.nan_to_num(lr) ** 2, 20))
    f["squeeze_pct"] = _trailing_rank(rv20)
    if (v > 0).sum() > len(v) * 0.8:
        lv = np.log(np.maximum(v, 1))
        m, s = _sma(lv, 50), np.sqrt(np.maximum(_sma(lv ** 2, 50) - _sma(lv, 50) ** 2, 1e-12))
        f["vol_z"] = (lv - np.concatenate([[np.nan], m[:-1]])) / np.concatenate([[np.nan], s[:-1]])
    else:  # FX and some indices report no volume
        f["vol_z"] = np.full(len(c), np.nan)
    rng = h - lo
    f["clv"] = np.where(rng > 0, (c - lo) / np.where(rng > 0, rng, 1), 0.5)
    d = np.diff(c, prepend=c[0])
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    au, ad = _sma(up, 3), _sma(dn, 3)
    f["rsi_3"] = np.where(ad > 0, 100 - 100 / (1 + au / np.where(ad > 0, ad, 1)), 100.0)
    f["hi_prior"] = {n: np.concatenate([[np.nan] * n, np.array([h[i - n:i].max() for i in range(n, len(h))])]) for n in (20, 55)}  # type: ignore[assignment]
    f["lo_prior"] = {n: np.concatenate([[np.nan] * n, np.array([lo[i - n:i].min() for i in range(n, len(lo))])]) for n in (20, 55)}  # type: ignore[assignment]
    return f


# ── Step 1: concrete, measurable patterns ────────────────────────────────────────────────────────
@dataclass
class Pattern:
    id: str
    name: str
    family: str
    direction: int  # +1 measures upside follow-through, -1 downside
    definition: str
    params: dict[str, float]
    rule: Callable[[dict[str, Any], dict[str, float]], np.ndarray]
    needs_volume: bool = False
    barrier: tuple[float, float] = (1.0, 1.0)  # profit, stop in units of sigma * sqrt(horizon)
    tags: list[str] = field(default_factory=list)


def _gt(a, b):
    return np.nan_to_num(a, nan=-np.inf) > b


def _lt(a, b):
    return np.nan_to_num(a, nan=np.inf) < b


PATTERNS: list[Pattern] = [
    Pattern("squeeze_breakout", "Volatility squeeze breakout", "Breakout", 1,
            "Volatility over the prior 20 bars sits in the lowest {squeeze:.0%} of the past year AND the bar closes above the highest high of the prior 20 bars.",
            {"squeeze": 0.2}, lambda f, p: _lt(np.concatenate([[np.nan], f["squeeze_pct"][:-1]]), p["squeeze"]) & (f["c"] > np.nan_to_num(f["hi_prior"][20], nan=np.inf)),
            tags=["compression", "breakout"]),
    Pattern("donchian_volume", "55-bar breakout on volume", "Breakout", 1,
            "Close above the highest high of the prior 55 bars with volume at least {vol_z} standard deviations above its 50-bar norm.",
            {"vol_z": 1.0}, lambda f, p: (f["c"] > np.nan_to_num(f["hi_prior"][55], nan=np.inf)) & _gt(f["vol_z"], p["vol_z"]), needs_volume=True,
            tags=["trend", "volume"]),
    Pattern("trend_pullback", "Pullback in an uptrend", "Mean reversion", 1,
            "Price is above its 200-bar average (by more than {trend} sigma) AND the 3-bar RSI falls below {rsi}.",
            {"trend": 0.5, "rsi": 15}, lambda f, p: _gt(f["dist_200"], p["trend"]) & _lt(f["rsi_3"], p["rsi"]), tags=["trend", "oversold"]),
    Pattern("shock_reversal", "Downside shock reversal", "Mean reversion", 1,
            "A single bar falls more than {z} times its trailing volatility (the move is extreme for that asset at that timeframe).",
            {"z": 3.0}, lambda f, p: _lt(f["z_ret"], -p["z"]), tags=["shock", "oversold"]),
    Pattern("capitulation", "Capitulation with recovery", "Exhaustion", 1,
            "A down bar of more than {z} sigma on volume more than {vol_z} sigma above normal that still closes in the top {clv:.0%} of its range.",
            {"z": 2.0, "vol_z": 2.5, "clv": 0.4}, lambda f, p: _lt(f["z_ret"], -p["z"]) & _gt(f["vol_z"], p["vol_z"]) & _gt(f["clv"], 1 - p["clv"]),
            needs_volume=True, tags=["volume", "exhaustion"]),
    Pattern("breakdown", "55-bar breakdown", "Breakout", -1,
            "Close below the lowest low of the prior 55 bars while price is below its 200-bar average by more than {trend} sigma.",
            {"trend": 0.5}, lambda f, p: (f["c"] < np.nan_to_num(f["lo_prior"][55], nan=-np.inf)) & _lt(f["dist_200"], -p["trend"]), tags=["trend", "downside"]),
]
BY_ID = {p.id: p for p in PATTERNS}


def describe(p: Pattern, params: dict[str, float] | None = None) -> str:
    return p.definition.format(**(params or p.params))


# ── Step 3: point-in-time labels (triple barrier, next-bar entry, no overlapping windows) ─────────
def label(f: dict[str, Any], idx: np.ndarray, direction: int, horizon: int, barrier: tuple[float, float]) -> dict[str, np.ndarray]:
    """For each signal bar t: enter at o[t+1]; exit at the first barrier touched in bars t+1..t+horizon, else at the close of
    t+horizon. Outcome is the direction-adjusted log return in units of sigma_t * sqrt(horizon) (the expected move)."""
    o, h, lo, c, s = f["o"], f["h"], f["l"], f["c"], f["sigma"]
    n = len(c)
    out_r, out_hit, end = [], [], []
    for t in idx:
        if t + horizon >= n or not np.isfinite(s[t]) or s[t] <= 0:
            out_r.append(np.nan)
            out_hit.append(np.nan)
            end.append(t)
            continue
        e = o[t + 1]
        scale = s[t] * math.sqrt(horizon)
        up, dn = e * math.exp(barrier[0] * scale * direction), e * math.exp(-barrier[1] * scale * direction)
        r, hit, j_end = None, 0.0, t + horizon
        for j in range(t + 1, t + horizon + 1):
            hit_stop = lo[j] <= dn if direction > 0 else h[j] >= dn
            hit_prof = h[j] >= up if direction > 0 else lo[j] <= up
            if hit_stop:  # if both are touched in one bar, assume the stop came first (conservative)
                r, hit, j_end = -barrier[1], 0.0, j
                break
            if hit_prof:
                r, hit, j_end = barrier[0], 1.0, j
                break
        if r is None:
            r = direction * math.log(c[t + horizon] / e) / scale
            hit = 1.0 if r > 0 else 0.0
        out_r.append(r)
        out_hit.append(hit)
        end.append(j_end)
    return {"r": np.array(out_r, float), "hit": np.array(out_hit, float), "end": np.array(end, int)}


def events(mask: np.ndarray, horizon: int, start: int = 200) -> np.ndarray:
    """Signal bars with a cooldown of `horizon` bars, so outcome windows don't overlap (keeps statistics honest)."""
    out, nxt = [], start
    for t in np.flatnonzero(mask):
        if t >= nxt:
            out.append(t)
            nxt = t + horizon + 1
    return np.array(out, int)


def load(symbol: str, timeframe: str) -> dict[str, Any] | None:
    try:
        b = service.bars(symbol, timeframe)
    except Exception as e:  # noqa: BLE001
        log.info("patterns: %s %s unavailable: %s", symbol, timeframe, e)
        return None
    bars = b["bars"]
    if len(bars) < MIN_BARS:
        return None
    digest = hashlib.sha256(json.dumps([bars[0]["t"], bars[-1]["t"], len(bars), round(bars[-1]["c"], 6)]).encode()).hexdigest()[:12]
    return {"symbol": symbol, "timeframe": timeframe, "bars": bars, "source": b["source"], "hash": digest, "f": normalise(bars)}


# ── Step 4: interpretable baselines ──────────────────────────────────────────────────────────────
def logistic(X: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 25) -> np.ndarray:
    """L2-regularised logistic regression by Newton/IRLS. X already standardised; returns [intercept, coefs...]."""
    Xb = np.column_stack([np.ones(len(X)), X])
    w = np.zeros(Xb.shape[1])
    R = np.eye(Xb.shape[1]) * l2
    R[0, 0] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Xb @ w, -30, 30)))
        g = Xb.T @ (p - y) + R @ w
        H = (Xb * (p * (1 - p))[:, None]).T @ Xb + R
        step = np.linalg.solve(H + np.eye(len(w)) * 1e-9, g)
        w -= step
        if np.max(np.abs(step)) < 1e-6:
            break
    return w


def auc(score: np.ndarray, y: np.ndarray) -> float | None:
    pos, neg = score[y == 1], score[y == 0]
    if not len(pos) or not len(neg):
        return None
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(len(order))
    ranks[order] = np.arange(1, len(order) + 1)
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


# ── Step 5: stress tests ─────────────────────────────────────────────────────────────────────────
def _tstat(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) > 0 else 0.0


def bh_qvalues(p: list[float]) -> list[float]:
    """Benjamini-Hochberg adjusted p-values (false discovery rate) across every test in a study."""
    n = len(p)
    if not n:
        return []
    order = np.argsort(p)
    q = np.empty(n)
    prev = 1.0
    for rank, i in reversed(list(enumerate(order, start=1))):
        prev = min(prev, p[i] * n / rank)
        q[i] = prev
    return q.tolist()


def deflated_hurdle(n_trials: int) -> float:
    """Expected maximum t-statistic from n_trials independent tests of pure noise (sqrt(2 ln N) approximation)."""
    return math.sqrt(2 * math.log(max(n_trials, 2)))


@dataclass
class SeriesResult:
    symbol: str
    source: str
    hash: str
    n_bars: int
    first: str
    last: str
    ev_r: np.ndarray
    ev_hit: np.ndarray
    ev_t: np.ndarray  # bar index
    ev_time: list[str]
    ev_feat: np.ndarray
    ev_regime: list[str]
    base_r: np.ndarray
    base_hit: np.ndarray
    base_feat: np.ndarray
    cost: float  # round-trip cost in outcome units, per event
    split_t: int  # first bar of the holdout
    embargo: int
    rnd_pool: np.ndarray  # eligible bars for random entries
    rnd_r: np.ndarray  # outcome of a random entry at each eligible bar
    live_signal: bool


def run_series(d: dict[str, Any], p: Pattern, horizon: int, cost_bps: float, params: dict[str, float] | None = None, holdout: float = 0.3) -> SeriesResult | None:
    f = d["f"]
    n = len(f["c"])
    if p.needs_volume and not np.isfinite(f["vol_z"]).any():
        return None
    prm = params or p.params
    mask = p.rule(f, prm)
    mask[:200] = False
    ev = events(mask, horizon)
    lab = label(f, ev, p.direction, horizon, p.barrier)
    ok = np.isfinite(lab["r"])
    ev = ev[ok]
    # random-entry baseline over every eligible bar, same direction, horizon and barriers (sampled for speed)
    pool = np.arange(200, n - horizon - 1)
    stride = max(1, len(pool) // 1500)
    pool = pool[::stride]
    base = label(f, pool, p.direction, horizon, p.barrier)
    keep = np.isfinite(base["r"])
    pool, base_r, base_hit = pool[keep], base["r"][keep], base["hit"][keep]
    feat = np.column_stack([f[k] for k in FEATURES])
    sig = f["sigma"]
    cost_units = np.array([(cost_bps / 1e4) / (sig[t] * math.sqrt(horizon)) if sig[t] > 0 else 0 for t in ev])
    regimes = []
    sp = f["squeeze_pct"]
    for t in ev:
        vol = "low vol" if sp[t] < 1 / 3 else "high vol" if sp[t] > 2 / 3 else "mid vol"
        tr = "uptrend" if np.nan_to_num(f["dist_200"][t]) > 0 else "downtrend"
        regimes.append(f"{vol}|{tr}")
    times = [d["bars"][t]["t"] for t in ev]
    return SeriesResult(d["symbol"], d["source"], d["hash"], n, d["bars"][0]["t"], d["bars"][-1]["t"], lab["r"][ok] - cost_units, lab["hit"][ok], ev, times,
                        feat[ev], regimes, base_r, base_hit, feat[pool], float(np.median(cost_units)) if len(cost_units) else 0.0,
                        int(n * (1 - holdout)), horizon, pool, base_r, bool(mask[-1]))


def _summ(r: np.ndarray, hit: np.ndarray) -> dict[str, Any]:
    r = r[np.isfinite(r)]
    if not len(r):
        return {"n": 0}
    return {"n": int(len(r)), "mean_r": float(r.mean()), "median_r": float(np.median(r)), "hit_rate": float(np.nanmean(hit)) if len(hit) else None,
            "t": _tstat(r), "profit_factor": float(r[r > 0].sum() / -r[r < 0].sum()) if (r < 0).any() else None}


def study(p: Pattern, series: list[SeriesResult], rng: np.random.Generator, params: dict[str, float] | None = None,
          sensitivity: dict[str, float] | None = None, n_perm: int = 1000) -> dict[str, Any]:
    """Pool events across symbols (outcomes are in sigma units, so they are comparable) and run every stress test."""
    S = [s for s in series if s is not None]
    if not S:
        return {"pattern": p.id, "status": "no_data"}
    r = np.concatenate([s.ev_r for s in S])
    hit = np.concatenate([s.ev_hit for s in S])
    base_r = np.concatenate([s.base_r for s in S])
    base_hit = np.concatenate([s.base_hit for s in S])
    in_hold = np.concatenate([s.ev_t >= s.split_t for s in S]) if r.size else np.array([], bool)
    in_train = np.concatenate([s.ev_t < s.split_t - s.embargo for s in S]) if r.size else np.array([], bool)
    out: dict[str, Any] = {"pattern": p.id, "events": int(len(r)), "symbols": [s.symbol for s in S], "status": "ok"}
    if len(r) < 15:
        out.update(status="too_few", verdict="Insufficient evidence", reasons=[f"Only {len(r)} non-overlapping events; at least 15 are needed."])
        out["baseline"] = _summ(base_r, base_hit)
        return out
    allstat = _summ(r, hit)
    bstat = _summ(base_r, base_hit)
    train, hold = _summ(r[in_train], hit[in_train]), _summ(r[in_hold], hit[in_hold])
    # permutation test: draw the same number of random entries per symbol, many times; where does the real mean land?
    real = float(r.mean())
    sims = np.zeros(n_perm)
    for s in S:
        k = len(s.ev_r)
        if k and len(s.rnd_r):
            draws = rng.integers(0, len(s.rnd_r), size=(n_perm, k))
            sims += (s.rnd_r[draws] - s.cost).sum(axis=1)
    sims /= len(r)
    p_perm = float((1 + (sims >= real).sum()) / (n_perm + 1))
    # purged walk-forward: 5 chronological folds per symbol; each fold's events are judged on their own
    folds = []
    for k in range(5):
        fr = []
        for s in S:
            lo_, hi_ = int(s.n_bars * k / 5), int(s.n_bars * (k + 1) / 5)
            m = (s.ev_t >= lo_ + s.embargo) & (s.ev_t < hi_ - s.embargo)  # purge events whose windows touch a fold edge
            fr.append(s.ev_r[m])
        x = np.concatenate(fr)
        folds.append({"fold": k + 1, "n": int(len(x)), "mean_r": float(x.mean()) if len(x) else None})
    pos_folds = sum(1 for fo in folds if fo["mean_r"] is not None and fo["n"] >= 3 and np.sign(fo["mean_r"]) == np.sign(real))
    used_folds = sum(1 for fo in folds if fo["n"] >= 3)
    # regime stability
    regs: dict[str, list[float]] = {}
    for s in S:
        for rg, v in zip(s.ev_regime, s.ev_r):
            regs.setdefault(rg, []).append(v)
    reg_tbl = [{"regime": k.replace("|", ", "), "n": len(v), "mean_r": float(np.mean(v))} for k, v in sorted(regs.items())]
    reg_used = [x for x in reg_tbl if x["n"] >= 5]
    reg_same = sum(1 for x in reg_used if np.sign(x["mean_r"]) == np.sign(real))
    # by year
    years: dict[str, list[float]] = {}
    for s in S:
        for tm, v in zip(s.ev_time, s.ev_r):
            years.setdefault(tm[:4], []).append(v)
    yr_tbl = [{"year": k, "n": len(v), "mean_r": float(np.mean(v))} for k, v in sorted(years.items())]
    # baselines: logistic regression on the same point-in-time features, trained before the holdout
    lg = None
    try:
        Xb = np.concatenate([s.base_feat for s in S])
        yb = np.concatenate([s.base_hit for s in S])
        tb = np.concatenate([s.rnd_pool >= s.split_t for s in S])
        cols = [i for i in range(Xb.shape[1]) if np.isfinite(Xb[:, i]).mean() > 0.9]
        X = np.nan_to_num(Xb[:, cols])
        mu_, sd_ = X[~tb].mean(0), X[~tb].std(0) + 1e-9
        Z = (X - mu_) / sd_
        if (~tb).sum() > 100 and tb.sum() > 30:
            w = logistic(Z[~tb], yb[~tb])
            score = np.column_stack([np.ones(tb.sum()), Z[tb]]) @ w
            Xe = np.nan_to_num(np.concatenate([s.ev_feat for s in S])[:, cols])
            lg = {"test_auc": auc(score, yb[tb]), "coefficients": sorted([{"feature": FEATURE_LABELS[FEATURES[c]], "weight": round(float(w[i + 1]), 3)} for i, c in enumerate(cols)],
                                                                       key=lambda x: -abs(x["weight"])),
                  "mean_score_on_events": float(1 / (1 + np.exp(-np.mean(np.column_stack([np.ones(len(Xe)), (Xe - mu_) / sd_]) @ w)))),
                  "base_probability": float(yb[~tb].mean())}
    except np.linalg.LinAlgError:
        lg = None
    out.update(all=allstat, baseline=bstat, train=train, holdout=hold, edge_vs_random=float(allstat["mean_r"] - bstat["mean_r"]),
               permutation={"p_value": p_perm, "random_mean": float(sims.mean()), "random_p95": float(np.quantile(sims, 0.95)), "draws": n_perm},
               walk_forward={"folds": folds, "same_sign": pos_folds, "folds_used": used_folds},
               regimes=reg_tbl, years=yr_tbl, logistic=lg, cost_r=float(np.mean([s.cost for s in S])),
               sensitivity=sensitivity, live=[s.symbol for s in S if s.live_signal],
               data=[{"symbol": s.symbol, "source": s.source, "hash": s.hash, "bars": s.n_bars, "from": s.first[:10], "to": s.last[:10], "events": int(len(s.ev_r))} for s in S],
               sources=sorted({s.source for s in S}))
    out["_reg"] = (reg_same, len(reg_used))
    return out


def verdict(o: dict[str, Any], hurdle: float) -> None:
    """Fill verdict and reasons once q-values across the whole study are known."""
    if o.get("status") != "ok":
        return
    reasons, fails = [], 0
    checks = [
        (o["all"]["mean_r"] > 0, f"Average outcome after costs is {'positive' if o['all']['mean_r'] > 0 else 'not positive'} ({o['all']['mean_r']:+.2f} R)"),
        (o["edge_vs_random"] > 0, f"{'Beats' if o['edge_vs_random'] > 0 else 'Does not beat'} random entries by {o['edge_vs_random']:+.2f} R"),
        (o["holdout"].get("n", 0) >= 5 and o["holdout"]["mean_r"] > 0, f"Untouched holdout: {o['holdout'].get('n', 0)} events, average {o['holdout'].get('mean_r', 0):+.2f} R"),
        (o["permutation"]["p_value"] < 0.05, f"Permutation test p = {o['permutation']['p_value']:.3f} against random entries"),
        (o["q_value"] < 0.10, f"False-discovery-adjusted q = {o['q_value']:.3f} across {o['n_tests']} tests"),
        (abs(o["all"]["t"]) >= hurdle, f"t-statistic {o['all']['t']:.2f} vs deflated hurdle {hurdle:.2f} for the number of trials"),
        (o["walk_forward"]["folds_used"] >= 3 and o["walk_forward"]["same_sign"] >= o["walk_forward"]["folds_used"] - 1,
         f"Same sign in {o['walk_forward']['same_sign']} of {o['walk_forward']['folds_used']} walk-forward folds"),
    ]
    rs, ru = o.pop("_reg", (0, 0))
    checks.append((ru >= 2 and rs >= math.ceil(ru * 2 / 3), f"Same sign in {rs} of {ru} market regimes"))
    sens = o.get("sensitivity") or {}
    if sens:
        same = all(np.sign(v) == np.sign(o["all"]["mean_r"]) for v in sens.values() if v is not None)
        checks.append((same, f"{'Holds' if same else 'Breaks'} when every threshold moves ±20%"))
    for ok, txt in checks:
        reasons.append({"pass": bool(ok), "text": txt})
        fails += 0 if ok else 1
    o["checks_passed"] = len(checks) - fails
    o["checks_total"] = len(checks)
    o["verdict"] = "Robust" if fails == 0 else "Promising" if fails <= 2 and o["all"]["mean_r"] > 0 and o["holdout"].get("mean_r", -1) > 0 else "Not robust"
    o["reasons"] = reasons


def _perturb(p: Pattern) -> list[dict[str, float]]:
    out = []
    for k in p.params:
        for m in (0.8, 1.2):
            q = dict(p.params)
            q[k] = q[k] * m
            out.append(q)
    return out


def run_study(asset_classes: list[str] | None = None, timeframes: list[str] | None = None, patterns: list[str] | None = None,
              symbols: list[str] | None = None, params: dict[str, float] | None = None, seed: int = 20261121,
              progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    t0 = time.time()
    acs = asset_classes or list(ASSET_CLASSES)
    tfs = timeframes or list(TIMEFRAMES)
    pats = [BY_ID[x] for x in (patterns or list(BY_ID))]
    rng = np.random.default_rng(seed)
    jobs = [(ac, s, tf) for ac in acs for s in (symbols if symbols else ASSET_CLASSES[ac]["symbols"]) for tf in tfs]
    with ThreadPoolExecutor(max_workers=4) as ex:
        loaded = dict(zip(jobs, ex.map(lambda j: load(j[1], j[2]), jobs)))
    results = []
    for tf in tfs:
        H = TIMEFRAMES[tf]["horizon"]
        for ac in acs:
            ds = [loaded[(ac, s, tf)] for s in (symbols if symbols else ASSET_CLASSES[ac]["symbols"]) if loaded.get((ac, s, tf))]
            if not ds:
                continue
            cost = ASSET_CLASSES[ac]["cost_bps"]
            for p in pats:
                if progress:
                    progress(f"{p.name} · {ASSET_CLASSES[ac]['label']} · {TIMEFRAMES[tf]['label']}")
                series = [run_series(d, p, H, cost, params) for d in ds]
                sens = {}
                for q in _perturb(p) if params is None else []:
                    rr = [x for x in (run_series(d, p, H, cost, q) for d in ds) if x is not None]
                    v = np.concatenate([x.ev_r for x in rr]) if rr else np.array([])
                    sens[", ".join(f"{k}={q[k]:g}" for k in q)] = float(v.mean()) if len(v) >= 10 else None
                o = study(p, series, rng, params, sens)
                o.update(asset_class=ac, timeframe=tf, horizon=H, definition=describe(p, params), cost_bps=cost, custom_params=params is not None)
                results.append(o)
    tested = [o for o in results if o.get("status") == "ok"]
    qs = bh_qvalues([o["permutation"]["p_value"] for o in tested])
    hurdle = deflated_hurdle(len(tested))
    for o, q in zip(tested, qs):
        o["q_value"] = q
        o["n_tests"] = len(tested)
        verdict(o, hurdle)
    for o in results:
        o.pop("_reg", None)
    sources = sorted({x for o in results for x in o.get("sources", [])})
    return {"results": results, "n_tests": len(tested), "hurdle": hurdle, "seconds": round(time.time() - t0, 1),
            "sources": sources, "source": "DEMO" if "DEMO" in sources else "LIVE" if sources else None,
            "loaded": sum(1 for v in loaded.values() if v), "requested": len(jobs), "as_of": dt.datetime.now(dt.timezone.utc).isoformat()}


def catalog() -> dict[str, Any]:
    return {"patterns": [{"id": p.id, "name": p.name, "family": p.family, "direction": "upside" if p.direction > 0 else "downside",
                          "definition": describe(p), "params": p.params, "barrier": {"profit_R": p.barrier[0], "stop_R": p.barrier[1]},
                          "needs_volume": p.needs_volume, "tags": p.tags} for p in PATTERNS],
            "asset_classes": {k: {"label": v["label"], "symbols": v["symbols"], "cost_bps": v["cost_bps"]} for k, v in ASSET_CLASSES.items()},
            "timeframes": TIMEFRAMES, "features": [{"id": k, "label": FEATURE_LABELS[k]} for k in FEATURES],
            "method": {
                "1": "Each pattern is a fixed rule with numeric thresholds, a direction and a holding horizon per timeframe. Outcomes use a triple barrier: "
                     "a profit target and a stop at one expected move (trailing volatility × √horizon) or the close at the horizon, whichever comes first.",
                "2": "Features are scale-invariant: returns in units of trailing volatility, distances to moving averages in sigma units, volume as a "
                     "z-score, compression as a trailing percentile. Outcomes are in R (expected moves), so events pool across assets and timeframes.",
                "3": "Point-in-time: features at a bar use only data up to that bar's close; entry is the next bar's open; events are spaced so "
                     "outcome windows never overlap; each study stores the source and a hash of the bars it used.",
                "4": "Baselines first: the same entry rules at random bars (base rate), the pattern rule, and an L2 logistic regression on the same "
                     "features trained before the holdout with its coefficients shown.",
                "5": "Stress tests: a 30% untouched chronological holdout with an embargo, 5 purged walk-forward folds, 1,000-draw permutation test "
                     "against random entries, Benjamini-Hochberg false-discovery control across every test, a deflated t-hurdle for the number of "
                     "trials, stability across volatility/trend regimes and years, ±20% threshold sensitivity, and asset-class trading costs."}}


# ── nightly study in the worker ──────────────────────────────────────────────────────────────────
_lock = threading.Lock()
_state: dict[str, Any] = {"running": False, "progress": None}


def due(db, now_utc: dt.datetime | None = None) -> bool:
    from sqlalchemy import select

    from ..models import PatternStudy

    now = now_utc or dt.datetime.now(dt.timezone.utc)
    last = db.scalar(select(PatternStudy.created_at).where(PatternStudy.kind == "grid").order_by(PatternStudy.created_at.desc()))
    if last is None:
        return True
    last = last.replace(tzinfo=dt.timezone.utc) if last.tzinfo is None else last
    return now.time() >= dt.time(23, 15) and last.date() < now.date()


def save(db, res: dict[str, Any], kind: str = "grid", trigger: str = "schedule", user_id: int | None = None):
    from ..models import PatternStudy

    passed = sum(1 for o in res["results"] if o.get("verdict") == "Robust")
    row = PatternStudy(kind=kind, trigger=trigger, user_id=user_id, source=res.get("source"), n_tests=res["n_tests"], passed=passed,
                       seconds=res["seconds"], results=json.loads(json.dumps(res, default=float)))
    db.add(row)
    db.commit()
    log.info("patterns report %s", json.dumps({"kind": kind, "tests": res["n_tests"], "robust": passed, "source": res.get("source"),
                                              "loaded": res.get("loaded"), "requested": res.get("requested"), "seconds": res["seconds"]}))
    return row


def start_background(trigger: str = "schedule") -> bool:
    if _lock.locked():
        return False

    def go():
        from ..db import SessionLocal

        with _lock:
            _state.update(running=True)
            try:
                res = run_study(progress=lambda m: _state.update(progress=m))
                with SessionLocal() as db:
                    save(db, res, "grid", trigger)
            except Exception:  # noqa: BLE001
                log.exception("pattern study failed")
            finally:
                _state.update(running=False, progress=None)

    threading.Thread(target=go, daemon=True, name="pattern-study").start()
    return True
