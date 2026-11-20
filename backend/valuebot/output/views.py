"""Report building blocks shared by the web view and the printable/PDF report.

* chapters   – "from story to numbers": each story chapter with its storyline and its numbers
* one_page   – the valuation on one page: assumptions by phase with a link to the story
* summary    – the final valuation summary table
"""
from __future__ import annotations

from typing import Any


def _p(x):
    return "—" if x is None else f"{x:.1%}"


def _m(x):
    return "—" if x is None else f"{x / 1e9:,.1f}bn" if abs(x) >= 1e9 else f"{x / 1e6:,.0f}m"


def _v(a: dict, k: str, d=None):
    x = a.get(k) or {}
    return x.get("value", d)


def chapters(ctx: dict[str, Any]) -> list[dict[str, str]]:
    a, st, r = ctx["assumptions"], ctx.get("stories") or {}, ctx["result"]
    why = {k: v.get("rationale", "") for k, v in a.items()}
    if ctx["method"] == "fcff":
        rows = r["table"]
        tv_share = r["terminal"]["pv_terminal_value"] / (r["terminal"]["pv_terminal_value"] + sum(x["pv_fcff"] for x in rows))
        reinv10 = sum(x["reinvestment"] for x in rows)
        return [
            {"chapter": "Growth", "story": st.get("growth") or why.get("revenue_growth_y2_5", ""),
             "numbers": f"Yr 1: {_p(_v(a, 'revenue_growth_y1'))} · Yrs 2-5: {_p(_v(a, 'revenue_growth_y2_5'))} · "
                        f"Yr-10 revenue: {_m(rows[-1]['revenue'])}"},
            {"chapter": "Profitability", "story": st.get("profitability") or why.get("target_operating_margin", ""),
             "numbers": f"Margin {_p(_v(a, 'operating_margin_y1'))} now → {_p(_v(a, 'target_operating_margin'))} "
                        f"by year {int(_v(a, 'margin_convergence_year', 5))}"},
            {"chapter": "Reinvestment", "story": st.get("efficiency") or why.get("sales_to_capital", ""),
             "numbers": f"Sales-to-capital {_v(a, 'sales_to_capital'):.2f} / {_v(a, 'sales_to_capital_late', _v(a, 'sales_to_capital')):.2f} · "
                        f"10-yr reinvestment {_m(reinv10)}"},
            {"chapter": "Risk", "story": st.get("risk") or why.get("wacc_initial", ""),
             "numbers": f"Cost of capital {_p(_v(a, 'wacc_initial'))} → {_p(_v(a, 'wacc_terminal'))} · "
                        f"failure {_p(_v(a, 'prob_failure'))}"},
            {"chapter": "Endgame", "story": st.get("moat") or why.get("terminal_roc", ""),
             "numbers": f"g {_p(r['terminal']['growth'])} · ROC {_p(_v(a, 'terminal_roc'))} · TV {tv_share:.0%} of value"},
        ]
    # equity models: growth comes from ROE × retention; risk is the cost of equity
    roe_k = "roe_high" if ctx["method"] == "ddm" else "roe_target"
    return [
        {"chapter": "Growth", "story": st.get("growth") or why.get(roe_k, ""),
         "numbers": f"ROE {_p(_v(a, roe_k))} · payout {_p(_v(a, 'payout_high'))}"},
        {"chapter": "Profitability", "story": st.get("profitability") or why.get(roe_k, ""),
         "numbers": f"Stable ROE {_p(_v(a, 'roe_stable'))}"},
        {"chapter": "Risk", "story": st.get("risk") or why.get("cost_of_equity_high", ""),
         "numbers": f"Cost of equity {_p(_v(a, 'cost_of_equity_high'))} → {_p(_v(a, 'cost_of_equity_stable'))}"},
        {"chapter": "Endgame", "story": st.get("moat") or why.get("terminal_growth", ""),
         "numbers": f"g {_p(r['terminal']['growth'])} · stable payout {_p(r['terminal'].get('payout'))}"},
    ]


def one_page(ctx: dict[str, Any]) -> list[dict[str, str]] | None:
    """Assumptions by phase (Damodaran's 'valuation on one page'). FCFF only."""
    if ctx["method"] != "fcff":
        return None
    a, rows, m0 = ctx["assumptions"], ctx["result"]["table"], ctx["metrics"][-1]
    t = ctx["result"]["terminal"]
    why = {k: v.get("rationale", "") for k, v in a.items()}
    return [
        {"item": "Revenue growth", "base": _p(m0.get("revenue_growth")), "y1_5": f"{_p(_v(a, 'revenue_growth_y1'))} → {_p(_v(a, 'revenue_growth_y2_5'))}",
         "y6_10": f"→ {_p(t['growth'])}", "after": _p(t["growth"]), "story": why.get("revenue_growth_y2_5", "")},
        {"item": "Operating margin", "base": _p(m0.get("operating_margin")), "y1_5": f"{_p(rows[0]['operating_margin'])} → {_p(rows[4]['operating_margin'])}",
         "y6_10": _p(rows[9]["operating_margin"]), "after": _p(_v(a, "target_operating_margin")), "story": why.get("target_operating_margin", "")},
        {"item": "Tax rate", "base": _p(m0.get("effective_tax_rate")), "y1_5": _p(_v(a, "effective_tax_rate")),
         "y6_10": f"→ {_p(_v(a, 'marginal_tax_rate'))}", "after": _p(_v(a, "marginal_tax_rate")), "story": why.get("effective_tax_rate", "")},
        {"item": "Sales to capital", "base": f"{m0['sales_to_capital']:.2f}" if m0.get("sales_to_capital") else "—",
         "y1_5": f"{_v(a, 'sales_to_capital'):.2f}", "y6_10": f"{_v(a, 'sales_to_capital_late', _v(a, 'sales_to_capital')):.2f}",
         "after": f"RIR {_p(t['reinvestment_rate'])}", "story": why.get("sales_to_capital", "")},
        {"item": "Return on capital", "base": _p(m0.get("roic")), "y1_5": _p(rows[4].get("roic")), "y6_10": _p(rows[9].get("roic")),
         "after": _p(_v(a, "terminal_roc")), "story": why.get("terminal_roc", "")},
        {"item": "Cost of capital", "base": _p(_v(a, "wacc_initial")), "y1_5": _p(_v(a, "wacc_initial")),
         "y6_10": f"→ {_p(_v(a, 'wacc_terminal'))}", "after": _p(_v(a, "wacc_terminal")), "story": why.get("wacc_initial", "")},
    ]


def summary(ctx: dict[str, Any]) -> list[tuple[str, str]]:
    r, s, c = ctx["result"], ctx["sensitivity"], ctx["company"]
    prob = ctx.get("probabilistic") or {}
    sim = prob.get("simulation") or {}
    rows = [
        ("Estimated value per share", f"{r['value_per_share']:,.2f} {c.get('currency', '')}"),
        ("Current price", f"{r['price']:,.2f}"),
        ("Price as % of value", f"{r['price'] / r['value_per_share']:.0%}" if r["value_per_share"] > 0 else "—"),
        ("Upside / (downside)", f"{r['upside']:+.1%}" if r.get("upside") is not None else "—"),
        ("Value of equity", _m(r["equity_value"])),
        ("Market value of equity", _m(r["price"] * c["shares"])),
        ("Valuation method", ctx["method_title"]),
    ]
    if ctx["method"] == "fcff":
        a = ctx["assumptions"]
        t = r["terminal"]
        tv_share = t["pv_terminal_value"] / (t["pv_terminal_value"] + sum(x["pv_fcff"] for x in r["table"]))
        rows += [("Cost of capital: initial → mature", f"{_p(_v(a, 'wacc_initial'))} → {_p(_v(a, 'wacc_terminal'))}"),
                 ("Stable growth / return on capital", f"{_p(t['growth'])} / {_p(_v(a, 'terminal_roc'))}"),
                 ("Year-10 revenue", _m(r["table"][-1]["revenue"])),
                 ("Target operating margin", _p(_v(a, "target_operating_margin"))),
                 ("Terminal value as % of value", f"{tv_share:.0%}")]
    rows.append(("Sensitivity range (one driver at a time)",
                 f"{min(min(d['low_value'], d['high_value']) for d in s['drivers']):,.2f} – "
                 f"{max(max(d['low_value'], d['high_value']) for d in s['drivers']):,.2f}"))
    if sim:
        pc = sim["percentiles"]
        p10, p90 = pc.get(10, pc.get("10")), pc.get(90, pc.get("90"))
        rows += [("Simulated value, 10th–90th percentile", f"{p10:,.2f} – {p90:,.2f}"),
                 ("Probability undervalued (simulated)", _p(sim.get("prob_undervalued"))),
                 ("Risk-adjusted margin of safety", _p(sim.get("margin_of_safety")))]
    if prob.get("scenarios"):
        rows.append(("Probability-weighted scenario value", f"{prob['scenarios']['expected_value']:,.2f}"))
    return rows
