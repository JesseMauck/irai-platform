"""The three research engines, computed from live market data.

ADR Monitor   ADR price vs the local line converted at spot FX and the depositary ratio, net of the
              pair's structural basis (trailing median premium). z-score vs the pair's own history,
              mean-reversion half-life from an AR(1) fit, confidence, and reasons a gap is not tradable.
ETF Monitor   Price vs the fund's published NAV (prior close from the issuer via Yahoo). Free data has
              no intraday iNAV, so the tier is reported honestly as "NAV (prior close)".
Fundamental   Within each peer group: quality composite (ROE, operating margin, leverage) → regress
RV            log(EV/EBITDA, or P/E when EV/EBITDA is missing) on quality → the residual is how cheap the
              name is *for its quality*. Percentile → letter grade.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics
from typing import Any

import numpy as np

from . import service

# Quotes in minor units (pence, cents).
MINOR_UNITS = {"GBp": ("GBP", 100.0), "GBX": ("GBP", 100.0), "ILA": ("ILS", 100.0), "ZAc": ("ZAR", 100.0)}
STALE_MINUTES = 30


def fx_symbol(ccy: str) -> str | None:
    """Yahoo symbol giving USD per one unit of `ccy`."""
    return None if ccy == "USD" else f"{ccy}USD=X"


def to_major(price: float | None, ccy: str | None) -> tuple[float | None, str | None]:
    if price is None or ccy is None:
        return price, ccy
    if ccy in MINOR_UNITS:
        major, div = MINOR_UNITS[ccy]
        return price / div, major
    return price, ccy


def _age_minutes(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        t = dt.datetime.fromisoformat(iso)
    except ValueError:
        return None
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 60


def half_life(series: list[float]) -> float | None:
    """Mean-reversion half-life (in observations) from an AR(1) fit of Δx_t on x_{t-1}."""
    if len(series) < 20:
        return None
    x = np.asarray(series, dtype=float)
    lag, dx = x[:-1], np.diff(x)
    lag_c = lag - lag.mean()
    denom = float((lag_c ** 2).sum())
    if denom <= 0:
        return None
    b = float((lag_c * (dx - dx.mean())).sum() / denom)
    if b >= 0 or b <= -1:
        # b ≥ 0: not mean-reverting; b ≤ −1: the AR(1) coefficient 1+b is ≤ 0 (over-correcting/oscillating),
        # so a half-life isn't defined (log(1+b) would be a math domain error).
        return None
    return -math.log(2) / math.log(1 + b)


def letter_grade(pct: float) -> str:
    for cut, g in ((95, "A+"), (85, "A"), (75, "B+"), (60, "B"), (45, "C+"), (30, "C"), (15, "D")):
        if pct >= cut:
            return g
    return "F"


def _pct_rank(values: list[float], v: float) -> float:
    if len(values) <= 1:
        return 50.0
    below = sum(1 for x in values if x < v)
    equal = sum(1 for x in values if x == v) - 1
    return 100.0 * (below + 0.5 * equal) / (len(values) - 1)


# ── ADR ───────────────────────────────────────────────────────────────────────────────────────────
def adr_row(pair: dict[str, Any]) -> dict[str, Any]:
    service.demo_source().link_pair(pair["adr_symbol"], pair["local_symbol"], pair["ratio"])
    adr_sym, loc_sym, ratio = pair["adr_symbol"], pair["local_symbol"], float(pair["ratio"])
    adr_c, loc_c = service.chart(adr_sym), service.chart(loc_sym)
    aq, lq = adr_c["quote"], loc_c["quote"]
    loc_px, loc_ccy = to_major(lq["price"], lq.get("currency") or pair["local_currency"])
    fx_sym = fx_symbol(loc_ccy or pair["local_currency"])
    fx_c = service.chart(fx_sym) if fx_sym else None
    fx = fx_c["quote"]["price"] if fx_c else 1.0
    implied = loc_px * ratio * fx
    premium = aq["price"] / implied - 1 if implied else None

    # History: align ADR, local and FX daily closes on common dates.
    def series(c):
        return {h["date"]: h["close"] for h in (c or {}).get("history", [])}

    a_h, l_h = series(adr_c), series(loc_c)
    f_h = series(fx_c) if fx_c else None
    dates = sorted(set(a_h) & set(l_h) & (set(f_h) if f_h is not None else set(a_h)))
    loc_div = MINOR_UNITS.get(lq.get("currency") or "", (None, 1.0))[1]
    prem_hist = []
    for d in dates:
        imp = l_h[d] / loc_div * ratio * (f_h[d] if f_h is not None else 1.0)
        if imp:
            prem_hist.append({"date": d, "premium": a_h[d] / imp - 1})
    ph = [p["premium"] for p in prem_hist]
    # Sanity-check the configured depositary ratio against history: ADR / (local in USD) should hover
    # near the ratio. A large gap almost always means the ratio (or a split/bonus issue) is stale.
    implied_ratio = None
    ratios = [a_h[d] / (l_h[d] / loc_div * (f_h[d] if f_h is not None else 1.0)) for d in dates[-120:]
              if l_h[d] and (f_h is None or f_h[d])]
    if len(ratios) >= 20:
        implied_ratio = statistics.median(ratios)
    ratio_suspect = implied_ratio is not None and abs(implied_ratio / ratio - 1) > 0.25
    basis = statistics.median(ph) if len(ph) >= 20 else None
    dev = (premium - basis) if (premium is not None and basis is not None) else None
    sd = statistics.pstdev([p - basis for p in ph]) if basis is not None and len(ph) >= 20 else None
    z = dev / sd if dev is not None and sd else None
    hl = half_life([p - basis for p in ph]) if basis is not None else None

    fx_src = (fx_c or {"quote": {"source": "LIVE"}})["quote"].get("source")
    # End-of-day FX (ECB) is fine for the PROXY case; with an open local market it makes the estimate stale.
    sources = {aq.get("source"), lq.get("source"), "LIVE" if fx_src == "EOD" and not lq.get("market_open") else fx_src}
    sources = {"STALE" if s == "EOD" else s for s in sources}
    loc_age = _age_minutes(lq.get("market_time"))
    if "DEMO" in sources:
        src = "DEMO"
    elif "STALE" in sources:
        src = "STALE"
    elif lq.get("market_open") and (loc_age is None or loc_age <= STALE_MINUTES):
        src = "LIVE"
    elif not lq.get("market_open"):
        src = "PROXY"  # local market closed: fair value uses its last close at current FX
    else:
        src = "STALE"

    conf = 100.0
    if src == "PROXY":
        conf -= 12
    if src in ("STALE", "DEMO"):
        conf -= 35
    if len(ph) < 120:
        conf -= 15
    if sd and sd > 0.03:
        conf -= 10
    conf = max(5.0, min(99.0, conf))

    reasons = []
    cost = pair.get("round_trip_cost_bps", 35.0) / 1e4
    if dev is not None and abs(dev) < cost:
        reasons.append("Deviation smaller than estimated round-trip costs")
    if z is not None and abs(z) < 2:
        reasons.append("Deviation within the usual basis band (|z| < 2)")
    if not pair.get("shortable_local", True) and dev is not None and dev < 0:
        reasons.append("Local shares hard to borrow, so the discount cannot be hedged")
    if src == "STALE":
        reasons.append(f"Fair-value estimate older than {STALE_MINUTES} minutes")
    if src == "PROXY":
        reasons.append("Local market closed: no live hedge price")
    if src == "DEMO":
        reasons.append("Demo data: live feed unavailable")
    if basis is None:
        reasons.append("Not enough shared history to estimate the basis")
    if ratio_suspect:
        reasons.append(f"Depositary ratio needs review: prices imply about {implied_ratio:.3g} local shares per ADR, not {ratio:g}")
        conf = min(conf, 20.0)

    return {
        "adr_symbol": adr_sym, "local_symbol": loc_sym, "name": pair["name"], "country": pair["country"],
        "ratio": ratio, "local_market_open": bool(lq.get("market_open")),
        "adr_price": aq["price"], "adr_currency": aq.get("currency"), "local_price": loc_px, "local_currency": loc_ccy,
        "fx": fx, "fx_symbol": fx_sym, "implied_usd": implied,
        "premium": premium, "basis": basis, "deviation": dev, "z": z,
        "half_life_days": hl, "history_days": len(ph), "source": src, "confidence": conf,
        "implied_ratio": implied_ratio, "ratio_suspect": ratio_suspect, "sector": pair.get("sector"),
        "tradable": not reasons, "reasons": reasons, "as_of": aq.get("market_time"),
        "premium_history": prem_hist[-180:],
    }


def build_adr_monitor(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor

    for p in pairs:
        service.demo_source().link_pair(p["adr_symbol"], p["local_symbol"], p["ratio"])

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for pair, fut in [(p, ex.submit(adr_row, p)) for p in pairs]:
            try:
                rows.append(fut.result())
            except Exception as e:  # noqa: BLE001
                rows.append({"adr_symbol": pair["adr_symbol"], "local_symbol": pair["local_symbol"], "name": pair["name"],
                             "country": pair["country"], "ratio": pair["ratio"], "error": str(e), "source": "ERROR",
                             "tradable": False, "reasons": [f"Data unavailable: {e}"]})
    rows.sort(key=lambda r: -abs(r.get("z") or 0))
    return rows


# ── ETF ───────────────────────────────────────────────────────────────────────────────────────────
def etf_row(fund: dict[str, Any]) -> dict[str, Any]:
    q = service.quote(fund["symbol"])
    try:
        inf = service.info(fund["symbol"])
    except Exception:  # noqa: BLE001
        inf = {}
    nav = inf.get("nav_price")
    prem = q["price"] / nav - 1 if nav else None
    src = "DEMO" if "DEMO" in (q.get("source"), inf.get("source")) else q.get("source", "LIVE")
    flags = []
    if prem is not None and abs(prem) >= 0.005:
        flags.append("Premium/discount ≥ 0.5%: check creation/redemption costs and holdings liquidity")
    if nav is None:
        flags.append("Issuer NAV not available from the feed")
    return {"symbol": fund["symbol"], "name": inf.get("name") or fund["name"], "category": fund["category"],
            "price": q["price"], "change_pct": q.get("change_pct"), "nav": nav, "premium": prem,
            "tier": "NAV (prior close)" if nav else "Unavailable", "expense_ratio": inf.get("expense_ratio"),
            "total_assets": inf.get("total_assets"), "ytd_return": inf.get("ytd_return"),
            "source": src, "flags": flags, "as_of": q.get("market_time")}


def build_etf_monitor(funds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor

    rows = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for f, fut in [(f, ex.submit(etf_row, f)) for f in funds]:
            try:
                rows.append(fut.result())
            except Exception as e:  # noqa: BLE001
                rows.append({"symbol": f["symbol"], "name": f["name"], "category": f["category"], "error": str(e),
                             "source": "ERROR", "flags": [f"Data unavailable: {e}"]})
    rows.sort(key=lambda r: -abs(r.get("premium") or 0))
    return rows


# ── Fundamental RV ────────────────────────────────────────────────────────────────────────────────
def _z(vals: list[float | None]) -> list[float]:
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return [0.0 for _ in vals]
    m, s = statistics.mean(xs), statistics.pstdev(xs) or 1.0
    return [((v - m) / s) if v is not None else 0.0 for v in vals]


def score_peer_group(group: str, members: list[dict[str, Any]], infos: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Quality-adjusted relative value within one peer group."""
    rows = []
    for m in members:
        inf = infos.get(m["symbol"]) or {}
        ev = inf.get("ev_ebitda")
        pe = inf.get("trailing_pe")
        rows.append({"symbol": m["symbol"], "name": inf.get("name") or m["name"], "peer_group": group,
                     "sector": inf.get("sector"), "ev_ebitda": ev if ev and ev > 0 else None,
                     "pe": pe if pe and pe > 0 else None, "roe": inf.get("roe"),
                     "operating_margin": inf.get("operating_margin"),
                     "leverage": (inf.get("debt_to_equity") or 0) / 100 if inf.get("debt_to_equity") is not None else None,
                     "revenue_growth": inf.get("revenue_growth"), "source": inf.get("source", "LIVE")})
    # Use EV/EBITDA if most of the group has it, otherwise P/E.
    use = "ev_ebitda" if sum(1 for r in rows if r["ev_ebitda"]) >= max(3, len(rows) // 2) else "pe"
    label = "EV/EBITDA" if use == "ev_ebitda" else "P/E"
    roe_z = _z([min(r["roe"], 1.0) if r["roe"] is not None else None for r in rows])
    om_z = _z([r["operating_margin"] for r in rows])
    lev_z = _z([min(r["leverage"], 5.0) if r["leverage"] is not None else None for r in rows])
    for r, a, b, c in zip(rows, roe_z, om_z, lev_z):
        r["quality"] = (a + b - c) / 3
        r["multiple"], r["multiple_name"] = r[use], label
    valid = [r for r in rows if r["multiple"]]
    if len(valid) >= 3:
        x = np.array([r["quality"] for r in valid])
        y = np.log(np.array([r["multiple"] for r in valid]))
        slope, intercept = (np.polyfit(x, y, 1) if x.std() > 0 else (0.0, float(y.mean())))
        for r in valid:
            r["fitted_multiple"] = float(math.exp(intercept + slope * r["quality"]))
            r["residual"] = float(math.log(r["multiple"]) - (intercept + slope * r["quality"]))
        sd = statistics.pstdev([r["residual"] for r in valid]) or None
        for r in valid:
            r["residual_sigma"] = r["residual"] / sd if sd else None
        res = [-r["residual"] for r in valid]  # cheaper than justified → higher score
        for r in valid:
            r["rv_percentile"] = _pct_rank(res, -r["residual"])
    qs = [r["quality"] for r in rows]
    med = statistics.median([r["multiple"] for r in valid]) if valid else None
    for r in rows:
        r["quality_percentile"] = _pct_rank(qs, r["quality"])
        r["peer_median_multiple"] = med
        r.setdefault("residual", None)
        r.setdefault("residual_sigma", None)
        r.setdefault("rv_percentile", None)
        r["grade"] = letter_grade(r["rv_percentile"]) if r["rv_percentile"] is not None else "—"
        r["coverage"] = "High" if len(valid) >= 6 else "Medium" if len(valid) >= 4 else "Low"
        r["peer_count"] = len(rows)
    rows.sort(key=lambda r: -(r["rv_percentile"] if r["rv_percentile"] is not None else -1))
    return rows


def build_fundamental(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from .source import parallel

    syms = sorted({m["symbol"] for g in groups for m in g["members"]})
    infos = {k: v for k, v in parallel(service.info, syms).items() if not isinstance(v, Exception)}
    out = []
    for g in groups:
        out.extend(score_peer_group(g["name"], g["members"], infos))
    return out
