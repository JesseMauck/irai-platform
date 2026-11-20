"""Possible, plausible, probable: test the story before trusting the numbers.

From the class: "There are lots of possible narratives, not all of them are plausible and
only a few of them are probable. No fairy tales or runaway stories."

  Impossible   – bigger than the economy, bigger than the total market, margins above the
                 gross-margin ceiling or 100%, growth forever above the risk-free rate.
  Implausible  – growth without reinvestment, profits without competition, returns without risk.
  Improbable   – needs evidence: growth while ROIC < cost of capital ("fix the business first"),
                 a value that is mostly terminal value, high failure risk ignored.
"""
from __future__ import annotations

from typing import Any

WORLD_GDP_USD = 115e12  # ~2025 nominal world GDP; an order-of-magnitude ceiling, not a forecast


def _t(level: str, name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"level": level, "test": name, "pass": bool(ok), "detail": detail}


def narrative_tests(method: str, a: dict[str, Any], result: dict[str, Any], *, riskfree: float,
                    gross_margin: float | None = None, current_roic: float | None = None,
                    current_wacc: float | None = None, tam_year10: float | None = None,
                    erp: float | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    term = result["terminal"]
    g = term.get("growth", 0.0)
    out.append(_t("impossible", "Not growing faster than the economy forever", g <= riskfree + 1e-9,
                  f"Stable growth {g:.2%} vs risk-free rate {riskfree:.2%} (a proxy for nominal growth)."))

    if method == "fcff":
        rows = result["table"]
        rev10 = rows[-1]["revenue"]
        out.append(_t("impossible", "Not bigger than the economy", rev10 < 0.02 * WORLD_GDP_USD,
                      f"Year-10 revenue {rev10 / 1e9:,.0f}bn vs ~{WORLD_GDP_USD / 1e12:,.0f}tn world GDP."))
        if tam_year10:
            share = rev10 / tam_year10
            out.append(_t("impossible", "Not bigger than the total market", share <= 1.0,
                          f"Year-10 revenue is {share:.0%} of the year-10 total market."))
            out.append(_t("implausible", "Market share a dominant player could hold", share <= 0.6,
                          f"Implied year-10 market share {share:.0%}."))
        tm = a["target_operating_margin"]
        out.append(_t("impossible", "Margin below 100%", tm < 1, f"Target operating margin {tm:.1%}."))
        if gross_margin is not None:
            out.append(_t("impossible", "Operating margin within the gross-margin ceiling", tm <= gross_margin,
                          f"Target operating margin {tm:.1%} vs gross margin {gross_margin:.1%} (unit economics cap profitability)."))
        # growth without reinvestment: marginal return on new capital implied by sales-to-capital
        mt = a["target_operating_margin"] * (1 - a["marginal_tax_rate"])
        marginal_roic = mt * a["sales_to_capital"]
        out.append(_t("implausible", "Growth is paid for (no growth without reinvestment)", marginal_roic <= 0.5,
                      f"Sales-to-capital {a['sales_to_capital']:.2f} × after-tax target margin {mt:.1%} implies a "
                      f"{marginal_roic:.0%} return on new capital."))
        roic10 = rows[-1].get("roic")
        if roic10 is not None:
            out.append(_t("implausible", "Profits face competition (year-10 ROIC)", roic10 <= 0.5,
                          f"Year-10 return on invested capital {roic10:.1%}."))
        excess = a["terminal_roc"] - a["wacc_terminal"]
        out.append(_t("implausible", "No perpetual excess returns without a durable moat", excess <= 0.05,
                      f"Stable ROIC {a['terminal_roc']:.1%} vs mature cost of capital {a['wacc_terminal']:.1%}."))
        high_growth = a["revenue_growth_y2_5"] > 0.15
        if erp is not None:
            avg_risk = riskfree + erp
            out.append(_t("implausible", "No high growth without risk", not (high_growth and a["wacc_initial"] < avg_risk - 0.005),
                          f"Growth {a['revenue_growth_y2_5']:.1%} with cost of capital {a['wacc_initial']:.2%} "
                          f"(an average-risk firm: {avg_risk:.2%})."))
        if current_roic is not None and current_wacc is not None:
            ok = not (current_roic < current_wacc and high_growth)
            out.append(_t("improbable", "Growth creates value (ROIC ≥ cost of capital)", ok,
                          f"Current ROIC {current_roic:.1%} vs cost of capital {current_wacc:.1%}. "
                          + ("" if ok else "Growth destroys value until the business earns its cost of capital: fix it before growing.")))
        tv_share = term["pv_terminal_value"] / (term["pv_terminal_value"] + sum(r["pv_fcff"] for r in rows))
        out.append(_t("improbable", "Value does not rest mostly on the terminal value", tv_share <= 0.85,
                      f"Terminal value is {tv_share:.0%} of operating-asset value."))
    else:
        roe_s = a["roe_stable"]
        ke_s = a["cost_of_equity_stable"]
        out.append(_t("implausible", "Stable ROE close to cost of equity", roe_s - ke_s <= 0.04,
                      f"Stable ROE {roe_s:.1%} vs stable cost of equity {ke_s:.1%}."))
        out.append(_t("impossible", "Stable payout between 0% and 100%", 0 <= term["payout"] <= 1,
                      f"Stable payout {term['payout']:.1%} = 1 − g/ROE."))
    return out
