"""Method registry, automatic method selection and sensitivity analysis."""
from __future__ import annotations

from types import ModuleType
from typing import Any

from . import ddm, excess_return, fcff
from .common import Driver, ValuationResult

METHODS: dict[str, ModuleType] = {m.METHOD: m for m in (fcff, ddm, excess_return)}

FINANCIAL_HINTS = ("bank", "insurance", "capital markets", "credit services", "asset management",
                   "financial services", "savings", "thrift", "mortgage finance")
DIVIDEND_SECTOR_HINTS = ("utilities", "utility", "reit", "real estate investment trust", "tobacco")


def choose_method(*, sector: str | None, industry: str | None, payout_ratio: float | None,
                  pays_dividends: bool, has_revenue: bool) -> tuple[str, str]:
    """Pick a framework the way Damodaran would: by what the business *is*.

    Returns (method key, one-line reason).
    """
    text = f"{sector or ''} {industry or ''}".lower()
    if any(h in text for h in FINANCIAL_HINTS) or not has_revenue:
        return "excess_return", (
            "Financial-services firm: debt is raw material rather than financing, so free cash flow "
            "is ill-defined. Valued from book equity plus the excess return it earns over the cost of equity."
        )
    if pays_dividends and payout_ratio is not None and payout_ratio >= 0.6 and any(h in text for h in DIVIDEND_SECTOR_HINTS):
        return "ddm", (
            "Regulated / mature dividend payer that returns most of its earnings, so dividends are a "
            "reasonable proxy for cash flow to equity."
        )
    return "fcff", (
        "Operating business: value is driven by revenue growth, margins, reinvestment efficiency and risk, "
        "so a free cash flow to the firm DCF ties the story to the numbers most directly."
    )


def drivers_for(method: str) -> list[Driver]:
    return METHODS[method].DRIVERS


def run(method: str, assumptions: dict[str, Any]) -> ValuationResult:
    return METHODS[method].value(assumptions)


def sensitivity(method: str, assumptions: dict[str, Any]) -> dict[str, Any]:
    """One-at-a-time driver flex for a tornado chart, plus combined bull/bear scenarios."""
    base = run(method, assumptions).value_per_share
    rows = []
    bull = dict(assumptions)
    bear = dict(assumptions)
    for d in drivers_for(method):
        v0 = assumptions[d.key]
        lo_in, hi_in = d.clamp(v0 - d.bump), d.clamp(v0 + d.bump)
        lo_val = run(method, {**assumptions, d.key: lo_in}).value_per_share
        hi_val = run(method, {**assumptions, d.key: hi_in}).value_per_share
        rows.append({
            "key": d.key, "label": d.label, "unit": d.unit, "base_input": v0,
            "low_input": lo_in, "high_input": hi_in,
            "low_value": lo_val, "high_value": hi_val,
            "range": abs(hi_val - lo_val),
        })
        good, bad = (hi_in, lo_in) if d.higher_is_better else (lo_in, hi_in)
        bull[d.key], bear[d.key] = good, bad
    rows.sort(key=lambda r: r["range"], reverse=True)
    return {
        "base_value": base,
        "drivers": rows,
        "scenarios": {
            "bear": {"assumptions": bear, "value_per_share": run(method, bear).value_per_share},
            "base": {"assumptions": dict(assumptions), "value_per_share": base},
            "bull": {"assumptions": bull, "value_per_share": run(method, bull).value_per_share},
        },
    }
