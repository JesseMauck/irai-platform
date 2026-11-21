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
# Holding-company reorganisations move a ticker to a new SEC registrant (CIK) whose XBRL history starts at the
# reorganisation. Facts from the predecessor registrant(s) are merged in so annual history continues.
PREDECESSOR_CIKS: dict[str, list[int]] = {
    "XOM": [34088],  # ExxonMobil Holdings Corp (2026) ← Exxon Mobil Corporation
}

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
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
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


def _quarters(obs: list[dict]) -> dict[str, tuple[str, float]]:
    """Discrete fiscal quarters {end: (start, value)} from mixed 10-Q/10-K duration facts.

    10-Q income items are usually reported as three-month figures, but cash-flow items are reported
    year-to-date (3, 6, 9 months) and Q4 appears only inside the annual total. Quarters missing as direct
    observations are derived by differencing cumulative values that share a start date:
    Q2 = H1 - Q1, Q3 = 9M - H1, Q4 = FY - 9M."""
    latest: dict[tuple[str, str], tuple[str, float]] = {}
    for o in obs:
        if "start" not in o:
            continue
        k = (o["start"], o["end"])
        if k not in latest or o.get("filed", "") > latest[k][0]:
            latest[k] = (o.get("filed", ""), float(o["val"]))
    q: dict[str, tuple[str, float]] = {}
    for (st, en), (_, v) in latest.items():
        if 80 <= _days(st, en) <= 100:
            q[en] = (st, v)
    by_start: dict[str, list[tuple[str, float]]] = {}
    for (st, en), (_, v) in latest.items():
        if 80 <= _days(st, en) <= 380:
            by_start.setdefault(st, []).append((en, v))
    for st, pts in by_start.items():
        pts.sort()
        for (e0, v0), (e1, v1) in zip(pts, pts[1:]):
            if 80 <= _days(e0, e1) <= 100 and e1 not in q:
                q[e1] = (e0, v1 - v0)
    # a cumulative figure minus the quarter that closes it gives the preceding period: H1 - Q2 = Q1
    for (st, en), (_, v) in latest.items():
        if 170 <= _days(st, en) <= 190 and en in q:
            qs, qv = q[en]
            prev_end = (dt.date.fromisoformat(qs) - dt.timedelta(days=1)).isoformat()
            if 80 <= _days(st, prev_end) <= 100 and prev_end not in q and not any(abs(_days(e, prev_end)) <= 10 for e in q):
                q[prev_end] = (st, v - qv)
    return q


def _ttm_series(facts: dict, tag: str, instant: bool) -> dict[str, float]:
    """Trailing-twelve-month value from quarterly data, for registrants with no usable annual report yet
    (new holding companies, recent IPOs). Duration items: sum of the latest four consecutive quarters,
    derived from year-to-date figures where needed (see _quarters). Instant items: the latest balance."""
    node = facts.get("facts", {}).get("us-gaap", {}).get(tag)
    if not node:
        return {}
    obs = [o for o in (node.get("units", {}).get("USD") or []) if o.get("form") in {"10-Q", "10-Q/A", "6-K"} | ANNUAL_FORMS]
    if instant:
        pts = sorted((o["end"], float(o["val"])) for o in obs if "start" not in o)
        return {pts[-1][0]: pts[-1][1]} if pts else {}
    q = _quarters(obs)
    ends = sorted(q)
    if len(ends) < 4:
        return {}
    last4 = ends[-4:]
    # consecutive: each quarter starts within ~10 days of the previous quarter's end
    for prev, cur in zip(last4, last4[1:]):
        if abs(_days(prev, q[cur][0])) > 10:
            return {}
    return {last4[-1]: sum(q[e][1] for e in last4)}


def _first(facts: dict, tags: list[str], instant: bool) -> tuple[dict[str, float], str | None]:
    """Best series for a line item across candidate tags.

    Companies switch tags over time (Microsoft reported `Revenues` until ~2010, then
    `RevenueFromContractWithCustomerExcludingAssessedTax`). Taking the first tag that has *any* data
    silently returns a decade-old series, so: pick the tag whose data is most recent (ties → more
    history, then the candidate order), and back-fill earlier periods it lacks from the other tags.
    """
    found = [(tag, s) for tag in tags if (s := _annual_series(facts, tag, instant))]
    if not found:
        return {}, None
    order = {t: i for i, t in enumerate(tags)}
    found.sort(key=lambda ts: (max(ts[1]), len(ts[1]), -order[ts[0]]), reverse=True)
    best_tag, best = found[0]
    merged = dict(best)
    for _, other in found[1:]:
        for end, v in other.items():
            merged.setdefault(end, v)
    return merged, best_tag


def merge_facts(primary: dict, older: dict) -> dict:
    """Union of two companyfacts documents (successor first). Observations for the same period from both
    registrants are kept; the series builders already pick the most recently filed value per period."""
    out = {**primary, "facts": {}}
    for ns in set(primary.get("facts", {})) | set(older.get("facts", {})):
        a, b = primary.get("facts", {}).get(ns, {}), older.get("facts", {}).get(ns, {})
        merged = {}
        for tag in set(a) | set(b):
            units: dict[str, list] = {}
            for src in (b.get(tag), a.get(tag)):
                for unit, obs in ((src or {}).get("units") or {}).items():
                    units.setdefault(unit, []).extend(obs)
            merged[tag] = {**(b.get(tag) or {}), **(a.get(tag) or {}), "units": units}
        out["facts"][ns] = merged
    return out


def fetch_financials(ticker: str, years: int = 5) -> dict[str, Any]:
    tm = ticker_map()
    t = ticker.upper()
    if t not in tm:
        raise LookupError(f"{ticker} is not an SEC registrant")
    cik = tm[t]["cik"]
    with _client() as c:
        facts = c.get(FACTS_URL.format(cik=cik)).raise_for_status().json()
        subs = c.get(SUBMISSIONS_URL.format(cik=cik)).raise_for_status().json()
        for pcik in PREDECESSOR_CIKS.get(t, []):
            try:
                facts = merge_facts(facts, c.get(FACTS_URL.format(cik=pcik)).raise_for_status().json())
            except httpx.HTTPError:
                pass

    series: dict[str, dict[str, float]] = {}
    tags_used: dict[str, str] = {}
    annual = any(_first(facts, DURATION_TAGS[k], False)[0] for k in ("revenue", "net_income"))
    for key, tags in DURATION_TAGS.items():
        series[key], tag = _first(facts, tags, instant=False)
        if not annual:
            series[key], tag = {}, None
            for t2 in tags:
                if (ttm := _ttm_series(facts, t2, False)):
                    series[key], tag = ttm, t2 + " (TTM from 10-Qs)"
                    break
        if tag:
            tags_used[key] = tag
    for key, tags in INSTANT_TAGS.items():
        series[key], tag = _first(facts, tags, instant=True)
        if not annual:
            series[key], tag = {}, None
            for t2 in tags:
                if (latest := _ttm_series(facts, t2, True)):
                    series[key], tag = latest, t2 + " (latest 10-Q)"
                    break
        if tag:
            tags_used[key] = tag
    if not annual:
        # Align instant balances with the TTM period end so rows line up.
        end = next(iter(series["revenue"] or series["net_income"] or {}), None)
        if end:
            for key in INSTANT_TAGS:
                if series[key]:
                    series[key] = {end: next(iter(series[key].values()))}

    ends = sorted(series["revenue"].keys())[-years:] if series["revenue"] else sorted(series["net_income"].keys())[-years:]
    history = []
    for end in ends:
        row: dict[str, Any] = {"period_end": end, "fiscal_year": int(end[:4])}
        for key in list(DURATION_TAGS) + list(INSTANT_TAGS):
            row[key] = series[key].get(end)
        # Some filers tag only part of their borrowings as LongTermDebt (e.g. one note programme) while the
        # balance sheet shows noncurrent + current debt; take the larger so debt is never undercounted.
        parts = (row.get("long_term_debt_noncurrent") or 0) + (row.get("debt_current") or 0)
        if row["long_term_debt"] is None or parts > row["long_term_debt"]:
            row["long_term_debt"] = parts or row["long_term_debt"]
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

    latest = history[-1]["period_end"] if history else None
    stale = latest is not None and (dt.date.today() - dt.date.fromisoformat(latest)).days > 550
    return {
        "cik": cik,
        "latest_period_end": latest,
        "basis": "annual" if annual else "ttm_10q",
        "stale": stale,
        "name": facts.get("entityName") or tm[t]["name"],
        "sic_description": subs.get("sicDescription"),
        "fiscal_year_end": subs.get("fiscalYearEnd"),
        "shares_outstanding": shares,
        "history": history,
        "xbrl_tags": tags_used,
        "filings": filings,
        "source": {"label": "SEC EDGAR XBRL company facts", "url": FACTS_URL.format(cik=cik)},
    }
