import pytest

from valuebot.engine import registry
from valuebot.engine.cost_of_capital import compute_cost_of_capital, synthetic_rating

FCFF = dict(revenue0=1000, ebit0=150, invested_capital0=800, cash=200, debt=300, minority_interest=0,
            non_operating_assets=0, options_value=0, shares=100, price=20, failure_proceeds_pct=0.5,
            revenue_growth_y1=0.1, revenue_growth_y2_5=0.08, operating_margin_y1=0.15, target_operating_margin=0.18,
            margin_convergence_year=5, sales_to_capital=1.5, sales_to_capital_late=1.5, wacc_initial=0.09, wacc_terminal=0.085,
            terminal_growth=0.04, terminal_roc=0.12, effective_tax_rate=0.21, marginal_tax_rate=0.25, prob_failure=0)


def test_fcff_hand_check_terminal():
    r = registry.run("fcff", FCFF)
    last = r.table[-1]
    assert last["revenue_growth"] == pytest.approx(0.04)  # converged to stable growth
    assert last["operating_margin"] == pytest.approx(0.18)
    assert last["cost_of_capital"] == pytest.approx(0.085)
    t = r.terminal
    nopat = last["revenue"] * 1.04 * 0.18 * 0.75
    fcff = nopat * (1 - 0.04 / 0.12)
    assert t["terminal_value"] == pytest.approx(fcff / (0.085 - 0.04))
    # bridge adds up
    b = dict(r.bridge)
    assert b["Value of equity"] == pytest.approx(b["Adjusted for probability of failure"] - 300 + 200)
    assert r.value_per_share == pytest.approx(b["Value of common equity"] / 100)


def test_fcff_higher_margin_more_value_and_failure_less():
    base = registry.run("fcff", FCFF).value_per_share
    assert registry.run("fcff", {**FCFF, "target_operating_margin": 0.25}).value_per_share > base
    assert registry.run("fcff", {**FCFF, "prob_failure": 0.2}).value_per_share < base


def test_growth_capped_below_cost_of_capital():
    r = registry.run("fcff", {**FCFF, "terminal_growth": 0.10})
    assert r.terminal["growth"] == pytest.approx(0.08)
    assert r.warnings


def test_ddm_no_growth_perpetuity():
    # zero growth, full payout, flat Ke -> value = EPS / Ke
    a = dict(eps0=5, shares=1, price=50, roe_high=0.1, payout_high=1.0, cost_of_equity_high=0.1,
             cost_of_equity_stable=0.1, terminal_growth=0.0, roe_stable=0.1)
    assert registry.run("ddm", a).value_per_share == pytest.approx(50)


def test_excess_return_zero_spread_equals_book():
    a = dict(book_equity0=1000, shares=10, price=90, roe_y1=0.1, roe_target=0.1, payout_high=0.5,
             cost_of_equity_high=0.1, cost_of_equity_stable=0.1, terminal_growth=0.03, roe_stable=0.1)
    assert registry.run("excess_return", a).value_per_share == pytest.approx(100)


def test_sensitivity_shapes():
    s = registry.sensitivity("fcff", FCFF)
    assert s["drivers"][0]["range"] >= s["drivers"][-1]["range"]
    assert s["scenarios"]["bear"]["value_per_share"] < s["base_value"] < s["scenarios"]["bull"]["value_per_share"]


def test_method_selection():
    assert registry.choose_method(sector="Financial Services", industry="Banks—Regional", payout_ratio=0.4,
                                  pays_dividends=True, has_revenue=True)[0] == "excess_return"
    assert registry.choose_method(sector="Utilities", industry="Utilities—Regulated Electric", payout_ratio=0.7,
                                  pays_dividends=True, has_revenue=True)[0] == "ddm"
    assert registry.choose_method(sector="Technology", industry="Software", payout_ratio=0.0,
                                  pays_dividends=False, has_revenue=True)[0] == "fcff"


def test_cost_of_capital():
    assert synthetic_rating(100, 5)[0] == "AAA"
    assert synthetic_rating(10, 10)[0] == "CCC"
    c = compute_cost_of_capital(riskfree=0.04, erp=0.05, beta=1.2, market_cap=800, debt=200, ebit=100,
                                interest_expense=10, marginal_tax_rate=0.25)
    assert c.cost_of_equity == pytest.approx(0.10)
    assert c.wacc == pytest.approx(0.8 * 0.10 + 0.2 * (0.04 + c.default_spread) * 0.75)
