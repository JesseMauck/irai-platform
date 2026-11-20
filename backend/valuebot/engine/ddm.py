"""Dividend discount model with fundamental growth (g = ROE × retention).

Used for mature dividend payers (utilities, REITs, consumer staples) where
dividends are a reasonable proxy for cash flow to equity.
"""
from __future__ import annotations

from .common import YEARS, Driver, ValuationResult, converge

METHOD = "ddm"
TITLE = "Dividend discount model"

DRIVERS: list[Driver] = [
    Driver("roe_high", "Return on equity, years 1-5", "pct", 0.02, "Profitability on reinvested earnings", -0.2, 0.6),
    Driver("payout_high", "Payout ratio, years 1-5", "pct", 0.05, "Share of earnings paid out today", 0.0, 1.0),
    Driver("cost_of_equity_high", "Cost of equity, years 1-5", "pct", 0.01, "Equity risk today", 0.02, 0.3, higher_is_better=False),
    Driver("cost_of_equity_stable", "Cost of equity, stable", "pct", 0.005, "Equity risk in steady state", 0.02, 0.2, higher_is_better=False),
    Driver("terminal_growth", "Stable growth rate", "pct", 0.005, "Long-run growth (capped at risk-free rate)", -0.02, 0.06),
    Driver("roe_stable", "Return on equity, stable", "pct", 0.02, "Long-run profitability; sets stable payout", 0.02, 0.5),
]

BASE_FIELDS = ["eps0", "shares", "price"]


def value(a: dict) -> ValuationResult:
    warnings: list[str] = []
    g_s = a["terminal_growth"]
    ke_s = a["cost_of_equity_stable"]
    if g_s >= ke_s:
        warnings.append("Stable growth >= stable cost of equity; capped growth at cost of equity - 0.5%.")
        g_s = ke_s - 0.005
    g_high = a["roe_high"] * (1 - a["payout_high"])
    payout_s = 1 - g_s / a["roe_stable"]

    rows = []
    eps = a["eps0"]
    df = 1.0
    pv_sum = 0.0
    for t in range(1, YEARS + 1):
        g = converge(t, g_high, g_s)
        payout = converge(t, a["payout_high"], payout_s)
        ke = converge(t, a["cost_of_equity_high"], ke_s)
        eps = eps * (1 + g)
        dps = eps * payout
        df = df / (1 + ke)
        pv = dps * df
        pv_sum += pv
        rows.append({"year": t, "eps_growth": g, "eps": eps, "payout": payout, "dps": dps,
                     "cost_of_equity": ke, "discount_factor": df, "pv_dps": pv})

    eps_t = eps * (1 + g_s)
    dps_t = eps_t * payout_s
    tv = dps_t / (ke_s - g_s)
    pv_tv = tv * df
    per_share = pv_sum + pv_tv
    if payout_s < 0:
        warnings.append("Stable ROE below stable growth implies negative payout.")
    terminal = {"growth": g_s, "eps": eps_t, "payout": payout_s, "dps": dps_t,
                "cost_of_equity": ke_s, "terminal_value": tv, "pv_terminal_value": pv_tv}
    bridge = [
        ("Expected growth, years 1-5 (ROE × retention)", g_high),
        ("PV of dividends, years 1-10", pv_sum),
        ("PV of terminal price", pv_tv),
        ("Estimated value per share", per_share),
        ("Shares outstanding", a["shares"]),
        ("Value of equity", per_share * a["shares"]),
    ]
    return ValuationResult(METHOD, per_share, a.get("price"), per_share * a["shares"], rows, terminal, bridge, warnings)
