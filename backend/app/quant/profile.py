"""Quantitative profile for the Analyst Bot report: everything a professional trader checks before forming a view, computed
deterministically from daily OHLCV so the narrative can only interpret it, never invent it.

Sections: performance and relative strength, trend structure (moving averages, crosses), momentum (RSI, MACD, rate of
change), key levels (pivots, Donchian channels, 52-week range), volume and participation (relative volume, up/down
volume, OBV), volatility and risk (realised vol term structure, ATR, beta, correlation, VaR/CVaR, drawdowns, Sharpe,
Sortino), a 3-state volatility regime (HMM), return distribution, seasonality, statistical 1-month ranges, options
positioning when live, and which stress-tested Pattern Lab setups are present on the latest bar.

All figures describe the past. Nothing here is a forecast or a recommendation.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..market import service

SECTOR_ETF = {"Technology": "XLK", "Information Technology": "XLK", "Financial Services": "XLF", "Financials": "XLF", "Energy": "XLE",
              "Healthcare": "XLV", "Health Care": "XLV", "Industrials": "XLI", "Consumer Cyclical": "XLY", "Consumer Discretionary": "XLY",
              "Consumer Defensive": "XLP", "Consumer Staples": "XLP", "Utilities": "XLU", "Real Estate": "XLRE", "Basic Materials": "XLB",
              "Materials": "XLB", "Communication Services": "XLC"}
PERIODS = {"1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252, "3Y": 756}


def _f(x) -> float | None:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _sma(x: np.ndarray, n: int) -> np.ndarray:
    o = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.insert(x, 0, 0.0))
        o[n - 1:] = (cs[n:] - cs[:-n]) / n
    return o


def _ema(x: np.ndarray, n: int) -> np.ndarray:
    a = 2 / (n + 1)
    o = np.empty_like(x)
    o[0] = x[0]
    for i in range(1, len(x)):
        o[i] = a * x[i] + (1 - a) * o[i - 1]
    return o


def _rsi(c: np.ndarray, n: int = 14) -> np.ndarray:
    d = np.diff(c, prepend=c[0])
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    o = np.full(len(c), np.nan)
    if len(c) <= n:
        return o
    ag, al = up[1:n + 1].mean(), dn[1:n + 1].mean()
    for i in range(n + 1, len(c)):
        ag, al = (ag * (n - 1) + up[i]) / n, (al * (n - 1) + dn[i]) / n
        o[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return o


def _wilder(x: np.ndarray, n: int) -> np.ndarray:
    o = np.full(len(x), np.nan)
    if len(x) <= n:
        return o
    o[n] = np.nanmean(x[1:n + 1])
    for i in range(n + 1, len(x)):
        o[i] = (o[i - 1] * (n - 1) + x[i]) / n
    return o


def _adx(h, lo, c, n: int = 14) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    up, dn = np.diff(h, prepend=h[0]), -np.diff(lo, prepend=lo[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum.reduce([h - lo, np.abs(h - np.roll(c, 1)), np.abs(lo - np.roll(c, 1))])
    tr[0] = h[0] - lo[0]
    atr = _wilder(tr, n)
    pdi = 100 * _wilder(pdm, n) / atr
    ndi = 100 * _wilder(ndm, n) / atr
    dx = 100 * np.abs(pdi - ndi) / np.where(pdi + ndi > 0, pdi + ndi, np.nan)
    return _wilder(np.nan_to_num(dx), n), pdi, ndi


def _last(x: np.ndarray) -> float | None:
    return _f(x[-1]) if len(x) else None


def _down(series: list, k: int = 260) -> list:
    if len(series) <= k:
        return series
    step = len(series) / k
    idx = sorted({int(i * step) for i in range(k)} | {len(series) - 1})
    return [series[i] for i in idx]


def _align(a: dict[str, float], b: dict[str, float]) -> tuple[list[str], np.ndarray, np.ndarray]:
    ds = sorted(set(a) & set(b))
    return ds, np.array([a[d] for d in ds]), np.array([b[d] for d in ds])


def _closes(sym: str) -> tuple[dict[str, float], str | None]:
    try:
        b = service.bars(sym, "1d")
        return {x["t"][:10]: x["c"] for x in b["bars"]}, b["source"]
    except Exception:  # noqa: BLE001
        return {}, None


def build(symbol: str, info: dict[str, Any] | None = None) -> dict[str, Any]:
    symbol = service.normalise_symbol(symbol)
    raw = service.bars(symbol, "1d")
    bars = raw["bars"]
    if raw["source"] == "DEMO" and bars:  # demo bars and demo quotes come from different generators: anchor bars to the quote
        try:
            px = service.quote(symbol).get("price")
            if px:
                k = px / bars[-1]["c"]
                bars = [{**b, "o": b["o"] * k, "h": b["h"] * k, "l": b["l"] * k, "c": b["c"] * k} for b in bars]
        except Exception:  # noqa: BLE001
            pass
    if len(bars) < 60:
        raise LookupError(f"Not enough history for {symbol}")
    dates = [b["t"][:10] for b in bars]
    h = np.array([b["h"] for b in bars], float)
    lo = np.array([b["l"] for b in bars], float)
    c = np.array([b["c"] for b in bars], float)
    v = np.array([b.get("v") or 0 for b in bars], float)
    n = len(c)
    lr = np.diff(np.log(c))
    info = info or {}
    out: dict[str, Any] = {"symbol": symbol, "as_of": dates[-1], "source": raw["source"], "bars": n, "from": dates[0]}

    # ── performance & relative strength ──
    spy, spy_src = _closes("SPY") if symbol != "SPY" else ({d: x for d, x in zip(dates, c)}, raw["source"])
    sec_etf = SECTOR_ETF.get(info.get("sector") or "")
    sec, _ = _closes(sec_etf) if sec_etf and sec_etf != symbol else ({}, None)
    me = dict(zip(dates, c))

    def per(series: dict[str, float], k: int) -> float | None:
        ds = sorted(series)
        return series[ds[-1]] / series[ds[-1 - k]] - 1 if len(ds) > k else None
    ytd_base = next((c[i - 1] for i in range(1, n) if dates[i][:4] == dates[-1][:4] and dates[i - 1][:4] != dates[-1][:4]), None)
    perf = []
    for lab, k in PERIODS.items():
        perf.append({"period": lab, "stock": per(me, k), "spy": per(spy, k) if spy else None, "sector": per(sec, k) if sec else None})
    perf.insert(4, {"period": "YTD", "stock": c[-1] / ytd_base - 1 if ytd_base else None, "spy": None, "sector": None})
    out["performance"] = {"rows": perf, "benchmark": "SPY", "sector_etf": sec_etf}
    if spy:
        ds, a, b = _align(me, spy)
        ds, a, b = ds[-504:], a[-504:], b[-504:]
        if len(ds) > 30:
            rs = (a / a[0]) / (b / b[0])
            out["relative_strength"] = {"dates": _down(ds), "ratio": _down([float(x) for x in rs]),
                                        "change_3m": float(rs[-1] / rs[-64] - 1) if len(rs) > 64 else None,
                                        "rs_rank_note": "Ratio of the stock to SPY, rebased to 1.0; rising means outperforming."}

    # ── trend structure ──
    s20, s50, s200 = _sma(c, 20), _sma(c, 50), _sma(c, 200)
    e21 = _ema(c, 21)
    cross = None
    for i in range(n - 1, 200, -1):
        if np.isfinite(s50[i]) and np.isfinite(s200[i]) and np.isfinite(s50[i - 1]) and np.isfinite(s200[i - 1]):
            if (s50[i] > s200[i]) != (s50[i - 1] > s200[i - 1]):
                cross = {"type": "golden cross" if s50[i] > s200[i] else "death cross", "date": dates[i], "sessions_ago": n - 1 - i}
                break
    slope200 = (s200[-1] / s200[-21] - 1) if n > 221 and np.isfinite(s200[-21]) else None
    adx, pdi, ndi = _adx(h, lo, c)
    stack = "bullish stack (price > 20 > 50 > 200-day)" if c[-1] > s20[-1] > s50[-1] > s200[-1] else \
            "bearish stack (price < 20 < 50 < 200-day)" if c[-1] < s20[-1] < s50[-1] < s200[-1] else "mixed moving-average stack"
    out["trend"] = {"price": float(c[-1]), "sma20": _last(s20), "sma50": _last(s50), "sma200": _last(s200), "ema21": _last(e21),
                    "vs_sma20": float(c[-1] / s20[-1] - 1) if np.isfinite(s20[-1]) else None,
                    "vs_sma50": float(c[-1] / s50[-1] - 1) if np.isfinite(s50[-1]) else None,
                    "vs_sma200": float(c[-1] / s200[-1] - 1) if np.isfinite(s200[-1]) else None,
                    "sma200_slope_1m": slope200, "last_cross": cross, "ma_stack": stack,
                    "adx14": _last(adx), "plus_di": _last(pdi), "minus_di": _last(ndi),
                    "trend_strength": None if not np.isfinite(adx[-1]) else "strong trend" if adx[-1] >= 25 else "weak / range-bound" if adx[-1] < 20 else "developing trend"}
    k = min(n, 504)
    out["chart"] = {"dates": _down(dates[-k:]), "close": _down([float(x) for x in c[-k:]]),
                    "sma50": _down([_f(x) for x in s50[-k:]]), "sma200": _down([_f(x) for x in s200[-k:]]),
                    "volume": _down([float(x) for x in v[-k:]])}

    # ── momentum ──
    rsi = _rsi(c)
    m12, m26 = _ema(c, 12), _ema(c, 26)
    macd = m12 - m26
    sig = _ema(macd, 9)
    k6 = min(n, 126)
    out["momentum"] = {"rsi14": _last(rsi), "rsi_state": None if not np.isfinite(rsi[-1]) else "overbought" if rsi[-1] > 70 else "oversold" if rsi[-1] < 30 else "neutral",
                       "macd": _last(macd), "macd_signal": _last(sig), "macd_hist": float(macd[-1] - sig[-1]),
                       "macd_state": "above signal (positive momentum)" if macd[-1] > sig[-1] else "below signal (negative momentum)",
                       "roc_21": float(c[-1] / c[-22] - 1) if n > 22 else None, "roc_63": float(c[-1] / c[-64] - 1) if n > 64 else None,
                       "mom_12_1": float(c[-22] / c[-253] - 1) if n > 253 else None,
                       "series": {"dates": dates[-k6:], "rsi": [_f(x) for x in rsi[-k6:]], "macd_hist": [float(x) for x in (macd - sig)[-k6:]]}}

    # ── key levels ──
    hi52, lo52 = float(h[-252:].max()), float(lo[-252:].min())
    piv_p = (h[-2] + lo[-2] + c[-2]) / 3 if n > 2 else None
    swings_hi = [float(h[i]) for i in range(max(2, n - 120), n - 2) if h[i] == h[i - 2:i + 3].max()]
    swings_lo = [float(lo[i]) for i in range(max(2, n - 120), n - 2) if lo[i] == lo[i - 2:i + 3].min()]
    res = sorted({round(x, 2) for x in swings_hi if x > c[-1]})[:3]
    sup = sorted({round(x, 2) for x in swings_lo if x < c[-1]}, reverse=True)[:3]
    levels = [{"level": "52-week high", "price": hi52}, *[{"level": f"Swing resistance {i + 1}", "price": x} for i, x in enumerate(res)],
              {"level": "20-day high (Donchian)", "price": float(h[-20:].max())}, {"level": "Last close", "price": float(c[-1])},
              {"level": "Classic pivot (prior bar)", "price": float(piv_p) if piv_p else None},
              {"level": "20-day low (Donchian)", "price": float(lo[-20:].min())}, *[{"level": f"Swing support {i + 1}", "price": x} for i, x in enumerate(sup)],
              {"level": "50-day average", "price": _last(s50)}, {"level": "200-day average", "price": _last(s200)}, {"level": "52-week low", "price": lo52}]
    levels = [lv for lv in levels if lv["price"]]
    for lv in levels:
        lv["distance"] = lv["price"] / c[-1] - 1
    levels.sort(key=lambda x: -x["price"])
    out["levels"] = {"rows": levels, "pct_of_52w_range": float((c[-1] - lo52) / (hi52 - lo52)) if hi52 > lo52 else None,
                     "from_52w_high": float(c[-1] / hi52 - 1), "from_52w_low": float(c[-1] / lo52 - 1)}

    # ── volume & participation ──
    if (v > 0).sum() > n * 0.8:
        up_v = v[-20:][np.diff(c[-21:]) > 0].sum()
        dn_v = v[-20:][np.diff(c[-21:]) < 0].sum()
        obv = np.cumsum(np.sign(np.diff(c, prepend=c[0])) * v)
        out["volume"] = {"avg_20d": float(v[-20:].mean()), "avg_3m": float(v[-63:].mean()), "relative_volume": float(v[-1] / v[-20:].mean()) if v[-20:].mean() else None,
                         "rvol_20_vs_3m": float(v[-20:].mean() / v[-63:].mean()) if v[-63:].mean() else None,
                         "up_down_volume_20d": float(up_v / dn_v) if dn_v else None,
                         "obv_trend_1m": "rising" if obv[-1] > obv[-21] else "falling",
                         "dollar_volume_20d": float((v[-20:] * c[-20:]).mean())}
    else:
        out["volume"] = None

    # ── volatility & risk ──
    def rv(k):
        return float(np.std(lr[-k:], ddof=1) * math.sqrt(252)) if len(lr) > k else None
    tr = np.maximum.reduce([h[1:] - lo[1:], np.abs(h[1:] - c[:-1]), np.abs(lo[1:] - c[:-1])])
    atr14 = float(tr[-14:].mean())
    roll20 = np.array([np.std(lr[i - 20:i], ddof=1) for i in range(20, len(lr) + 1)]) * math.sqrt(252)
    vol_pct = float((roll20[-253:-1] < roll20[-1]).mean()) if len(roll20) > 60 else None
    r1y = lr[-252:]
    peak = np.maximum.accumulate(c[-252:])
    dd = c[-252:] / peak - 1
    risk: dict[str, Any] = {"vol_10d": rv(10), "vol_20d": rv(20), "vol_60d": rv(60), "vol_1y": rv(252), "vol_percentile_1y": vol_pct,
                            "atr14": atr14, "atr_pct": atr14 / c[-1], "max_drawdown_1y": float(dd.min()), "current_drawdown": float(dd[-1]),
                            "var95_1d": float(-np.quantile(r1y, 0.05)), "cvar95_1d": float(-r1y[r1y <= np.quantile(r1y, 0.05)].mean()),
                            "best_day_1y": float(r1y.max()), "worst_day_1y": float(r1y.min()),
                            "sharpe_1y": float(r1y.mean() / r1y.std(ddof=1) * math.sqrt(252)) if r1y.std() else None,
                            "sortino_1y": float(r1y.mean() / (r1y[r1y < 0].std(ddof=1) or 1) * math.sqrt(252)) if (r1y < 0).sum() > 2 else None,
                            "skew_1y": float(((r1y - r1y.mean()) ** 3).mean() / r1y.std() ** 3) if r1y.std() else None,
                            "kurtosis_1y": float(((r1y - r1y.mean()) ** 4).mean() / r1y.std() ** 4 - 3) if r1y.std() else None,
                            "up_days_1y": float((r1y > 0).mean())}
    if spy and symbol != "SPY":
        ds, a, b = _align(me, spy)
        ra, rb = np.diff(np.log(a[-253:])), np.diff(np.log(b[-253:]))
        if len(ra) > 60:
            risk["beta_1y"] = float(np.cov(ra, rb)[0, 1] / np.var(rb, ddof=1))
            risk["correlation_1y"] = float(np.corrcoef(ra, rb)[0, 1])
            up, dn = rb > 0, rb < 0
            risk["upside_capture"] = float(ra[up].mean() / rb[up].mean()) if up.any() else None
            risk["downside_capture"] = float(ra[dn].mean() / rb[dn].mean()) if dn.any() else None
    risk["drawdown_series"] = {"dates": _down(dates[-252:], 200), "dd": _down([float(x) for x in dd], 200)}
    risk["vol_series"] = {"dates": _down(dates[-len(roll20):][-252:], 200), "vol": _down([float(x) for x in roll20[-252:]], 200)}
    edges = np.linspace(-0.08, 0.08, 33)
    hist, _ = np.histogram(np.clip(r1y, -0.0799, 0.0799), bins=edges)
    risk["distribution"] = {"edges": [float(x) for x in edges], "counts": hist.tolist()}
    out["risk"] = risk

    # ── volatility regime (3-state HMM on this symbol) ──
    try:
        from .patterns import fit_hmm
        k2 = min(len(lr), 1260)
        vol21 = np.array([np.std(lr[max(0, i - 21):i], ddof=1) if i > 5 else np.nan for i in range(len(lr) - k2 + 1, len(lr) + 1)]) * math.sqrt(252)
        X = np.column_stack([lr[-k2:] * 100, np.nan_to_num(vol21, nan=np.nanmean(vol21)) * 100])
        m = fit_hmm(X[5:], K=3, iters=40)
        order = np.argsort(m["mu"][:, 1])
        names = ["Calm", "Normal", "Stressed"]
        rank = {int(s): i for i, s in enumerate(order)}
        path = [rank[int(s)] for s in m["path"]]
        cur = path[-1]
        run = 1
        while run < len(path) and path[-1 - run] == cur:
            run += 1
        A = m["A"][np.ix_(order, order)]
        rd = dates[-len(path):]
        out["regime"] = {"current": names[cur], "days_in_regime": run, "stay_probability": float(A[cur, cur]),
                         "probabilities": dict(zip(names, map(float, m["post"][-1][order]))),
                         "states": [{"name": names[i], "annual_vol": float(m["mu"][order[i], 1] / 100), "share": float(np.mean(np.array(path) == i))} for i in range(3)],
                         "strip": {"dates": _down(rd, 180), "state": _down(path, 180)}}
    except Exception:  # noqa: BLE001
        out["regime"] = None

    # ── seasonality (calendar months) ──
    months: dict[int, list[float]] = {}
    ym = {}
    for d, px in zip(dates, c):
        ym[d[:7]] = px
    keys = sorted(ym)
    mret = {keys[i]: ym[keys[i]] / ym[keys[i - 1]] - 1 for i in range(1, len(keys))}
    for k_, r in mret.items():
        months.setdefault(int(k_[5:]), []).append(r)
    out["seasonality"] = {"by_month": [{"month": mth, "avg": float(np.mean(months[mth])), "median": float(np.median(months[mth])),
                                        "hit_rate": float(np.mean(np.array(months[mth]) > 0)), "years": len(months[mth])} for mth in sorted(months)],
                          "recent": [{"month": k_, "ret": float(r)} for k_, r in list(mret.items())[-24:]]}

    # ── statistical ranges (not targets) ──
    sig_d = (rv(20) or rv(60) or 0.3) / math.sqrt(252)
    rng = []
    for lab, days in (("1 week", 5), ("1 month", 21), ("3 months", 63)):
        s = sig_d * math.sqrt(days)
        rng.append({"horizon": lab, "minus_2sd": float(c[-1] * math.exp(-2 * s)), "minus_1sd": float(c[-1] * math.exp(-s)),
                    "plus_1sd": float(c[-1] * math.exp(s)), "plus_2sd": float(c[-1] * math.exp(2 * s)), "one_sd_pct": float(math.exp(s) - 1)})
    out["ranges"] = {"basis": "20-day realised volatility, lognormal; about 68% of outcomes fall within ±1σ and 95% within ±2σ if volatility holds", "rows": rng}

    # ── options & positioning ──
    out["options"] = None
    try:
        from ..routers.discover import options as opt

        oc = opt(symbol)
        if oc.get("summary"):
            sm = oc["summary"]
            out["options"] = {"expiry": oc.get("expiry"), "days": oc.get("days_to_expiry"), "atm_iv": sm.get("atm_iv"), "expected_move_pct": sm.get("expected_move_pct"),
                              "expected_move": sm.get("expected_move"), "put_call_volume": sm.get("put_call_volume"), "put_call_oi": sm.get("put_call_oi"),
                              "max_pain": sm.get("max_pain"), "iv_vs_realised": (sm["atm_iv"] / rv(20)) if sm.get("atm_iv") and rv(20) else None,
                              "unusual": [{k_: u.get(k_) for k_ in ("type", "strike", "volume", "open_interest", "iv")} for u in (oc.get("unusual") or [])[:6]],
                              "source": oc.get("source")}
    except Exception:  # noqa: BLE001
        pass
    out["positioning"] = {"short_percent_float": _f(info.get("short_percent_float")), "held_by_institutions": _f(info.get("held_by_institutions")),
                          "held_by_insiders": _f(info.get("held_by_insiders")), "float_shares": _f(info.get("float_shares"))}

    # ── stress-tested patterns present today ──
    out["patterns"] = _patterns_today(symbol, bars)

    # ── factor scorecard (descriptive) ──
    def lab3(x, hi, lo_, rev=False):
        if x is None:
            return "n/a"
        if rev:
            x, hi, lo_ = -x, -lo_, -hi
        return "Positive" if x >= hi else "Negative" if x <= lo_ else "Neutral"
    t = out["trend"]
    out["scorecard"] = [
        {"factor": "Trend", "read": lab3((t["vs_sma200"] or 0) + (t["vs_sma50"] or 0), 0.05, -0.05), "evidence": f"{t['ma_stack']}; ADX {t['adx14']:.0f}" if t["adx14"] else t["ma_stack"]},
        {"factor": "Momentum", "read": lab3(out["momentum"]["mom_12_1"], 0.10, -0.05), "evidence": f"12-1 month momentum {_pc(out['momentum']['mom_12_1'])}; RSI {out['momentum']['rsi14']:.0f}" if out["momentum"]["rsi14"] else "n/a"},
        {"factor": "Relative strength", "read": lab3((out.get("relative_strength") or {}).get("change_3m"), 0.03, -0.03), "evidence": f"vs SPY over 3 months {_pc((out.get('relative_strength') or {}).get('change_3m'))}"},
        {"factor": "Volatility", "read": lab3(vol_pct, 0.7, 0.3, rev=True), "evidence": f"20-day vol {_pc(rv(20), sign=False)}, {ordinal(vol_pct)} percentile of the past year"},
        {"factor": "Participation", "read": lab3(((out["volume"] or {}).get("up_down_volume_20d") or 1) - 1, 0.2, -0.2), "evidence": f"up/down volume {(out['volume'] or {}).get('up_down_volume_20d') or 0:.2f} over 20 days" if out["volume"] else "no volume data"},
    ]
    return out


def ordinal(p: float | None) -> str:
    if p is None:
        return "n/a"
    n = int(round(p * 100))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _pc(x, sign=True):
    return "n/a" if x is None else (f"{x * 100:+.1f}%" if sign else f"{x * 100:.1f}%")


def _patterns_today(symbol: str, bars: list[dict]) -> dict[str, Any] | None:
    """Which Pattern Lab setups trigger on the latest daily bar, with the latest grid verdict for the matching asset class."""
    try:
        from sqlalchemy import select

        from ..db import SessionLocal
        from ..models import PatternStudy
        from . import engine as eng

        f = eng.normalise(bars)
        ac = next((k for k, v in eng.ASSET_CLASSES.items() if symbol in v["symbols"]), "etfs" if symbol in ("SPY", "QQQ", "IWM", "DIA") else
                  "crypto" if symbol.endswith("-USD") else "fx" if symbol.endswith("=X") else "commodities" if symbol.endswith("=F") else "equities")
        verdicts = {}
        with SessionLocal() as db:
            g = db.scalar(select(PatternStudy).where(PatternStudy.kind == "grid").order_by(PatternStudy.created_at.desc()))
            for o in (g.results["results"] if g and g.results else []):
                if o.get("asset_class") == ac and o.get("timeframe") == "1d":
                    verdicts[o["pattern"]] = {"verdict": o.get("verdict"), "checks": f"{o.get('checks_passed')}/{o.get('checks_total')}" if o.get("checks_total") else None,
                                              "mean_r": (o.get("all") or {}).get("mean_r"), "events": o.get("events")}
        rows = []
        for p in eng.PATTERNS:
            if p.needs_volume and not np.isfinite(f["vol_z"]).any():
                continue
            m = p.rule(f, p.params)
            last = int(np.flatnonzero(m)[-1]) if m.any() else None
            rows.append({"pattern": p.name, "id": p.id, "active": bool(m[-1]), "last_seen": bars[last]["t"][:10] if last is not None else None,
                         "definition": eng.describe(p), **verdicts.get(p.id, {})})
        return {"asset_class": ac, "asset_class_label": eng.ASSET_CLASSES[ac]["label"], "rows": rows, "study_at": g.created_at.isoformat() if g else None}
    except Exception:  # noqa: BLE001
        return None
