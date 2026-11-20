"""Fictional demo companies for offline runs and tests.

These are NOT real companies; every number is made up so the full pipeline can
run without network access or API keys (VALUEBOT_OFFLINE=1).
"""
from __future__ import annotations

import copy

M = 1_000_000


def _hist(rows: list[tuple]) -> list[dict]:
    keys = ["fiscal_year", "revenue", "operating_income", "pretax_income", "income_tax", "net_income",
            "interest_expense", "cash", "debt", "lease_liabilities", "equity", "minority_interest",
            "dividends_paid", "buybacks", "rnd", "total_assets"]
    out = []
    for r in rows:
        d = dict(zip(keys, r))
        for k in keys[1:]:
            if d[k] is not None:
                d[k] = d[k] * M
        d["period_end"] = f"{d['fiscal_year']}-12-31"
        out.append(d)
    return out


_DEMO_NOTE = "Fictional demo company — numbers are invented for offline testing."

FIXTURES: dict[str, dict] = {
    "DEMO": {
        "ticker": "DEMO",
        "name": "Northwind Analytics Inc. (demo)",
        "sector": "Technology",
        "industry": "Software—Application",
        "country": "United States",
        "currency": "USD",
        "price": 84.50,
        "shares": 410 * M,
        "beta": 1.25,
        "summary": "Northwind sells a cloud analytics platform to mid-market and enterprise customers on "
                   "annual subscriptions, with usage-based add-ons for data storage and AI features.",
        "dividend_rate": 0.0,
        "payout_ratio": 0.0,
        "consensus": {"target_mean_price": 95.0, "recommendation": "buy", "analyst_count": 22,
                      "revenue_growth_next_fy": 0.17},
        "history": _hist([
            (2021, 2150, 86, 70, 14, 56, 18, 1900, 1200, 210, 2600, 0, 0, 0, 640, 6100),
            (2022, 2720, 190, 172, 34, 138, 20, 2050, 1200, 230, 2950, 0, 0, 150, 790, 6800),
            (2023, 3310, 365, 350, 70, 280, 20, 2300, 1150, 240, 3300, 0, 0, 300, 930, 7400),
            (2024, 3920, 545, 532, 106, 426, 19, 2600, 1100, 250, 3720, 0, 0, 420, 1060, 8100),
            (2025, 4560, 730, 720, 151, 569, 18, 2950, 1050, 260, 4200, 0, 0, 500, 1180, 8900),
        ]),
        "news": [
            {"title": "Northwind launches AI copilot add-on priced per seat (demo headline)", "publisher": "Demo Wire", "date": "2026-10-02", "url": None},
            {"title": "Northwind raises FY guidance on strong enterprise bookings (demo headline)", "publisher": "Demo Wire", "date": "2026-08-05", "url": None},
        ],
    },
    "DEMOB": {
        "ticker": "DEMOB",
        "name": "Harborview Bancorp (demo)",
        "sector": "Financial Services",
        "industry": "Banks—Regional",
        "country": "United States",
        "currency": "USD",
        "price": 41.20,
        "shares": 150 * M,
        "beta": 1.05,
        "summary": "Harborview is a regional bank with $60bn of assets, funded mostly by retail deposits "
                   "and lending to commercial real estate, small business and consumers.",
        "dividend_rate": 1.60,
        "payout_ratio": 0.38,
        "consensus": {"target_mean_price": 45.0, "recommendation": "hold", "analyst_count": 14},
        "history": _hist([
            (2021, 2400, None, 820, 170, 650, 210, 3000, 4000, 0, 5200, 0, 230, 100, None, 52000),
            (2022, 2600, None, 900, 190, 710, 380, 2800, 4200, 0, 5450, 0, 240, 120, None, 55000),
            (2023, 2750, None, 760, 160, 600, 900, 3300, 4500, 0, 5600, 0, 245, 50, None, 58000),
            (2024, 2820, None, 800, 168, 632, 1100, 3500, 4400, 0, 5850, 0, 238, 60, None, 59500),
            (2025, 2950, None, 860, 181, 679, 1050, 3600, 4300, 0, 6100, 0, 240, 80, None, 61000),
        ]),
        "news": [{"title": "Harborview reserves rise on office CRE exposure (demo headline)", "publisher": "Demo Wire", "date": "2026-10-20", "url": None}],
    },
    "DEMOU": {
        "ticker": "DEMOU",
        "name": "Cascade Power & Light (demo)",
        "sector": "Utilities",
        "industry": "Utilities—Regulated Electric",
        "country": "United States",
        "currency": "USD",
        "price": 58.00,
        "shares": 300 * M,
        "beta": 0.55,
        "summary": "Cascade is a regulated electric utility serving 2.1 million customers, earning an "
                   "allowed return on a growing rate base as it invests in grid and renewables.",
        "dividend_rate": 2.40,
        "payout_ratio": 0.68,
        "consensus": {"target_mean_price": 61.0, "recommendation": "hold", "analyst_count": 12},
        "history": _hist([
            (2021, 7100, 1650, 1200, 180, 1020, 520, 150, 14000, 0, 11500, 0, 640, 0, None, 38000),
            (2022, 7600, 1720, 1250, 190, 1060, 560, 160, 14800, 0, 11900, 0, 670, 0, None, 40000),
            (2023, 7900, 1800, 1290, 195, 1095, 610, 180, 15500, 0, 12300, 0, 700, 0, None, 42000),
            (2024, 8200, 1880, 1340, 200, 1140, 650, 170, 16200, 0, 12700, 0, 730, 0, None, 44000),
            (2025, 8600, 1970, 1400, 210, 1190, 690, 190, 17000, 0, 13150, 0, 760, 0, None, 46500),
        ]),
        "news": [{"title": "Regulator approves Cascade rate case with 9.6% allowed ROE (demo headline)", "publisher": "Demo Wire", "date": "2026-09-14", "url": None}],
    },
}


# Extra line items (gross profit, employee options, NOLs) for the demo companies.
_EXTRAS = {
    "DEMO": {"gross_margin": 0.76, "options_outstanding": 14 * M, "options_strike": 38.0, "nol": 0.0},
    "DEMOU": {"gross_margin": 0.42},
}


def get(ticker: str) -> dict:
    t = ticker.upper()
    if t not in FIXTURES:
        raise LookupError(f"{ticker} is not available offline. Demo tickers: {', '.join(FIXTURES)}")
    snap = copy.deepcopy(FIXTURES[t])
    ex = _EXTRAS.get(t, {})
    for h in snap["history"]:
        if "gross_margin" in ex and h.get("revenue"):
            h["gross_profit"] = h["revenue"] * ex["gross_margin"]
    for k in ("options_outstanding", "options_strike", "nol"):
        if k in ex:
            snap["history"][-1][k] = ex[k]
    snap.update({
        "demo": True,
        "market_cap": snap["price"] * snap["shares"],
        "filings": [],
        "riskfree": 0.0395,
        "riskfree_source": "Demo risk-free rate (10y Treasury net of US default spread)",
        "sources": [{"label": _DEMO_NOTE, "url": None}],
    })
    return snap


def search(query: str) -> list[dict]:
    q = query.upper()
    return [{"ticker": t, "name": f["name"]} for t, f in FIXTURES.items() if q in t or q in f["name"].upper()]
