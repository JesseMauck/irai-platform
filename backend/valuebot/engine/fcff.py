"""Free cash flow to the firm DCF ("story to numbers" style, as in Damodaran's Ginzu model).

Revenue growth, operating margin, reinvestment (via sales-to-capital) and risk
(cost of capital) are the four levers a narrative can move.
"""
from __future__ import annotations

import math

from .common import HIGH_GROWTH_END, YEARS, Driver, ValuationResult, converge

METHOD = "fcff"
TITLE = "FCFF discounted cash flow"

DRIVERS: list[Driver] = [
    Driver("revenue_growth_y1", "Revenue growth, year 1", "pct", 0.03, "How fast sales grow next year", -0.5, 2.0),
    Driver("revenue_growth_y2_5", "Revenue growth, years 2-5 (CAGR)", "pct", 0.03, "The size of the growth story", -0.3, 1.0),
    Driver("operating_margin_y1", "Operating margin, year 1", "pct", 0.02, "Near-term profitability", -1.0, 0.8),
    Driver("target_operating_margin", "Target pre-tax operating margin", "pct", 0.03, "Steady-state profitability / moat", -0.5, 0.8),
    Driver("margin_convergence_year", "Year of convergence to target margin", "years", 2, "How quickly margins reach target", 1, 10, higher_is_better=False),
    Driver("sales_to_capital", "Sales-to-capital ratio, years 1-5", "x", 0.5, "Reinvestment efficiency: $ of sales per $ of capital", 0.1, 10.0),
    Driver("sales_to_capital_late", "Sales-to-capital ratio, years 6-10", "x", 0.5, "Reinvestment efficiency as the business matures (scale, excess capacity)", 0.1, 10.0),
    Driver("wacc_initial", "Cost of capital, years 1-5", "pct", 0.01, "Operating risk today", 0.02, 0.3, higher_is_better=False),
    Driver("wacc_terminal", "Cost of capital, mature", "pct", 0.005, "Risk once the firm is mature", 0.02, 0.2, higher_is_better=False),
    Driver("terminal_growth", "Stable growth rate", "pct", 0.005, "Long-run growth (capped at risk-free rate)", -0.02, 0.06),
    Driver("terminal_roc", "Return on capital, stable phase", "pct", 0.02, "Competitive advantage in perpetuity", 0.02, 0.6),
    Driver("effective_tax_rate", "Effective tax rate, years 1-5", "pct", 0.03, "Taxes paid today", 0.0, 0.5, higher_is_better=False),
    Driver("marginal_tax_rate", "Marginal tax rate, terminal", "pct", 0.03, "Taxes paid in steady state", 0.0, 0.5, higher_is_better=False),
    Driver("prob_failure", "Probability of failure", "pct", 0.05, "Chance the business does not survive", 0.0, 1.0, higher_is_better=False),
]

# Balance-sheet and market inputs that come from data, not from the story.
BASE_FIELDS = [
    "revenue0",
    "ebit0",
    "invested_capital0",
    "cash",
    "debt",
    "minority_interest",
    "non_operating_assets",
    "options_value",
    "shares",
    "price",
    "failure_proceeds_pct",
    "nol0",
]


def value(a: dict) -> ValuationResult:
    warnings: list[str] = []
    g_t = a["terminal_growth"]
    if g_t >= a["wacc_terminal"]:
        warnings.append("Stable growth >= mature cost of capital; capped growth at cost of capital - 0.5%.")
        g_t = a["wacc_terminal"] - 0.005
    n_conv = max(1, math.floor(max(1.0, a["margin_convergence_year"]) + 0.5))  # matches Excel ROUND(MAX(1,x),0)

    rows = []
    rev_prev = a["revenue0"]
    ic = a.get("invested_capital0") or 0.0
    df = 1.0
    pv_sum = 0.0
    nol = max(a.get("nol0", 0.0) or 0.0, 0.0)
    for t in range(1, YEARS + 1):
        if t == 1:
            g = a["revenue_growth_y1"]
        else:
            g = converge(t, a["revenue_growth_y2_5"], g_t)
        rev = rev_prev * (1 + g)
        if t == 1:
            m = a["operating_margin_y1"]
        elif t >= n_conv:
            m = a["target_operating_margin"]
        else:
            m = a["target_operating_margin"] - (a["target_operating_margin"] - a["operating_margin_y1"]) * (n_conv - t) / (n_conv - 1)
        ebit = rev * m
        tax = converge(t, a["effective_tax_rate"], a["marginal_tax_rate"])
        nol_open = nol
        if ebit > 0:  # losses carried forward shelter future income (net operating loss)
            used = min(nol, ebit)
            nopat = ebit - (ebit - used) * tax
            nol = nol - used
        else:  # no tax on losses; they add to the carryforward
            nopat = ebit
            nol = nol - ebit
        s2c = a["sales_to_capital"] if t <= HIGH_GROWTH_END else a.get("sales_to_capital_late", a["sales_to_capital"])
        reinv = (rev - rev_prev) / s2c
        fcff = nopat - reinv
        wacc = converge(t, a["wacc_initial"], a["wacc_terminal"])
        df = df / (1 + wacc)
        pv = fcff * df
        pv_sum += pv
        ic_open = ic
        ic = ic + reinv
        rows.append(
            {
                "year": t,
                "revenue_growth": g,
                "revenue": rev,
                "operating_margin": m,
                "ebit": ebit,
                "tax_rate": tax,
                "nol_beginning": nol_open,
                "nopat": nopat,
                "reinvestment": reinv,
                "fcff": fcff,
                "cost_of_capital": wacc,
                "discount_factor": df,
                "pv_fcff": pv,
                "invested_capital": ic,
                "roic": nopat / ic_open if ic_open else None,
            }
        )
        rev_prev = rev

    rev_t = rev_prev * (1 + g_t)
    ebit_t = rev_t * a["target_operating_margin"]
    nopat_t = ebit_t * (1 - a["marginal_tax_rate"])
    reinv_rate = g_t / a["terminal_roc"] if a["terminal_roc"] else 0.0
    fcff_t = nopat_t * (1 - reinv_rate)
    tv = fcff_t / (a["wacc_terminal"] - g_t)
    pv_tv = tv * df

    op_value = pv_sum + pv_tv
    p_fail = a.get("prob_failure", 0.0) or 0.0
    proceeds = a.get("failure_proceeds_pct", 0.5)
    op_value_adj = op_value * (1 - p_fail) + op_value * proceeds * p_fail
    equity = op_value_adj - a["debt"] - a.get("minority_interest", 0) + a["cash"] + a.get("non_operating_assets", 0)
    common = equity - a.get("options_value", 0)
    per_share = common / a["shares"]

    if pv_tv / op_value > 0.85 if op_value > 0 else False:
        warnings.append("Terminal value is more than 85% of operating asset value; the story is mostly about the long run.")
    if reinv_rate > 1:
        warnings.append("Stable growth exceeds return on capital: terminal reinvestment > 100% of NOPAT.")

    terminal = {
        "growth": g_t,
        "revenue": rev_t,
        "ebit": ebit_t,
        "nopat": nopat_t,
        "reinvestment_rate": reinv_rate,
        "fcff": fcff_t,
        "cost_of_capital": a["wacc_terminal"],
        "terminal_value": tv,
        "pv_terminal_value": pv_tv,
    }
    bridge = [
        ("PV of FCFF, years 1-10", pv_sum),
        ("PV of terminal value", pv_tv),
        ("Value of operating assets", op_value),
        ("Adjusted for probability of failure", op_value_adj),
        ("− Debt", -a["debt"]),
        ("− Minority interests", -a.get("minority_interest", 0)),
        ("+ Cash", a["cash"]),
        ("+ Non-operating assets", a.get("non_operating_assets", 0)),
        ("Value of equity", equity),
        ("− Value of options", -a.get("options_value", 0)),
        ("Value of common equity", common),
        ("Shares outstanding", a["shares"]),
        ("Estimated value per share", per_share),
    ]
    return ValuationResult(METHOD, per_share, a.get("price"), common, rows, terminal, bridge, warnings)


def growth_for_revenue_target(a: dict, target_revenue_y10: float) -> float | None:
    """Revenue CAGR for years 2-5 that makes year-10 revenue hit a target (e.g. TAM × market share).

    Ties the growth story to market size and share, as in the Uber/Zomato valuations."""
    lo, hi = -0.3, 1.5

    def rev10(g):
        return value({**a, "revenue_growth_y2_5": g}).table[-1]["revenue"]

    if not (rev10(lo) <= target_revenue_y10 <= rev10(hi)):
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if rev10(mid) < target_revenue_y10:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
