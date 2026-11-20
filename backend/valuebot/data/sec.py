"""SEC EDGAR: ticker → CIK lookup and annual financials from XBRL "companyfacts".

Docs: https://www.sec.gov/edgar/sec-api-documentation
SEC asks for a descriptive User-Agent and ≤10 requests/second.
"""
from __future__ import annotations

import datetime as dt
import functools
from typing import Any

import httpx

from ..config import settings

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FILING_INDEX_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K"

ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}

# Ordered candidate tags per line item; first tag with data wins.
DURATION_TAGS: dict[str, list[str]] = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "RevenuesNetOfInterestExpense",
    ],
    "operating_income": ["OperatingIncomeLoss"],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "income_tax": ["IncomeTaxExpenseBenefit"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "interest_expense": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"],
    "dividends_paid": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "depreciation": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"],
    "rnd": ["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"],
    "gross_profit": ["GrossProfit"],
    "acquisitions": ["PaymentsToAcquireBusinessesNetOfCashAcquired"],
}
INSTANT_TAGS: dict[str, list[str]] = {
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "marketable_securities": ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "long_term_debt": ["LongTermDebt"],
    "long_term_debt_noncurrent": ["LongTermDebtNoncurrent"],
    "debt_current": ["LongTermDebtCurrent", "DebtCurrent"],
    "short_term_borrowings": ["ShortTermBorrowings", "CommercialPaper"],
    "operating_leases": ["OperatingLeaseLiability"],
    "equity": ["StockholdersEquity"],
    "minority_interest": ["MinorityInterest"],
    "total_assets": ["Assets"],
    "equity_investments": ["EquityMethodInvestments"],
    "nol": ["OperatingLossCarryforwards"],
    "options_outstanding": ["ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingNumber"],
    "options_strike": ["ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingWeightedAverageExercisePrice"],
}


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": settings.sec_user_agent, "Accept-Encoding": "gzip, deflate"}, timeout=30)


@functools.lru_cache(maxsize=1)
def ticker_map() -> dict[str, dict[str, Any]]:
    with _client() as c:
        raw = c.get(TICKERS_URL).raise_for_status().json()
    return {row["ticker"].upper(): {"cik": int(row["cik_str"]), "name": row["title"]} for row in raw.values()}


def search(query: str, limit: int = 8) -> list[dict[str, Any]]:
    q = query.strip().upper()
    tm = ticker_map()
    hits = []
    if q in tm:
        hits.append({"ticker": q, **tm[q]})
    for t, row in tm.items():
        if len(hits) >= limit:
            break
        if t != q and (t.startswith(q) or q in row["name"].upper()):
            hits.append({"ticker": t, **row})
    return hits


def _days(start: str, end: str) -> int:
    return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days


def _annual_series(facts: dict, tag: str, instant: bool) -> dict[str, float]:
    """Return {period_end: value} for annual (10-K-type) observations of one tag."""
    node = facts.get("facts", {}).get("us-gaap", {}).get(tag)
    if not node:
        return {}
    units = node.get("units", {})
    obs = units.get("USD") or next(iter(units.values()), [])
    out: dict[str, tuple[str, float]] = {}
    for o in obs:
        if o.get("form") not in ANNUAL_FORMS:
            continue
        if instant:
            if "start" in o:
                continue
        else:
            if "start" not in o or not 350 <= _days(o["start"], o["end"]) <= 380:
                continue
        end = o["end"]
        # keep the most recently filed value for each period (restatements win)
        if end not in out or o.get("filed", "") > out[end][0]:
            out[end] = (o.get("filed", ""), float(o["val"]))
    return {k: v for k, (_, v) in out.items()}


def _first(facts: dict, tags: list[str], instant: bool) -> tuple[dict[str, float], str | None]:
    for tag in tags:
        s = _annual_series(facts, tag, instant)
        if s:
            return s, tag
    return {}, None


def fetch_financials(ticker: str, years: int = 5) -> dict[str, Any]:
    tm = ticker_map()
    t = ticker.upper()
    if t not in tm:
        raise LookupError(f"{ticker} is not an SEC registrant")
    cik = tm[t]["cik"]
    with _client() as c:
        facts = c.get(FACTS_URL.format(cik=cik)).raise_for_status().json()
        subs = c.get(SUBMISSIONS_URL.format(cik=cik)).raise_for_status().json()

    series: dict[str, dict[str, float]] = {}
    tags_used: dict[str, str] = {}
    for key, tags in DURATION_TAGS.items():
        series[key], tag = _first(facts, tags, instant=False)
        if tag:
            tags_used[key] = tag
    for key, tags in INSTANT_TAGS.items():
        series[key], tag = _first(facts, tags, instant=True)
        if tag:
            tags_used[key] = tag

    ends = sorted(series["revenue"].keys())[-years:] if series["revenue"] else sorted(series["net_income"].keys())[-years:]
    history = []
    for end in ends:
        row: dict[str, Any] = {"period_end": end, "fiscal_year": int(end[:4])}
        for key in list(DURATION_TAGS) + list(INSTANT_TAGS):
            row[key] = series[key].get(end)
        if row["long_term_debt"] is None:
            row["long_term_debt"] = (row.get("long_term_debt_noncurrent") or 0) + (row.get("debt_current") or 0) or None
        row["debt"] = (row.get("long_term_debt") or 0) + (row.get("short_term_borrowings") or 0)
        row["lease_liabilities"] = row.get("operating_leases") or 0
        row["cash"] = (row.get("cash") or 0) + (row.get("marketable_securities") or 0)
        history.append(row)

    shares = None
    dei = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding")
    if dei:
        obs = sorted(next(iter(dei["units"].values())), key=lambda o: o["end"])
        shares = float(obs[-1]["val"]) if obs else None

    recent = subs.get("filings", {}).get("recent", {})
    filings = []
    for form, acc, date, doc in zip(recent.get("form", []), recent.get("accessionNumber", []),
                                    recent.get("filingDate", []), recent.get("primaryDocument", [])):
        if form in {"10-K", "10-Q", "8-K", "20-F", "40-F"} and len(filings) < 12:
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"
            filings.append({"form": form, "date": date, "url": url})

    return {
        "cik": cik,
        "name": facts.get("entityName") or tm[t]["name"],
        "sic_description": subs.get("sicDescription"),
        "fiscal_year_end": subs.get("fiscalYearEnd"),
        "shares_outstanding": shares,
        "history": history,
        "xbrl_tags": tags_used,
        "filings": filings,
        "source": {"label": "SEC EDGAR XBRL company facts", "url": FACTS_URL.format(cik=cik)},
    }
