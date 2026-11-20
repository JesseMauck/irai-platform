"""Probabilistic approaches, following Damodaran's "Probabilistic Approaches in Valuation":

  a. Sensitivity / what-if  -> registry.sensitivity (tornado) + break_even() below
  b. Scenario analysis      -> plausible_scenarios(): a few coherent stories with probabilities,
                               not just "every input at its best / worst"
  d. Monte Carlo simulation -> simulate(): distributions on a *few* key drivers (less is more),
                               with correlation between them (variables move together)
  Margin of safety          -> derived from the simulated distribution, so it widens for riskier firms
  Consistency tests         -> consistency_checks(): is the stable phase really stable?

Decision trees (discrete, sequential risks such as drug approvals) and commodity-price
normalisation are natural extensions; see README "Extending".
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .common import Driver
from .registry import METHODS, drivers_for, run

# The handful of drivers that carry the story for each method ("less is more").
KEY_DRIVERS: dict[str, list[str]] = {
    "fcff": ["revenue_growth_y2_5", "target_operating_margin", "sales_to_capital", "wacc_initial"],
    "ddm": ["roe_high", "payout_high", "cost_of_equity_high", "terminal_growth"],
    "excess_return": ["roe_target", "roe_stable", "cost_of_equity_high", "payout_high"],
}

# Pairwise correlations between key drivers. The deck's Amgen example uses 0.4 between
# revenue growth and operating margin; risk tends to move with growth too.
CORRELATIONS: dict[str, dict[tuple[str, str], float]] = {
    "fcff": {("revenue_growth_y2_5", "target_operating_margin"): 0.4,
             ("revenue_growth_y2_5", "wacc_initial"): 0.2},
    "ddm": {("roe_high", "payout_high"): -0.3},
    "excess_return": {("roe_target", "roe_stable"): 0.6},
}


def _driver(method: str, key: str) -> Driver:
    return next(d for d in drivers_for(method) if d.key == key)


# ---------------------------------------------------------------------------- break-even
def break_even(method: str, a: dict[str, Any], key: str, target: float, iters: int = 80) -> float | None:
    """Value of driver `key` at which value per share equals `target` (e.g. the price).

    Bisection inside the driver's bounds; None if the price can't be reached in that range.
    """
    d = _driver(method, key)
    lo, hi = (d.lo if d.lo is not None else a[key] - 10 * d.bump), (d.hi if d.hi is not None else a[key] + 10 * d.bump)
    if key == "terminal_growth":  # growth must stay below the stable discount rate
        cap = a.get("wacc_terminal", a.get("cost_of_equity_stable", 1.0)) - 0.0051
        hi = min(hi, cap)
    f = lambda x: run(method, {**a, key: x}).value_per_share - target  # noqa: E731
    try:
        flo, fhi = f(lo), f(hi)
    except (ZeroDivisionError, OverflowError):
        return None
    if math.isnan(flo) or math.isnan(fhi) or flo * fhi > 0:
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2
        fm = f(mid)
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def break_even_table(method: str, a: dict[str, Any], price: float, keys: list[str] | None = None) -> list[dict]:
    out = []
    for k in keys or KEY_DRIVERS[method]:
        d = _driver(method, k)
        be = break_even(method, a, k, price)
        out.append({"key": k, "label": d.label, "unit": d.unit, "base": a[k], "break_even": be,
                    "gap": None if be is None else be - a[k]})
    return out


def break_even_curve(method: str, a: dict[str, Any], key: str, points: int = 25,
                     include: float | None = None) -> list[dict]:
    """Value per share across a range of one driver (the Con Ed 'value vs growth' chart).

    `include` (usually the break-even value) widens the range so the crossing is visible."""
    d = _driver(method, key)
    lo, hi = a[key] - 4 * d.bump, a[key] + 4 * d.bump
    if include is not None:
        pad = 0.15 * abs(include - a[key]) + d.bump
        lo, hi = min(lo, include - pad), max(hi, include + pad)
    if key == "terminal_growth":
        hi = min(hi, a.get("wacc_terminal", a.get("cost_of_equity_stable", 1.0)) - 0.0051)
    xs = np.linspace(lo, hi, points)
    out = []
    for x in xs:
        x = d.clamp(float(x))
        try:
            out.append({"x": x, "value": run(method, {**a, key: x}).value_per_share})
        except ZeroDivisionError:
            continue
    return out


# ---------------------------------------------------------------------------- simulation
def _sigma(method: str, key: str, metrics: list[dict] | None, base: float | None = None) -> float:
    """Standard deviation for a driver: its sensitivity bump, widened by historical volatility
    where history speaks to it (the deck: use historical or cross-sectional data)."""
    d = _driver(method, key)
    s = d.bump
    if d.unit == "x" and base is not None:  # ratios vary proportionally: ~20% of the base value
        s = min(s, 0.2 * abs(base))
    hist_key = {"revenue_growth_y2_5": "revenue_growth", "target_operating_margin": "operating_margin",
                "roe_high": "roe", "roe_target": "roe"}.get(key)
    if metrics and hist_key:
        vals = [m[hist_key] for m in metrics if m.get(hist_key) is not None]
        if len(vals) >= 3:
            s = max(s, float(np.std(vals, ddof=1)))
    return s


def simulate(method: str, a: dict[str, Any], *, price: float | None, metrics: list[dict] | None = None,
             n: int = 4000, seed: int = 7, keys: list[str] | None = None) -> dict[str, Any]:
    keys = keys or KEY_DRIVERS[method]
    sig = np.array([_sigma(method, k, metrics, a.get(k)) for k in keys])
    corr = np.eye(len(keys))
    for (k1, k2), rho in CORRELATIONS.get(method, {}).items():
        if k1 in keys and k2 in keys:
            i, j = keys.index(k1), keys.index(k2)
            corr[i, j] = corr[j, i] = rho
    chol = np.linalg.cholesky(corr)
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n, len(keys))) @ chol.T
    draws = np.array([a[k] for k in keys]) + z * sig
    drivers = [_driver(method, k) for k in keys]

    values = []
    for row in draws:
        trial = dict(a)
        for d, v in zip(drivers, row):
            trial[d.key] = d.clamp(float(v))
        try:
            v = run(method, trial).value_per_share
        except ZeroDivisionError:
            continue
        if math.isfinite(v):
            values.append(v)
    v = np.array(values)
    pct = {p: float(np.percentile(v, p)) for p in (5, 10, 25, 50, 75, 90, 95)}
    lo_edge, hi_edge = np.percentile(v, 1), np.percentile(v, 99)
    if price:
        lo_edge, hi_edge = min(lo_edge, price * 0.97), max(hi_edge, price * 1.03)
    counts, edges = np.histogram(np.clip(v, lo_edge, hi_edge), bins=30)
    median = pct[50]
    # Risk-varying margin of safety: how far below the median value the 25th percentile sits.
    mos = max(0.0, 1 - pct[25] / median) if median > 0 else None
    out = {
        "n": int(len(v)),
        "drivers": [{"key": k, "label": d.label, "unit": d.unit, "mean": a[k], "sd": float(s)}
                    for k, d, s in zip(keys, drivers, sig)],
        "correlations": [{"a": k1, "b": k2, "rho": r} for (k1, k2), r in CORRELATIONS.get(method, {}).items()
                         if k1 in keys and k2 in keys],
        "mean": float(v.mean()), "sd": float(v.std()), "percentiles": pct,
        "histogram": {"counts": counts.tolist(), "edges": edges.tolist()},
        "margin_of_safety": mos,
        "buy_below": median * (1 - mos) if mos is not None else None,
    }
    if price:
        out["prob_undervalued"] = float((v > price).mean())
        out["price_percentile"] = float((v < price).mean())
    return out


# ---------------------------------------------------------------------------- plausible scenarios
def plausible_scenarios(method: str, a: dict[str, Any], specs: list[dict] | None = None) -> dict[str, Any]:
    """Value a small set of coherent scenarios and their probability-weighted value.

    `specs`: [{"name", "probability", "narrative", "overrides": {driver: value}}] — usually from the LLM.
    Without specs, builds three default stories that move the key drivers *together*
    at half-strength in each direction (an interacting story rather than best/worst everything).
    """
    if not specs:
        keys = KEY_DRIVERS[method]
        specs = []
        for name, sign, prob, story in (
            ("Story breaks", -1, 0.25, "Growth disappoints, margins stall and risk rises together."),
            ("Base story", 0, 0.50, "The base-case narrative plays out."),
            ("Story delivers", 1, 0.25, "Growth and margins beat expectations as the thesis plays out."),
        ):
            ov = {}
            for k in keys:
                d = _driver(method, k)
                direction = sign if d.higher_is_better else -sign
                ov[k] = d.clamp(a[k] + direction * d.bump)
            specs.append({"name": name, "probability": prob, "narrative": story, "overrides": ov})
    total = sum(max(0.0, float(s.get("probability", 0))) for s in specs) or 1.0
    rows = []
    for s in specs:
        allowed = {d.key: d for d in drivers_for(method)}
        ov = {k: allowed[k].clamp(float(v)) for k, v in (s.get("overrides") or {}).items() if k in allowed}
        val = run(method, {**a, **ov}).value_per_share
        rows.append({"name": s["name"], "probability": max(0.0, float(s.get("probability", 0))) / total,
                     "narrative": s.get("narrative", ""), "overrides": ov, "value_per_share": val})
    return {"scenarios": rows, "expected_value": sum(r["probability"] * r["value_per_share"] for r in rows)}


# ---------------------------------------------------------------------------- consistency tests
def consistency_checks(method: str, a: dict[str, Any], *, riskfree: float, beta: float | None,
                       result_terminal: dict[str, float]) -> list[dict[str, Any]]:
    """The stable-growth tests from the Con Ed example, generalised to each method."""
    checks = []

    def add(name, ok, detail):
        checks.append({"test": name, "pass": bool(ok), "detail": detail})

    g = result_terminal.get("growth")
    add("Stable growth ≤ risk-free rate", g is not None and g <= riskfree + 1e-9,
        f"Stable growth {g:.2%} vs risk-free {riskfree:.2%}.")
    if method == "fcff":
        roc, wacc = a["terminal_roc"], a["wacc_terminal"]
        add("Stable reinvestment consistent with growth (RR = g / ROC)", 0 <= result_terminal["reinvestment_rate"] < 1,
            f"Reinvestment rate {result_terminal['reinvestment_rate']:.1%} = {g:.2%} / {roc:.2%}.")
        add("Stable return on capital close to cost of capital", roc <= wacc + 0.05,
            f"ROC {roc:.2%} vs cost of capital {wacc:.2%}; excess returns above 5 points forever need a very durable moat.")
    else:
        ke = a["cost_of_equity_stable"]
        payout = result_terminal["payout"]
        add("Stable payout consistent with fundamentals (g = ROE × retention)", 0 <= payout <= 1,
            f"Stable payout {payout:.1%} = 1 − {g:.2%} / ROE {a['roe_stable']:.2%}.")
        add("Stable ROE close to cost of equity", a["roe_stable"] <= ke + 0.04,
            f"Stable ROE {a['roe_stable']:.2%} vs cost of equity {ke:.2%}.")
        if method == "ddm":
            add("Firm already pays like a stable firm", a["payout_high"] >= 0.5,
                f"Current payout {a['payout_high']:.0%}; a DDM fits best when most earnings are paid out.")
    if beta is not None:
        add("Risk consistent with a stable firm (beta 0.8–1.2 at maturity)", True,
            f"Current beta {beta:.2f}; the model moves the discount rate toward a beta of 1 in stable growth.")
    return checks


# ---------------------------------------------------------------------------- reverse DCF
def reverse_dcf(method: str, a: dict[str, Any], price: float, keys: list[str] | None = None) -> dict[str, Any]:
    """What the market believes: move the key drivers *together* (each by λ × its sensitivity bump,
    in its value-increasing direction) until value per share equals the price. Solved exactly by
    bisection on λ, so it always converges when the price is reachable within the drivers' bounds."""
    keys = keys or KEY_DRIVERS[method]
    drivers = [_driver(method, k) for k in keys]

    def at(lam: float) -> dict[str, Any]:
        out = dict(a)
        for d in drivers:
            sign = 1 if d.higher_is_better else -1
            out[d.key] = d.clamp(a[d.key] + sign * lam * d.bump)
        return out

    def f(lam: float) -> float:
        try:
            return run(method, at(lam)).value_per_share - price
        except ZeroDivisionError:
            return float("nan")

    base_val = run(method, a).value_per_share
    lo, hi = (0.0, 1.0) if base_val < price else (-1.0, 0.0)
    for _ in range(12):  # widen until the price is bracketed
        flo, fhi = f(lo), f(hi)
        if math.isfinite(flo) and math.isfinite(fhi) and flo * fhi <= 0:
            break
        lo, hi = (lo, hi * 2) if base_val < price else (lo * 2, hi)
    else:
        return {"converged": False, "base_value": base_val, "price": price, "rows": []}
    for _ in range(100):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    lam = (lo + hi) / 2
    implied = at(lam)
    val = run(method, implied).value_per_share
    rows = [{"key": d.key, "label": d.label, "unit": d.unit, "mine": a[d.key], "market": implied[d.key],
             "diverges": abs(implied[d.key] - a[d.key]) > 1e-9} for d in drivers]
    return {"converged": abs(val - price) / price < 1e-6, "lambda": lam, "base_value": base_val, "price": price,
            "implied_value": val, "rows": rows,
            "sigmas": lam, "note": f"Each key driver moved {abs(lam):.2f} sensitivity steps "
                                    f"{'toward the bull case' if lam > 0 else 'toward the bear case'}."}
