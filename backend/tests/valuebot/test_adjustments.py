"""Each adjustment checked against the worked example on Damodaran's class slides."""
import pytest

from valuebot.engine import adjustments as adj


def test_amgen_rnd_capitalization():
    # Slide "Capitalizing R&D expenses: Amgen" — 10-year life, oldest -> current
    rnd = [558, 631, 663, 823, 845, 865, 1117, 1655, 2028, 2314, 3366]
    r = adj.capitalize_rnd(rnd, 10)
    assert r["research_asset"] == pytest.approx(10113, abs=1)
    assert r["amortization"] == pytest.approx(1150, abs=1)
    # Adjusted operating income = 5,120 + 3,366 − 1,150 = 7,336
    assert 5120 + r["ebit_adjustment"] == pytest.approx(7336, abs=1)
    assert r["extrapolated_years"] == 0


def test_rnd_extrapolates_short_history():
    r = adj.capitalize_rnd([100, 110, 121], 5)
    assert r["extrapolated_years"] == 3
    assert r["research_asset"] > 121  # includes unamortized prior years


def test_egypt_riskfree_by_differential_inflation():
    # Slide: rf EGP = 1.0227 × (1.097 / 1.015) − 1 = 10.53%
    assert adj.riskfree_in_currency(0.0227, 0.097, 0.015) == pytest.approx(0.1053, abs=1e-4)


def test_riskfree_nets_sovereign_default_spread():
    assert adj.riskfree_from_govt_bond(0.2681, 0.0446) == pytest.approx(0.2235)  # Enka / Turkey


def test_india_country_risk_premium():
    # CRP = 2% × (21% / 14%) = 3%; total ERP = 6% + 3% = 9%
    crp = adj.country_crp_from_default_spread(0.02, 0.21, 0.14)
    assert crp == pytest.approx(0.03)
    erp, w = adj.erp_from_exposure(0.06, [{"region": "India", "weight": 1, "crp": crp}])
    assert erp == pytest.approx(0.09)


def test_erp_weighted_by_operations():
    erp, crp = adj.erp_from_exposure(0.0423, [{"region": "US", "weight": 60, "crp": 0.0},
                                              {"region": "Brazil", "weight": 40, "crp": 0.05}])
    assert crp == pytest.approx(0.02)
    assert erp == pytest.approx(0.0623)


def test_amgen_bottom_up_beta():
    # Slide shows 1.59 × (1 + (1 − .35)(.11)) = "1.73"; the arithmetic is 1.704 (slide rounding/typo).
    b = adj.bottom_up_beta([{"name": "Pharma", "weight": 1, "unlevered_beta": 1.59}], 0.11, 0.35)
    assert b["levered_beta"] == pytest.approx(1.59 * (1 + 0.65 * 0.11))
    # Tata Motors: 0.98 × (1 + (1 − .3399)(.3387)) = 1.20
    assert adj.relever_beta(0.98, 0.3387, 0.3399) == pytest.approx(1.20, abs=0.005)


def test_citi_implied_cost_of_equity_from_pbv():
    # PBV 1.04 = (12% − 3.3%) / (Ke − 3.3%)  ⇒  Ke = 11.67%
    assert adj.implied_cost_of_equity_from_pbv(1.04, 0.12, 0.033) == pytest.approx(0.1167, abs=1e-4)


def test_black_scholes_and_dilution():
    c = adj.black_scholes_call(100, 100, 1, 0.2, 0.05)
    assert c == pytest.approx(10.4506, abs=1e-3)  # textbook value
    v = adj.employee_options_value(n_options=10, strike=100, maturity=1, price=100, shares=100, sigma=0.2, r=0.05)
    assert 0 < v < 10 * c  # dilution lowers per-option value


def test_value_of_growth_split():
    g = adj.value_of_growth(ebit=100, tax_rate=0.25, wacc=0.075, operating_asset_value=1500)
    assert g["existing_assets"] == pytest.approx(1000)
    assert g["growth_assets"] == pytest.approx(500)


def test_rnd_life_hints():
    assert adj.rnd_life_for("Software—Application") == 3
    assert adj.rnd_life_for("Drug Manufacturers") == 10
    assert adj.rnd_life_for("Restaurants") == 5
