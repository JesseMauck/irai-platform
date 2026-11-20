"""Excess return model for banks and insurers.

Value of equity = book equity + PV of (ROE − cost of equity) × beginning book equity.
Cash flows are hard to define for financial firms (debt is raw material, not
financing), so value is built from book equity and the spread it earns.
"""
from __future__ import annotations

from .common import HIGH_GROWTH_END, YEARS, Driver, ValuationResult, converge

METHOD = "excess_return"
TITLE = "Excess return model (financials)"

DRIVERS: list[Driver] = [
    Driver("roe_y1", "Return on equity, year 1", "pct", 0.02, "Current profitability", -0.3, 0.5),
    Driver("roe_target", "Return on equity, year 5", "pct", 0.02, "Where profitability settles in the high-growth phase", -0.3, 0.5),
    Driver("payout_high", "Payout ratio, years 1-5", "pct", 0.05, "Dividends + buybacks as share of earnings", 0.0, 1.0),
    Driver("cost_of_equity_high", "Cost of equity, years 1-5", "pct", 0.01, "Equity risk today", 0.02, 0.3, higher_is_better=False),
    Driver("cost_of_equity_stable", "Cost of equity, stable", "pct", 0.005, "Equity risk in steady state", 0.02, 0.2, higher_is_better=False),
    Driver("terminal_growth", "Stable growth rate", "pct", 0.005, "Long-run growth (capped at risk-free rate)", -0.02, 0.06),
    Driver("roe_stable", "Return on equity, stable", "pct", 0.02, "Long-run profitability", 0.0, 0.4),
]

BASE_FIELDS = ["book_equity0", "shares", "price"]


def _roe(t: int, a: dict) -> float:
    if t <= HIGH_GROWTH_END:
        # linear from year-1 ROE to year-5 ROE
        return a["roe_y1"] + (a["roe_target"] - a["roe_y1"]) * (t - 1) / (HIGH_GROWTH_END - 1)
    return converge(t, a["roe_target"], a["roe_stable"])


def value(a: dict) -> ValuationResult:
    warnings: list[str] = []
    g_s = a["terminal_growth"]
    ke_s = a["cost_of_equity_stable"]
    if g_s >= ke_s:
        warnings.append("Stable growth >= stable cost of equity; capped growth at cost of equity - 0.5%.")
        g_s = ke_s - 0.005
    payout_s = 1 - g_s / a["roe_stable"] if a["roe_stable"] else 1.0

    rows = []
    bv = a["book_equity0"]
    df = 1.0
    pv_sum = 0.0
    for t in range(1, YEARS + 1):
        roe = _roe(t, a)
        ke = converge(t, a["cost_of_equity_high"], ke_s)
        payout = converge(t, a["payout_high"], payout_s)
        ni = roe * bv
        excess = (roe - ke) * bv
        df = df / (1 + ke)
        pv = excess * df
        pv_sum += pv
        bv_open = bv
        bv = bv + ni * (1 - payout)
        rows.append({"year": t, "roe": roe, "cost_of_equity": ke, "beginning_book_equity": bv_open,
                     "net_income": ni, "payout": payout, "excess_return": excess,
                     "discount_factor": df, "pv_excess_return": pv, "ending_book_equity": bv})

    excess_t = (a["roe_stable"] - ke_s) * bv
    tv = excess_t / (ke_s - g_s)
    pv_tv = tv * df
    equity = a["book_equity0"] + pv_sum + pv_tv
    per_share = equity / a["shares"]
    terminal = {"growth": g_s, "roe": a["roe_stable"], "payout": payout_s, "excess_return": excess_t,
                "cost_of_equity": ke_s, "terminal_value": tv, "pv_terminal_value": pv_tv}
    bridge = [
        ("Current book value of equity", a["book_equity0"]),
        ("PV of excess returns, years 1-10", pv_sum),
        ("PV of terminal excess returns", pv_tv),
        ("Value of equity", equity),
        ("Shares outstanding", a["shares"]),
        ("Estimated value per share", per_share),
    ]
    return ValuationResult(METHOD, per_share, a.get("price"), equity, rows, terminal, bridge, warnings)
