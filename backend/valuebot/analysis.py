"""Historical metrics and data-driven starting assumptions for each method.

The LLM refines these starting points against the thesis; in offline mode they
are used as-is. Every starting point carries a short rationale so the report can
explain where each number came from.
"""
from __future__ import annotations

from statistics import mean
from typing import Any

from .config import settings
from .engine import adjustments as adj
from .engine.cost_of_capital import CostOfCapital, compute_cost_of_capital

US_MARGINAL_TAX = 0.25  # 21% federal + ~4% state


def _safe_div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def history_metrics(snap: dict) -> list[dict[str, Any]]:
    hist = snap["history"]
    out = []
    prev = None
    for h in hist:
        rev = h.get("revenue")
        ebit = h.get("operating_income")
        if ebit is None and h.get("pretax_income") is not None:
            ebit = h["pretax_income"] + (h.get("interest_expense") or 0)
        debt = (h.get("debt") or 0) + (h.get("lease_liabilities") or 0)
        ic = (h.get("equity") or 0) + debt - (h.get("cash") or 0)
        tax_rate = _safe_div(h.get("income_tax"), h.get("pretax_income"))
        payout = _safe_div((h.get("dividends_paid") or 0), h.get("net_income"))
        cash_return = _safe_div((h.get("dividends_paid") or 0) + (h.get("buybacks") or 0), h.get("net_income"))
        avg_equity = mean([x for x in (h.get("equity"), prev and prev.get("equity")) if x]) if h.get("equity") else None
        m = {
            "fiscal_year": h["fiscal_year"],
            "revenue": rev,
            "revenue_growth": _safe_div(rev, prev and prev.get("revenue")) - 1 if prev and rev and prev.get("revenue") else None,
            "ebit": ebit,
            "operating_margin": _safe_div(ebit, rev),
            "gross_margin": _safe_div(h.get("gross_profit"), rev),
            "rnd": h.get("rnd"),
            "effective_tax_rate": tax_rate,
            "net_income": h.get("net_income"),
            "invested_capital": ic,
            "sales_to_capital": _safe_div(rev, ic) if ic and ic > 0 else None,
            "roic": _safe_div(ebit * (1 - _clamp(tax_rate or US_MARGINAL_TAX, 0, 0.5)), ic) if ebit is not None and ic and ic > 0 else None,
            "roe": _safe_div(h.get("net_income"), avg_equity),
            "payout_ratio": payout,
            "cash_return_ratio": cash_return,
            "debt_incl_leases": debt,
            "cash": h.get("cash"),
            "equity": h.get("equity"),
            "interest_expense": h.get("interest_expense"),
        }
        out.append(m)
        prev = h
    return out


def _avg(metrics, key, n=3):
    vals = [m[key] for m in metrics[-n:] if m.get(key) is not None]
    return mean(vals) if vals else None


def _f(x) -> float | None:
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def risk_inputs(snap: dict, metrics: list[dict], risk: dict | None) -> dict[str, Any]:
    """Risk-free rate, beta and ERP, following the class:

    * risk-free = default-free rate *in the currency of the cash flows* (differential inflation
      for non-US$ currencies, or a government bond net of its sovereign default spread);
    * beta = bottom-up (businesses the firm operates in, relevered) before regression beta;
    * ERP = mature ERP + country risk weighted by where revenues come from, not incorporation.
    """
    risk = risk or {}
    notes: list[str] = []
    last = metrics[-1]
    rf = snap["riskfree"]
    rf_src = snap.get("riskfree_source", "")
    cur = (snap.get("currency") or "USD").upper()
    if _f(risk.get("riskfree_override")) is not None:
        rf = _f(risk["riskfree_override"])
        rf_src = "Set by you"
    elif cur != "USD" and _f(risk.get("inflation")) is not None:
        rf = adj.riskfree_in_currency(snap["riskfree"], _f(risk["inflation"]), settings.us_inflation)
        rf_src = (f"US$ risk-free {snap['riskfree']:.2%} converted to {cur} with expected inflation "
                  f"{_f(risk['inflation']):.1%} vs US {settings.us_inflation:.1%}")
    elif cur != "USD":
        notes.append(f"Cash flows are in {cur} but the risk-free rate is in US$: enter expected {cur} inflation "
                     "so discount rate and cash flows are in the same currency.")

    debt = last["debt_incl_leases"] or 0
    de = debt / snap["market_cap"] if snap.get("market_cap") else 0
    beta, beta_src, segs = snap.get("beta") or 1.0, "Regression beta (Yahoo Finance)", None
    segments = [s for s in risk.get("segments") or [] if s.get("name")]
    if segments:
        if any(_f(s.get("unlevered_beta")) is None for s in segments):
            from .data import damodaran

            table = damodaran.industry_betas()
            for s in segments:
                if _f(s.get("unlevered_beta")) is None:
                    m = damodaran.best_match(s["name"], table)
                    if m:
                        s["unlevered_beta"], s["matched_industry"] = table[m], m
        bu = adj.bottom_up_beta([{**s, "weight": _f(s.get("weight")) or 0, "unlevered_beta": _f(s.get("unlevered_beta"))}
                                 for s in segments], de, US_MARGINAL_TAX)
        if bu:
            beta, beta_src, segs = bu["levered_beta"], "Bottom-up beta from your business segments", bu
    elif not snap.get("demo"):
        from .data import damodaran

        table = damodaran.industry_betas()
        m = damodaran.best_match(snap.get("industry"), table)
        if m:
            bu = adj.bottom_up_beta([{"name": m, "weight": 1, "unlevered_beta": table[m]}], de, US_MARGINAL_TAX)
            beta, beta_src, segs = bu["levered_beta"], f"Bottom-up beta: '{m}' industry average (NYU Stern public datasets)", bu
    if snap.get("beta") and not segs:
        notes.append("Regression betas are backward looking and noisy; enter business segments for a bottom-up beta.")

    exposures = [e for e in risk.get("regions") or [] if e.get("region")]
    if exposures and any(_f(e.get("crp")) is None for e in exposures):
        from .data import damodaran

        table = damodaran.country_premiums()
        for e in exposures:
            if _f(e.get("crp")) is None:
                m = damodaran.best_match(e["region"], table, cutoff=0.7)
                e["crp"] = table[m] if m else 0.0
                e["crp_source"] = f"Country risk premium dataset: {m}" if m else "not found: assumed 0"
    erp, crp = adj.erp_from_exposure(settings.equity_risk_premium,
                                     [{**e, "weight": _f(e.get("weight")) or 0, "crp": _f(e.get("crp")) or 0} for e in exposures])
    erp_src = (f"Mature ERP {settings.equity_risk_premium:.2%} + revenue-weighted country risk {crp:.2%}"
               if exposures else f"Mature-market implied ERP {settings.equity_risk_premium:.2%}")
    return {"riskfree": rf, "riskfree_source": rf_src, "beta": beta, "beta_source": beta_src, "bottom_up": segs,
            "erp": erp, "erp_source": erp_src, "country_risk": crp, "exposures": exposures, "notes": notes,
            "debt_to_equity": de}


def cost_of_capital(snap: dict, metrics: list[dict], risk: dict | None = None) -> CostOfCapital:
    last = metrics[-1]
    r = risk or {"riskfree": snap["riskfree"], "erp": settings.equity_risk_premium, "beta": snap.get("beta") or 1.0}
    return compute_cost_of_capital(
        riskfree=r["riskfree"],
        erp=r["erp"],
        beta=r["beta"],
        market_cap=snap["market_cap"],
        debt=last["debt_incl_leases"] or 0,
        ebit=last["ebit"] or 0,
        interest_expense=last["interest_expense"] or 0,
        marginal_tax_rate=US_MARGINAL_TAX,
    )


def earnings_adjustments(snap: dict, metrics: list[dict], coc: CostOfCapital, opts: dict | None) -> dict[str, Any]:
    """'Measure earnings right': capitalize R&D, treat leases as debt, strip one-time items.

    Mutates the latest metrics row in place (keeping the reported numbers alongside) so every
    downstream default sees adjusted operating income and invested capital."""
    opts = opts or {}
    last = metrics[-1]
    rev = last["revenue"] or 0
    ebit_rep, ic_rep = last["ebit"] or 0.0, last["invested_capital"] or 0.0
    ebit, ic = ebit_rep, ic_rep
    items: list[dict[str, Any]] = []

    mode = (opts.get("capitalize_rnd") or "auto").lower()
    rnd_hist = [m.get("rnd") for m in metrics if m.get("rnd") is not None]
    rnd_intensity = (rnd_hist[-1] / rev) if rnd_hist and rev else 0
    rnd = None
    if rnd_hist and (mode == "yes" or (mode == "auto" and rnd_intensity >= 0.03)):
        life = int(_f(opts.get("rnd_life")) or adj.rnd_life_for(snap.get("industry")))
        rnd = adj.capitalize_rnd(rnd_hist, life)
        if rnd.get("applied"):
            ebit += rnd["ebit_adjustment"]
            ic += rnd["research_asset"]
            items.append({"item": f"Capitalize R&D ({life}-year life)", "ebit": rnd["ebit_adjustment"],
                          "invested_capital": rnd["research_asset"],
                          "detail": f"+ R&D {rnd['current_rnd'] / 1e6:,.0f}m − amortization {rnd['amortization'] / 1e6:,.0f}m; "
                                    f"research asset {rnd['research_asset'] / 1e6:,.0f}m"
                                    + (f" ({rnd['extrapolated_years']} early years extrapolated)" if rnd["extrapolated_years"] else "")})

    lease_debt = snap["history"][-1].get("lease_liabilities") or 0
    if lease_debt and opts.get("lease_adjust", True):
        add = adj.lease_ebit_adjustment(lease_debt, coc.pretax_cost_of_debt)
        ebit += add
        items.append({"item": "Operating leases as debt", "ebit": add, "invested_capital": 0.0,
                      "detail": f"Lease debt {lease_debt / 1e6:,.0f}m included in debt; implied interest "
                                f"({coc.pretax_cost_of_debt:.2%}) added back to operating income"})

    one_off = _f(opts.get("one_time_addback")) or 0.0
    if one_off:
        ebit += one_off
        items.append({"item": "One-time / non-recurring items", "ebit": one_off, "invested_capital": 0.0,
                      "detail": "Added back as entered by you"})

    last.update({"ebit_reported": ebit_rep, "invested_capital_reported": ic_rep, "ebit": ebit,
                 "invested_capital": ic, "operating_margin": ebit / rev if rev else last["operating_margin"],
                 "operating_margin_reported": last["operating_margin"],
                 "sales_to_capital": rev / ic if ic > 0 else None})
    t = _clamp(last.get("effective_tax_rate") or US_MARGINAL_TAX, 0, 0.5)
    last["roic"] = ebit * (1 - t) / ic if ic > 0 else None
    avg_margin = _avg(metrics[:-1] + [last], "operating_margin", n=len(metrics))
    return {"items": items, "ebit_reported": ebit_rep, "ebit_adjusted": ebit, "invested_capital_reported": ic_rep,
            "invested_capital_adjusted": ic, "rnd": rnd, "rnd_intensity": rnd_intensity,
            "normalize": bool(opts.get("normalize_margins")), "average_margin": avg_margin}


def options_value(snap: dict, extras: dict | None, riskfree: float) -> tuple[float, str | None]:
    extras = extras or {}
    last_h = snap["history"][-1]
    n = _f(extras.get("options_count")) or last_h.get("options_outstanding")
    k = _f(extras.get("options_strike")) or last_h.get("options_strike")
    if not n or not k:
        return 0.0, None
    t = _f(extras.get("options_maturity")) or 5.0
    sigma = _f(extras.get("volatility")) or 0.35
    y = (snap.get("dividend_rate") or 0) / snap["price"] if snap.get("price") else 0
    v = adj.employee_options_value(n_options=n, strike=k, maturity=t, price=snap["price"], shares=snap["shares"],
                                   sigma=sigma, r=riskfree, y=y)
    return v, (f"{n / 1e6:,.1f}m options, avg strike {k:,.2f}, {t:.1f}y maturity, volatility {sigma:.0%} "
               "(Black-Scholes, dilution-adjusted)")


def base_inputs(method: str, snap: dict, metrics: list[dict], extras: dict | None = None,
                riskfree: float | None = None) -> dict[str, Any]:
    extras = extras or {}
    last_h = snap["history"][-1]
    last = metrics[-1]
    if method == "fcff":
        opt_val, _ = options_value(snap, extras, riskfree if riskfree is not None else snap["riskfree"])
        nonop = _f(extras.get("non_operating_assets"))
        return {
            "revenue0": last["revenue"],
            "ebit0": last["ebit"],
            "invested_capital0": last["invested_capital"],
            "cash": last_h.get("cash") or 0,
            "debt": last["debt_incl_leases"],
            "minority_interest": last_h.get("minority_interest") or 0,
            "non_operating_assets": nonop if nonop is not None else (last_h.get("equity_investments") or 0),
            "options_value": opt_val,
            "shares": snap["shares"],
            "price": snap["price"],
            "failure_proceeds_pct": 0.5,
            "nol0": max(_f(extras.get("nol")) if _f(extras.get("nol")) is not None else (last_h.get("nol") or 0.0), 0.0),
        }
    if method == "ddm":
        return {"eps0": last["net_income"] / snap["shares"], "shares": snap["shares"], "price": snap["price"]}
    if method == "excess_return":
        return {"book_equity0": last_h["equity"], "shares": snap["shares"], "price": snap["price"]}
    raise ValueError(method)


def default_drivers(method: str, snap: dict, metrics: list[dict], coc: CostOfCapital,
                    earnings: dict | None = None) -> tuple[dict[str, float], dict[str, str]]:
    """Return (driver values, rationale per driver)."""
    earnings = earnings or {}
    rf = snap["riskfree"]
    last = metrics[-1]
    why: dict[str, str] = {}
    d: dict[str, float] = {}

    if method == "fcff":
        cons = (snap.get("consensus") or {}).get("revenue_growth_next_fy")
        g_last = last.get("revenue_growth")
        g1 = cons if cons is not None else (g_last if g_last is not None else 0.05)
        d["revenue_growth_y1"] = _clamp(g1, -0.2, 0.6)
        why["revenue_growth_y1"] = "Analyst consensus for next fiscal year." if cons is not None else "Last fiscal year's revenue growth."
        revs = [m["revenue"] for m in metrics if m["revenue"]]
        cagr = (revs[-1] / revs[0]) ** (1 / (len(revs) - 1)) - 1 if len(revs) > 1 and revs[0] > 0 else d["revenue_growth_y1"]
        # Scale discipline: the bigger the revenue base, the lower the sustainable multi-year growth ceiling
        # (40% for a $50B-revenue company, ~25% at $330B, floor 8%). Avoids extrapolating hyper-growth.
        rev0 = revs[-1] if revs else 0
        cap = _clamp(0.40 * (50e9 / rev0) ** 0.25, 0.08, 0.40) if rev0 > 50e9 else 0.40
        raw = 0.85 * (d["revenue_growth_y1"] + cagr) / 2
        d["revenue_growth_y2_5"] = _clamp(raw, -0.05, cap)
        why["revenue_growth_y2_5"] = f"Fades the {len(revs) - 1}-year historical CAGR ({cagr:.1%}) and year-1 growth by 15% for scale."
        if raw > cap:
            why["revenue_growth_y2_5"] += f" Capped at {cap:.0%} for a ${rev0 / 1e9:,.0f}B revenue base."
        m_last = last["operating_margin"] or 0.0
        adjusted = " (adjusted: " + ", ".join(i["item"] for i in earnings.get("items", [])) + ")" if earnings.get("items") else ""
        if earnings.get("normalize") and earnings.get("average_margin") is not None:
            m_last = earnings["average_margin"]
            why["operating_margin_y1"] = f"Normalized: average margin across the {len(metrics)}-year cycle{adjusted}."
        else:
            why["operating_margin_y1"] = f"Trailing fiscal-year operating margin{adjusted}."
        d["operating_margin_y1"] = m_last
        m_avg = _avg(metrics, "operating_margin") or m_last
        d["target_operating_margin"] = max(m_last, m_avg) if m_last > 0 else 0.10
        why["target_operating_margin"] = "Higher of current and 3-year average margin." if m_last > 0 else "Loss-making today: assumes a generic 10% margin at maturity."
        gm = last.get("gross_margin")
        if gm is not None and d["target_operating_margin"] > gm:
            d["target_operating_margin"] = gm
            why["target_operating_margin"] += f" Capped at the {gm:.1%} gross margin (unit economics set the ceiling)."
        d["margin_convergence_year"] = 5
        why["margin_convergence_year"] = "Margins reach target by the end of the high-growth phase."
        s2c = last.get("sales_to_capital")
        d["sales_to_capital"] = _clamp(s2c, 0.5, 5.0) if s2c else 2.0
        why["sales_to_capital"] = "Current revenue / invested capital (book equity + debt + leases − cash)." if s2c else "Invested capital not meaningful; uses 2.0x."
        d["sales_to_capital_late"] = d["sales_to_capital"]
        why["sales_to_capital_late"] = "Same efficiency as years 1-5 unless scale or excess capacity changes it."
        d["wacc_initial"] = coc.wacc
        why["wacc_initial"] = f"CAPM with beta {coc.beta:.2f}, ERP {coc.erp:.2%}, synthetic rating {coc.rating}."
        d["wacc_terminal"] = coc.terminal_wacc
        why["wacc_terminal"] = "Mature-firm cost of capital: beta converges to 1."
        d["terminal_growth"] = min(rf, 0.04, coc.terminal_wacc - 0.01)
        why["terminal_growth"] = ("The lower of the risk-free rate and 4% long-run nominal growth: no firm outgrows the "
                                  "economy forever.")
        # Excess returns fade but rarely vanish for firms that earn them today: keep half of today's spread
        # over the mature cost of capital (ROIC capped at 35%). Firms without excess returns get ROIC = WACC.
        roic_now = last.get("roic")
        spread = max(0.0, min(roic_now or 0.0, 0.35) - coc.terminal_wacc)
        d["terminal_roc"] = coc.terminal_wacc + 0.5 * spread
        why["terminal_roc"] = (f"Half of today's excess return persists: current ROIC {roic_now:.1%} vs mature cost of capital "
                               f"{coc.terminal_wacc:.1%}." if spread > 0 else
                               "Return on capital equals cost of capital in stable growth (no excess returns today).")
        t = last.get("effective_tax_rate")
        d["effective_tax_rate"] = _clamp(t, 0.0, 0.35) if t is not None else US_MARGINAL_TAX
        why["effective_tax_rate"] = "Trailing effective tax rate."
        d["marginal_tax_rate"] = US_MARGINAL_TAX
        why["marginal_tax_rate"] = "US federal 21% plus average state taxes."
        distressed = m_last < 0 and (snap["history"][-1].get("cash") or 0) < abs(last["ebit"] or 0) * 2
        d["prob_failure"] = 0.1 if distressed else 0.0
        why["prob_failure"] = "Losses and under two years of cash runway." if distressed else "Established, cash-generating business."
    elif method == "ddm":
        roe = _avg(metrics, "roe") or 0.1
        payout = _clamp(last.get("payout_ratio") or (snap.get("payout_ratio") or 0.5), 0.0, 1.0)
        ke_s = rf + coc.erp
        d.update({
            "roe_high": roe, "payout_high": payout, "cost_of_equity_high": coc.cost_of_equity,
            "cost_of_equity_stable": ke_s, "terminal_growth": min(rf, ke_s - 0.01),
            "roe_stable": max(ke_s, min(roe, ke_s + 0.02)),
        })
        why.update({
            "roe_high": "3-year average return on equity.",
            "payout_high": "Trailing dividends / net income.",
            "cost_of_equity_high": f"CAPM with beta {coc.beta:.2f}.",
            "cost_of_equity_stable": "Beta converges to 1 in stable growth.",
            "terminal_growth": "Capped at the risk-free rate.",
            "roe_stable": "Stable ROE at most 2 points above the cost of equity.",
        })
    elif method == "excess_return":
        roe_last = last.get("roe") or 0.1
        roe_avg = _avg(metrics, "roe") or roe_last
        ke_s = rf + coc.erp
        cr = last.get("cash_return_ratio")
        d.update({
            "roe_y1": roe_last, "roe_target": roe_avg,
            "payout_high": _clamp(cr if cr is not None else 0.4, 0.0, 1.0),
            "cost_of_equity_high": coc.cost_of_equity, "cost_of_equity_stable": ke_s,
            "terminal_growth": min(rf, ke_s - 0.01), "roe_stable": min(roe_avg, ke_s + 0.01),
        })
        why.update({
            "roe_y1": "Trailing return on average equity.",
            "roe_target": "3-year average ROE.",
            "payout_high": "Dividends + buybacks as a share of net income.",
            "cost_of_equity_high": f"CAPM with beta {coc.beta:.2f}.",
            "cost_of_equity_stable": "Beta converges to 1 in stable growth.",
            "terminal_growth": "Capped at the risk-free rate.",
            "roe_stable": "Excess returns fade: stable ROE at most 1 point above cost of equity.",
        })
    return d, why
