"""Cost of capital: CAPM cost of equity, synthetic-rating cost of debt, market-value WACC.

The interest-coverage → rating → default-spread table follows the structure of
Damodaran's synthetic rating table for large non-financial firms. The spreads
move every year: refresh them from his "ratings.htm" dataset each January.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# (minimum interest coverage, rating, default spread). Ordered high -> low.
RATING_TABLE: list[tuple[float, str, float]] = [
    (8.50, "AAA", 0.0059),
    (6.50, "AA", 0.0070),
    (5.50, "A+", 0.0092),
    (4.25, "A", 0.0107),
    (3.00, "A-", 0.0121),
    (2.50, "BBB", 0.0147),
    (2.25, "BB+", 0.0193),
    (2.00, "BB", 0.0226),
    (1.75, "B+", 0.0300),
    (1.50, "B", 0.0400),
    (1.25, "B-", 0.0500),
    (0.80, "CCC", 0.0800),
    (0.65, "CC", 0.1000),
    (0.20, "C", 0.1200),
    (float("-inf"), "D", 0.1500),
]


def synthetic_rating(ebit: float, interest_expense: float) -> tuple[str, float, float]:
    """Return (rating, default spread, coverage ratio)."""
    if not interest_expense or interest_expense <= 0:
        return "AAA", RATING_TABLE[0][2], float("inf")
    coverage = ebit / interest_expense
    for min_cov, rating, spread in RATING_TABLE:
        if coverage >= min_cov:
            return rating, spread, coverage
    return "D", RATING_TABLE[-1][2], coverage  # pragma: no cover


@dataclass
class CostOfCapital:
    riskfree: float
    erp: float
    beta: float
    country_risk_premium: float
    cost_of_equity: float
    rating: str
    default_spread: float
    interest_coverage: float
    pretax_cost_of_debt: float
    marginal_tax_rate: float
    aftertax_cost_of_debt: float
    equity_weight: float
    debt_weight: float
    wacc: float
    terminal_wacc: float  # mature-firm cost of capital: beta -> 1, same weights

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["interest_coverage"] == float("inf"):
            d["interest_coverage"] = None
        return d


def compute_cost_of_capital(
    *,
    riskfree: float,
    erp: float,
    beta: float,
    market_cap: float,
    debt: float,
    ebit: float,
    interest_expense: float,
    marginal_tax_rate: float = 0.25,
    country_risk_premium: float = 0.0,
) -> CostOfCapital:
    beta = beta if beta and beta > 0 else 1.0
    ke = riskfree + beta * erp + country_risk_premium
    rating, spread, coverage = synthetic_rating(ebit, interest_expense)
    kd_pre = riskfree + spread
    kd_post = kd_pre * (1 - marginal_tax_rate)
    total = max(market_cap, 0) + max(debt, 0)
    we = market_cap / total if total > 0 else 1.0
    wd = 1 - we
    wacc = ke * we + kd_post * wd
    # Mature firm: average risk (beta 1), no country premium beyond what stays.
    ke_mature = riskfree + 1.0 * erp + country_risk_premium
    terminal = ke_mature * we + kd_post * wd
    return CostOfCapital(
        riskfree=riskfree,
        erp=erp,
        beta=beta,
        country_risk_premium=country_risk_premium,
        cost_of_equity=ke,
        rating=rating,
        default_spread=spread,
        interest_coverage=coverage,
        pretax_cost_of_debt=kd_pre,
        marginal_tax_rate=marginal_tax_rate,
        aftertax_cost_of_debt=kd_post,
        equity_weight=we,
        debt_weight=wd,
        wacc=wacc,
        terminal_wacc=terminal,
    )
