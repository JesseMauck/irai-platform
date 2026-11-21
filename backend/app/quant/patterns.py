"""IRAI pattern recognition on the cleaned data panel.

* Statistical regimes: a 3-state Gaussian hidden Markov model on daily log returns and 21-day volatility, fitted by
  Baum-Welch, decoded with Viterbi. States are ordered by volatility (calm / normal / stressed).
* Cross-asset lead-lag: cross-correlations of daily returns at lags -5..+5 and a Granger-style F-test, so a
  relationship is reported only when the lagged series adds explanatory power.
* Recurring market states: k-means on a standardised daily vector of cross-asset features; the current state, how
  often each state recurs, how long it lasts, and the closest historical analogues with what followed.
* Microstructure: live order-book imbalance, spread, microprice and trade-flow imbalance from Coinbase's public
  level-2 book for crypto; equities need a licensed depth-of-book feed (pluggable).

Everything is descriptive research: patterns describe the past and can break.
"""
from __future__ import annotations

import datetime as dt
import math
import time
from typing import Any

import numpy as np

from . import datapipe


# ── Gaussian HMM (diagonal covariance) ──────────────────────────────────────────────────────────
def _logpdf(X: np.ndarray, mu: np.ndarray, var: np.ndarray) -> np.ndarray:
    # X: (T, D), mu/var: (K, D) -> (T, K)
    return -0.5 * (np.sum(np.log(2 * np.pi * var), axis=1)[None, :] + np.sum((X[:, None, :] - mu[None]) ** 2 / var[None], axis=2))


def fit_hmm(X: np.ndarray, K: int = 3, iters: int = 60, seed: int = 7) -> dict[str, Any]:
    T, D = X.shape
    rng = np.random.default_rng(seed)
    order = np.argsort(X[:, -1])  # initialise by quantiles of the last feature (volatility)
    mu = np.array([X[order[int((k + 0.5) * T / K)]] for k in range(K)])
    var = np.tile(X.var(axis=0) + 1e-8, (K, 1))
    A = np.full((K, K), 0.05 / (K - 1)) + np.eye(K) * (0.95 - 0.05 / (K - 1))
    pi = np.full(K, 1 / K)
    prev = -np.inf
    for _ in range(iters):
        logB = _logpdf(X, mu, var)
        # scaled forward-backward in log space
        la = np.zeros((T, K))
        la[0] = np.log(pi) + logB[0]
        logA = np.log(A)
        for t in range(1, T):
            la[t] = logB[t] + np.logaddexp.reduce(la[t - 1][:, None] + logA, axis=0)
        ll = float(np.logaddexp.reduce(la[-1]))
        lb = np.zeros((T, K))
        for t in range(T - 2, -1, -1):
            lb[t] = np.logaddexp.reduce(logA + logB[t + 1][None] + lb[t + 1][None], axis=1)
        lg = la + lb
        g = np.exp(lg - np.logaddexp.reduce(lg, axis=1, keepdims=True))
        xi = np.zeros((K, K))
        for t in range(T - 1):
            m = la[t][:, None] + logA + logB[t + 1][None] + lb[t + 1][None]
            xi += np.exp(m - np.logaddexp.reduce(m.ravel()))
        pi = g[0] + 1e-6
        pi /= pi.sum()
        A = xi + 1e-6
        A /= A.sum(axis=1, keepdims=True)
        w = g.sum(axis=0) + 1e-9
        mu = (g.T @ X) / w[:, None]
        var = (g.T @ (X ** 2)) / w[:, None] - mu ** 2 + 1e-8
        if abs(ll - prev) < 1e-4 * abs(prev if math.isfinite(prev) else 1):
            break
        prev = ll
    # Viterbi
    logB = _logpdf(X, mu, var)
    logA = np.log(A)
    d = np.log(pi) + logB[0]
    bp = np.zeros((T, K), dtype=int)
    for t in range(1, T):
        s = d[:, None] + logA
        bp[t] = s.argmax(axis=0)
        d = s.max(axis=0) + logB[t]
    path = np.zeros(T, dtype=int)
    path[-1] = int(d.argmax())
    for t in range(T - 1, 0, -1):
        path[t - 1] = bp[t, path[t]]
    _ = rng
    return {"mu": mu, "var": var, "A": A, "pi": pi, "path": path, "post": g, "loglik": prev}


def _source(panel, syms) -> str:
    """DEMO if any input is demo, STALE if any is stale, else LIVE: never present demo or stale inputs as live."""
    srcs = {(panel.get(s) or {}).get("source") or "DEMO" for s in syms}
    for worst in ("DEMO", "STALE", "PROXY", "EOD"):
        if worst in srcs:
            return worst
    return "LIVE"


def regimes(symbol: str = "SPY") -> dict[str, Any]:
    panel = datapipe.cached_panel()
    p = panel.get(symbol)
    if not p:
        raise LookupError(f"{symbol} isn't in the research universe")
    f = p["features"]
    r = np.log(p["closes"][1:] / p["closes"][:-1])
    vol = f["vol_21d"][1:]
    ok = np.isfinite(vol)
    r, vol = r[ok], vol[ok]
    dates = [d for d, k in zip(p["dates"][1:], ok) if k]
    X = np.column_stack([r * 100, vol * 100])
    m = fit_hmm(X, K=3)
    order = np.argsort(m["mu"][:, 1])  # by volatility
    names = ["Calm", "Normal", "Stressed"]
    rank = {int(k): i for i, k in enumerate(order)}
    path = np.array([rank[int(s)] for s in m["path"]])
    post = m["post"][:, order]
    A = m["A"][np.ix_(order, order)]
    states = []
    for i, k in enumerate(order):
        mask = path == i
        runs, cur = [], 0
        for s in path:
            if s == i:
                cur += 1
            elif cur:
                runs.append(cur)
                cur = 0
        if cur:
            runs.append(cur)
        states.append({"name": names[i], "mean_daily_return": float(m["mu"][k, 0] / 100), "annual_vol": float(m["mu"][k, 1] / 100),
                       "share_of_days": float(mask.mean()), "expected_duration_days": float(1 / max(1e-9, 1 - A[i, i])),
                       "avg_run_days": float(np.mean(runs)) if runs else None, "annualised_return": float(np.mean(r[mask]) * 252) if mask.any() else None})
    cur = int(path[-1])
    since = len(path) - 1
    while since > 0 and path[since - 1] == cur:
        since -= 1
    step = max(1, len(dates) // 400)
    return {"symbol": symbol, "as_of": dates[-1], "current": {"state": names[cur], "probabilities": dict(zip(names, map(float, post[-1]))),
                                                              "since": dates[since], "days_in_state": len(path) - since,
                                                              "stay_probability": float(A[cur, cur])},
            "states": states, "transition_matrix": {"labels": names, "matrix": A.round(4).tolist()},
            "series": {"dates": dates[::step], "state": path[::step].tolist(), "close": [float(x) for x in p["closes"][1:][ok][::step]]},
            "source": _source(panel, [symbol]), "model": "3-state Gaussian HMM on daily log return and 21-day volatility, Baum-Welch fit, Viterbi path",
            "data_version": datapipe._panel_cache.get("version")}


# ── lead-lag ────────────────────────────────────────────────────────────────────────────────────
def _aligned(panel, a: str, b: str):
    pa, pb = panel[a], panel[b]
    ia = {d: i for i, d in enumerate(pa["dates"])}
    common = [d for d in pb["dates"] if d in ia]
    ib = {d: i for i, d in enumerate(pb["dates"])}
    ca = np.array([pa["closes"][ia[d]] for d in common])
    cb = np.array([pb["closes"][ib[d]] for d in common])
    return common, np.diff(np.log(ca)), np.diff(np.log(cb))


def _granger_f(y: np.ndarray, x: np.ndarray, p: int) -> tuple[float, int, int]:
    """F-statistic for adding p lags of x to an AR(p) model of y."""
    T = len(y)
    Y = y[p:]
    lag = lambda s, k: s[p - k:T - k]  # noqa: E731
    Xr = np.column_stack([np.ones(T - p)] + [lag(y, k) for k in range(1, p + 1)])
    Xu = np.column_stack([Xr] + [lag(x, k) for k in range(1, p + 1)])
    rss = lambda M: float(np.sum((Y - M @ np.linalg.lstsq(M, Y, rcond=None)[0]) ** 2))  # noqa: E731
    rr, ru = rss(Xr), rss(Xu)
    df1, df2 = p, len(Y) - Xu.shape[1]
    return ((rr - ru) / df1) / (ru / df2) if ru > 0 and df2 > 0 else 0.0, df1, df2


def _f_pvalue(F: float, d1: int, d2: int) -> float:
    """Upper tail of the F distribution via the regularised incomplete beta function (continued fraction)."""
    if F <= 0:
        return 1.0
    x = d2 / (d2 + d1 * F)
    a, b = d2 / 2, d1 / 2

    def betacf(a, b, x):
        qab, qap, qam = a + b, a + 1, a - 1
        c, d = 1.0, 1 - qab * x / qap
        d = 1 / (d if abs(d) > 1e-30 else 1e-30)
        h = d
        for m in range(1, 200):
            m2 = 2 * m
            aa = m * (b - m) * x / ((qam + m2) * (a + m2))
            d = 1 + aa * d
            d = 1 / (d if abs(d) > 1e-30 else 1e-30)
            c = 1 + aa / c if abs(1 + aa / c) > 1e-30 else 1e-30
            h *= d * c
            aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
            d = 1 + aa * d
            d = 1 / (d if abs(d) > 1e-30 else 1e-30)
            c = 1 + aa / c if abs(1 + aa / c) > 1e-30 else 1e-30
            de = d * c
            h *= de
            if abs(de - 1) < 3e-12:
                break
        return h
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    bt = math.exp(lbeta)
    return float(bt * betacf(a, b, x) / a) if x < (a + 1) / (a + b + 2) else float(1 - bt * betacf(b, a, 1 - x) / b)


LEADLAG_SETS = {
    "macro": ["SPY", "QQQ", "IWM", "TLT", "HYG", "GLD", "UUP", "USO", "EEM", "^VIX", "BTC-USD", "SMH"],
    "sectors": ["SPY", "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "SMH"],
    "megacaps": ["SPY", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA"],
}


def leadlag(universe: str = "macro", window_days: int = 504, max_lag: int = 5) -> dict[str, Any]:
    panel = datapipe.cached_panel()
    syms = [s for s in LEADLAG_SETS.get(universe, LEADLAG_SETS["macro"]) if s in panel]
    pairs = []
    for i, a in enumerate(syms):
        for b in syms[i + 1:]:
            dates, ra, rb = _aligned(panel, a, b)
            ra, rb = ra[-window_days:], rb[-window_days:]
            n = len(ra)
            if n < 120:
                continue
            ccf = {}
            for k in range(-max_lag, max_lag + 1):
                x, y = (ra[:n - k], rb[k:]) if k >= 0 else (ra[-k:], rb[:n + k])  # k>0: a leads b by k days
                ccf[k] = float(np.corrcoef(x, y)[0, 1]) if len(x) > 30 else 0.0
            best = max((k for k in ccf if k != 0), key=lambda k: abs(ccf[k]))
            leader, follower = (a, b) if best > 0 else (b, a)
            yv, xv = (rb, ra) if best > 0 else (ra, rb)
            F, d1, d2 = _granger_f(yv, xv, min(3, abs(best)))
            pval = _f_pvalue(F, d1, d2)
            pairs.append({"leader": leader, "follower": follower, "lag_days": abs(best), "lagged_corr": ccf[best], "same_day_corr": ccf[0],
                          "granger_f": round(F, 3), "p_value": pval, "significant": pval < 0.01 and abs(ccf[best]) > 2.5 / math.sqrt(n),
                          "ccf": {str(k): round(v, 4) for k, v in ccf.items()}, "observations": n})
    pairs.sort(key=lambda p: (not p["significant"], p["p_value"]))
    corr = []
    for a in syms:
        row = []
        for b in syms:
            if a == b:
                row.append(1.0)
                continue
            _, ra, rb = _aligned(panel, a, b)
            row.append(round(float(np.corrcoef(ra[-window_days:], rb[-window_days:])[0, 1]), 3) if len(ra) > 30 else None)
        corr.append(row)
    return {"universe": universe, "symbols": syms, "source": _source(panel, syms), "window_days": window_days, "pairs": pairs, "correlation": corr,
            "method": f"Daily log-return cross-correlations at lags -{max_lag}..+{max_lag} over the last {window_days} sessions; a pair counts as a "
                      "lead-lag relationship only if a Granger F-test (lags 1-3) rejects 'no added information' at 1% and the lagged correlation "
                      "clears 2.5/√n. Crypto trades on weekends, so its dates are aligned to US sessions.",
            "data_version": datapipe._panel_cache.get("version")}


# ── recurring market states ─────────────────────────────────────────────────────────────────────
STATE_FEATURES = [("SPY", "ret_21d", "S&P 500 1-month return"), ("SPY", "vol_21d", "S&P 500 volatility"), ("SPY", "dist_sma200", "S&P 500 vs 200-day"),
                  ("TLT", "ret_21d", "Long Treasuries 1-month"), ("HYG", "ret_21d", "High yield 1-month"), ("UUP", "ret_21d", "US dollar 1-month"),
                  ("USO", "ret_21d", "Oil 1-month"), ("GLD", "ret_21d", "Gold 1-month"), ("IWM", "ret_21d", "Small caps 1-month"),
                  ("^VIX", "dist_sma50", "VIX vs 50-day")]


def _kmeans(Z: np.ndarray, k: int, seed: int = 11, iters: int = 100) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    C = [Z[rng.integers(len(Z))]]
    for _ in range(1, k):  # k-means++
        d2 = np.min(((Z[:, None] - np.array(C)[None]) ** 2).sum(-1), axis=1)
        C.append(Z[rng.choice(len(Z), p=d2 / d2.sum())])
    C = np.array(C)
    for _ in range(iters):
        lab = ((Z[:, None] - C[None]) ** 2).sum(-1).argmin(1)
        newC = np.array([Z[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
        if np.allclose(newC, C):
            break
        C = newC
    return lab, C


def market_states(k: int = 6, analogs: int = 10, horizon: int = 21) -> dict[str, Any]:
    panel = datapipe.cached_panel()
    feats = [(s, f, lab) for s, f, lab in STATE_FEATURES if s in panel]
    if len(feats) < 5 or "SPY" not in panel:
        raise LookupError("Not enough cross-asset data for market states")
    common = sorted(set.intersection(*[set(panel[s]["dates"]) for s, _, _ in feats]))
    idx = {s: {d: i for i, d in enumerate(panel[s]["dates"])} for s, _, _ in feats}
    M = np.array([[panel[s]["features"][f][idx[s][d]] for s, f, _ in feats] for d in common])
    ok = np.all(np.isfinite(M), axis=1)
    M, dates = M[ok], [d for d, o in zip(common, ok) if o]
    mu, sd = M.mean(0), M.std(0) + 1e-12
    Z = (M - mu) / sd
    lab, C = _kmeans(Z, k)
    spy = panel["SPY"]
    si = {d: i for i, d in enumerate(spy["dates"])}
    fwd = np.array([spy["closes"][min(si[d] + horizon, len(spy["closes"]) - 1)] / spy["closes"][si[d]] - 1 if si[d] + horizon < len(spy["closes"]) else np.nan for d in dates])
    states = []
    for j in range(k):
        mask = lab == j
        top = np.argsort(-np.abs(C[j]))[:3]
        desc = ", ".join(f"{feats[t][2]} {'high' if C[j][t] > 0 else 'low'}" for t in top)
        runs, cur = [], 0
        for v in lab:
            if v == j:
                cur += 1
            elif cur:
                runs.append(cur)
                cur = 0
        if cur:
            runs.append(cur)
        fr = fwd[mask & np.isfinite(fwd)]
        states.append({"id": j, "description": desc, "share_of_days": float(mask.mean()), "episodes": len(runs), "avg_run_days": float(np.mean(runs)) if runs else None,
                       "centroid": {feats[t][2]: round(float(C[j][t]), 2) for t in range(len(feats))},
                       "spy_fwd_21d_median": float(np.median(fr)) if fr.size else None, "spy_fwd_21d_positive": float((fr > 0).mean()) if fr.size else None,
                       "last_seen": dates[int(np.where(mask)[0][-1])] if mask.any() else None})
    z_now = Z[-1]
    dist = np.sqrt(((Z[:-horizon] - z_now) ** 2).sum(1))
    near = np.argsort(dist)
    picked: list[int] = []
    for i in near:  # one analogue per 21-day window, so analogues aren't the same episode repeated
        if all(abs(i - j) > horizon for j in picked):
            picked.append(int(i))
        if len(picked) >= analogs:
            break
    an = [{"date": dates[i], "distance": round(float(dist[i]), 3), "state": int(lab[i]), "spy_fwd_21d": float(fwd[i]) if np.isfinite(fwd[i]) else None} for i in picked]
    fr = np.array([a["spy_fwd_21d"] for a in an if a["spy_fwd_21d"] is not None])
    return {"as_of": dates[-1], "source": _source(panel, [s for s, _, _ in feats]), "current_state": int(lab[-1]), "states": states, "features": [lab_ for _, _, lab_ in feats],
            "current_vector": {feats[t][2]: round(float(z_now[t]), 2) for t in range(len(feats))},
            "analogs": an, "analog_summary": {"median_spy_fwd_21d": float(np.median(fr)) if fr.size else None, "share_positive": float((fr > 0).mean()) if fr.size else None,
                                              "range": [float(fr.min()), float(fr.max())] if fr.size else None},
            "timeline": {"dates": dates[::5], "state": lab[::5].tolist()},
            "method": f"k-means (k={k}, k-means++) on {len(feats)} standardised cross-asset features per day; analogues are the closest past days by "
                      "Euclidean distance, at most one per 21-day window, with what the S&P 500 did over the next 21 sessions.",
            "data_version": datapipe._panel_cache.get("version")}


# ── microstructure (crypto, public Coinbase level-2 book) ───────────────────────────────────────
_micro: dict[str, tuple[float, dict]] = {}
CB = "https://api.exchange.coinbase.com/products/{pair}"


def book_metrics(bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> dict[str, Any]:
    """Imbalance at depth bands, spread, microprice. bids/asks: [(price, size)] best first."""
    bb, ba = bids[0][0], asks[0][0]
    mid = (bb + ba) / 2
    out: dict[str, Any] = {"best_bid": bb, "best_ask": ba, "mid": mid, "spread_bps": (ba - bb) / mid * 1e4}
    bs, as_ = bids[0][1], asks[0][1]
    out["microprice"] = (ba * bs + bb * as_) / (bs + as_) if bs + as_ else mid
    out["microprice_vs_mid_bps"] = (out["microprice"] / mid - 1) * 1e4
    for band in (0.001, 0.005, 0.01):
        bv = sum(p * s for p, s in bids if p >= mid * (1 - band))
        av = sum(p * s for p, s in asks if p <= mid * (1 + band))
        out[f"imbalance_{int(band * 1e4)}bps"] = (bv - av) / (bv + av) if bv + av else None
        out[f"depth_usd_{int(band * 1e4)}bps"] = bv + av
    return out


def trade_flow(trades: list[dict]) -> dict[str, Any]:
    """Coinbase 'side' is the maker side: side == 'sell' means the taker bought (aggressive buy)."""
    buy = sum(float(t["size"]) * float(t["price"]) for t in trades if t.get("side") == "sell")
    sell = sum(float(t["size"]) * float(t["price"]) for t in trades if t.get("side") == "buy")
    return {"aggressive_buy_usd": buy, "aggressive_sell_usd": sell, "flow_imbalance": (buy - sell) / (buy + sell) if buy + sell else None, "trades": len(trades)}


def microstructure(pair: str = "BTC-USD") -> dict[str, Any]:
    pair = pair.upper()
    if pair not in {"BTC-USD", "ETH-USD", "SOL-USD"}:
        return {"pair": pair, "available": False, "note": "Order-book data for stocks and ETFs needs a licensed depth-of-book feed. Crypto pairs (BTC-USD, ETH-USD, SOL-USD) use Coinbase's public book."}
    hit = _micro.get(pair)
    if hit and time.time() - hit[0] < 10:
        return hit[1]
    import httpx

    with httpx.Client(timeout=8, headers={"User-Agent": "IrradianceResearch/1.0 (support@irradiance.ai)"}) as c:
        book = c.get(CB.format(pair=pair) + "/book", params={"level": 2}).raise_for_status().json()
        trades = c.get(CB.format(pair=pair) + "/trades", params={"limit": 200}).raise_for_status().json()
    bids = [(float(p), float(s)) for p, s, *_ in book.get("bids", [])[:500]]
    asks = [(float(p), float(s)) for p, s, *_ in book.get("asks", [])[:500]]
    if not bids or not asks:
        raise LookupError("Empty order book")
    out = {"pair": pair, "available": True, "as_of": dt.datetime.now(dt.timezone.utc).isoformat(), **book_metrics(bids, asks), **trade_flow(trades),
           "ladder": {"bids": bids[:15], "asks": asks[:15]}, "source": "LIVE",
           "provider": {"label": "Coinbase Exchange public level-2 order book and trades", "url": f"https://exchange.coinbase.com/trade/{pair}"},
           "note": "Imbalance = (bid value − ask value) / total within each band around the mid. Positive means more resting buy interest. "
                   "Order books change by the millisecond and can be spoofed; treat these as a snapshot."}
    hist = _micro.get(pair + ":hist", (0, {"points": []}))[1]["points"]
    hist = [*hist, {"t": out["as_of"], "imb": out["imbalance_10bps"], "flow": out["flow_imbalance"], "mid": out["mid"]}][-120:]
    _micro[pair + ":hist"] = (time.time(), {"points": hist})
    out["recent"] = hist
    _micro[pair] = (time.time(), out)
    return out
