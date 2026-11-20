"""Input adjustments from Damodaran's valuation class ("measure earnings right", risk inputs, loose ends).

Every function is pure and unit-tested against the worked examples in the slides
(Amgen R&D, Egypt risk-free rate, Amgen bottom-up beta, Citi implied cost of equity, ...).
"""
from __future__ import annotations

import math
from typing import Any

# Amortizable life of R&D by industry (Damodaran's rules of thumb: software ~3 years,
# light manufacturing/tech hardware ~5, pharma/biotech ~10).
RND_LIFE_HINTS: list[tuple[tuple[str, ...], int]] = [
    (("software", "internet", "application", "saas", "information technology services"), 3),
    (("drug", "pharma", "biotech"), 10),
    (("semiconductor", "electronic", "hardware", "auto", "aerospace", "machinery", "medical"), 5),
]


def rnd_life_for(industry: str | None) -> int:
    t = (industry or "").lower()
    for keys, life in RND_LIFE_HINTS:
        if any(k in t for k in keys):
            return life
    return 5


# ------------------------------------------------------------------------------ measure earnings right
def capitalize_rnd(rnd_history: list[float], life: int) -> dict[str, Any]:
    """Capitalize R&D as an asset amortized straight-line over `life` years.

    `rnd_history` is oldest → newest; the last element is the current year. If fewer than
    `life` prior years are available, earlier years are extrapolated back at the observed
    R&D growth rate (capped at 0-30%), and flagged.

    Returns research asset (unamortized R&D), this year's amortization, and the EBIT adjustment
    (+ current R&D − amortization).
    """
    life = max(1, int(life))
    hist = [float(x) for x in rnd_history if x is not None and x >= 0]
    if not hist:
        return {"applied": False}
    extrapolated = 0
    if len(hist) < life + 1:
        if len(hist) > 1 and hist[0] > 0:
            g = (hist[-1] / hist[0]) ** (1 / (len(hist) - 1)) - 1
        else:
            g = 0.0
        g = min(max(g, 0.0), 0.30)
        while len(hist) < life + 1:
            hist.insert(0, hist[0] / (1 + g))
            extrapolated += 1
    current = hist[-1]
    rows, asset, amort = [], 0.0, 0.0
    for k in range(0, life + 1):  # k = 0 is current year
        x = hist[-1 - k]
        unamortized = (life - k) / life
        a_this = x / life if k >= 1 else 0.0
        asset += x * unamortized
        amort += a_this
        rows.append({"year": -k, "rnd": x, "unamortized_pct": unamortized, "unamortized": x * unamortized,
                     "amortization": a_this})
    return {"applied": True, "life": life, "research_asset": asset, "amortization": amort,
            "current_rnd": current, "ebit_adjustment": current - amort, "extrapolated_years": extrapolated,
            "rows": rows}


def lease_ebit_adjustment(lease_debt: float, pretax_cost_of_debt: float) -> float:
    """Operating lease expense is part interest, part depreciation. Once leases are treated as debt,
    the interest component (≈ lease debt × pre-tax cost of debt) is added back to operating income."""
    return max(lease_debt or 0.0, 0.0) * pretax_cost_of_debt


# ------------------------------------------------------------------------------ risk inputs
def riskfree_in_currency(rf_usd: float, inflation_local: float, inflation_us: float) -> float:
    """Differential inflation: rf_local = (1 + rf_US$) × (1 + inflation_local) / (1 + inflation_US) − 1."""
    return (1 + rf_usd) * (1 + inflation_local) / (1 + inflation_us) - 1


def riskfree_from_govt_bond(govt_bond_rate: float, sovereign_default_spread: float) -> float:
    """A government bond is risk-free only if the government is default-free: net out its default spread."""
    return govt_bond_rate - sovereign_default_spread


def erp_from_exposure(mature_erp: float, exposures: list[dict]) -> tuple[float, float]:
    """ERP weighted by where the company *operates* (revenues), not where it is incorporated.

    exposures: [{"region": str, "weight": float, "crp": float}] — weights are normalised.
    Returns (total ERP, weighted country risk premium).
    """
    rows = [e for e in exposures or [] if (e.get("weight") or 0) > 0]
    tot = sum(float(e["weight"]) for e in rows)
    if not rows or tot <= 0:
        return mature_erp, 0.0
    crp = sum(float(e["weight"]) / tot * float(e.get("crp") or 0.0) for e in rows)
    return mature_erp + crp, crp


def country_crp_from_default_spread(default_spread: float, sd_equity: float, sd_bond: float) -> float:
    """CRP = default spread × (σ equity market / σ government bond)."""
    return default_spread * sd_equity / sd_bond


def relever_beta(unlevered: float, debt_to_equity: float, tax_rate: float) -> float:
    """Levered beta = unlevered beta × (1 + (1 − t) × D/E)."""
    return unlevered * (1 + (1 - tax_rate) * debt_to_equity)


def bottom_up_beta(segments: list[dict], debt_to_equity: float, tax_rate: float) -> dict[str, Any] | None:
    """Value- (or revenue-) weighted unlevered beta of the businesses the firm is in, relevered.

    segments: [{"name", "weight", "unlevered_beta"}]; rows without a beta are ignored.
    """
    rows = [s for s in segments or [] if s.get("unlevered_beta") not in (None, "") and (s.get("weight") or 0) > 0]
    tot = sum(float(s["weight"]) for s in rows)
    if not rows or tot <= 0:
        return None
    bu = sum(float(s["weight"]) / tot * float(s["unlevered_beta"]) for s in rows)
    return {"unlevered_beta": bu, "levered_beta": relever_beta(bu, debt_to_equity, tax_rate),
            "debt_to_equity": debt_to_equity, "segments": rows}


def implied_cost_of_equity_from_pbv(pbv: float, roe: float, g: float) -> float | None:
    """Stable-growth P/BV = (ROE − g) / (Ke − g)  ⇒  Ke = (ROE − g) / (P/BV) + g."""
    if not pbv or pbv <= 0:
        return None
    return (roe - g) / pbv + g


# ------------------------------------------------------------------------------ loose ends
def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def black_scholes_call(s: float, k: float, t: float, sigma: float, r: float, y: float = 0.0) -> float:
    if t <= 0 or sigma <= 0 or s <= 0 or k <= 0:
        return max(0.0, s - k)
    d1 = (math.log(s / k) + (r - y + sigma ** 2 / 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    return s * math.exp(-y * t) * _norm_cdf(d1) - k * math.exp(-r * t) * _norm_cdf(d2)


def employee_options_value(*, n_options: float, strike: float, maturity: float, price: float, shares: float,
                           sigma: float, r: float, y: float = 0.0, iters: int = 20) -> float:
    """Value of employee options outstanding (Black-Scholes, adjusted for dilution).

    Damodaran nets this value out of equity *before* dividing by primary shares, rather than
    using a diluted share count. Dilution: the stock price is adjusted to
    (price × shares + option value × options) / (shares + options), solved iteratively.
    """
    if not n_options or n_options <= 0:
        return 0.0
    val = black_scholes_call(price, strike, maturity, sigma, r, y)
    for _ in range(iters):
        s_adj = (price * shares + val * n_options) / (shares + n_options)
        new = black_scholes_call(s_adj, strike, maturity, sigma, r, y)
        if abs(new - val) < 1e-9:
            break
        val = new
    return val * n_options


# ------------------------------------------------------------------------------ insights
def value_of_growth(ebit: float, tax_rate: float, wacc: float, operating_asset_value: float) -> dict[str, float]:
    """Split operating assets into the value of existing assets (status quo, no growth) and growth assets.

    Status quo value = EBIT × (1 − t) / cost of capital (current earnings forever, no reinvestment)."""
    status_quo = ebit * (1 - tax_rate) / wacc if wacc > 0 else 0.0
    return {"existing_assets": status_quo, "growth_assets": operating_asset_value - status_quo,
            "growth_share": (operating_asset_value - status_quo) / operating_asset_value if operating_asset_value else None}


def implied_multiples(*, equity_value: float, price: float, shares: float, debt: float, cash: float,
                      revenue: float | None, ebit: float | None, net_income: float | None,
                      book_equity: float | None) -> dict[str, dict[str, float | None]]:
    """Pricing cross-check: the multiples our value implies versus what the market pays today."""
    def mult(eq: float) -> dict[str, float | None]:
        ev = eq + debt - cash
        return {
            "ev_sales": ev / revenue if revenue else None,
            "ev_ebit": ev / ebit if ebit and ebit > 0 else None,
            "pe": eq / net_income if net_income and net_income > 0 else None,
            "pbv": eq / book_equity if book_equity and book_equity > 0 else None,
        }
    return {"at_value": mult(equity_value), "at_price": mult(price * shares)}


CONVENTIONAL_MULTIPLE = [  # Damodaran, "conventional usage" by sector
    (("bank", "insurance", "financial", "capital markets"), "Price / book equity", "Assets marked to market"),
    (("reit", "real estate"), "Price / (net income + depreciation)", "Big depreciation charges on real estate"),
    (("utilit", "telecom", "infrastructure", "pipeline"), "EV / EBITDA", "Early losses, big depreciation"),
    (("retail",), "EV / sales", "Margins equalize sooner or later"),
    (("auto", "steel", "chemical", "mining", "oil", "gas", "metal", "airline", "construction"), "PE (normalized earnings)", "Cyclical: earnings swing with the cycle"),
]


def conventional_multiple(sector: str | None, industry: str | None, growth: float | None, profitable: bool) -> tuple[str, str]:
    t = f"{sector or ''} {industry or ''}".lower()
    for keys, m, why in CONVENTIONAL_MULTIPLE:
        if any(k in t for k in keys):
            return m, why
    if not profitable:
        return "EV / sales", "Young growth firm with losses: little choice but revenue multiples"
    if growth is not None and growth > 0.15:
        return "PEG ratio", "Big differences in growth rates across firms"
    return "PE", "Profitable firm with stable earnings"
