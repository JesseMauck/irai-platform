"""Market data via yfinance: price, beta, shares, sector, consensus, news, and the 10y Treasury.

Also provides a financial-statement fallback for companies that don't file
with the SEC (non-US listings).
"""
from __future__ import annotations

import math
from typing import Any

from ..config import settings


def _yf():
    import yfinance as yf  # imported lazily so offline mode needs no network deps

    return yf


def _num(x: Any) -> float | None:
    try:
        f = float(x)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def riskfree_rate() -> tuple[float, str]:
    """US$ risk-free rate = 10-year Treasury yield minus the US sovereign default spread (Aa1)."""
    try:
        hist = _yf().Ticker("^TNX").history(period="5d")
        if not hist.empty:
            tbond = float(hist["Close"].iloc[-1]) / 100
            return tbond - settings.us_default_spread, (
                f"10-year US Treasury {tbond:.2%} (Yahoo Finance ^TNX) minus US default spread "
                f"{settings.us_default_spread:.2%}")
    except Exception:  # noqa: BLE001
        pass
    return settings.default_riskfree, "Default risk-free rate (VALUEBOT_RISKFREE)"


def quote(ticker: str) -> dict[str, Any]:
    t = _yf().Ticker(ticker)
    info = t.info or {}
    price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice")) or _num(info.get("previousClose"))
    if price is None:
        raise LookupError(f"No market data for {ticker}")
    out = {
        "name": info.get("longName") or info.get("shortName") or ticker,
        "price": price,
        "currency": info.get("currency", "USD"),
        "financial_currency": info.get("financialCurrency", info.get("currency", "USD")),
        "market_cap": _num(info.get("marketCap")),
        "shares_outstanding": _num(info.get("sharesOutstanding")),
        "beta": _num(info.get("beta")),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "summary": info.get("longBusinessSummary"),
        "dividend_rate": _num(info.get("dividendRate")),
        "payout_ratio": _num(info.get("payoutRatio")),
        "trailing_eps": _num(info.get("trailingEps")),
        "book_value_per_share": _num(info.get("bookValue")),
        "consensus": {
            "target_mean_price": _num(info.get("targetMeanPrice")),
            "target_low_price": _num(info.get("targetLowPrice")),
            "target_high_price": _num(info.get("targetHighPrice")),
            "recommendation": info.get("recommendationKey"),
            "analyst_count": info.get("numberOfAnalystOpinions"),
            "revenue_growth_ttm": _num(info.get("revenueGrowth")),
        },
        "source": {"label": "Yahoo Finance quote", "url": f"https://finance.yahoo.com/quote/{ticker}"},
    }
    try:
        est = t.revenue_estimate  # newer yfinance versions
        if est is not None and not est.empty and "growth" in est.columns:
            out["consensus"]["revenue_growth_next_fy"] = _num(est.loc["+1y", "growth"]) if "+1y" in est.index else None
    except Exception:  # noqa: BLE001
        pass
    return out


def news(ticker: str, limit: int = 8) -> list[dict[str, Any]]:
    try:
        items = _yf().Ticker(ticker).news or []
    except Exception:  # noqa: BLE001
        return []
    out = []
    for it in items[:limit]:
        c = it.get("content", it)
        url = (c.get("canonicalUrl") or {}).get("url") if isinstance(c.get("canonicalUrl"), dict) else c.get("link")
        out.append({"title": c.get("title"), "publisher": (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict) else c.get("publisher"),
                    "date": c.get("pubDate") or c.get("providerPublishTime"), "url": url})
    return [n for n in out if n["title"]]


_IS_MAP = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "operating_income": ["Operating Income", "EBIT"],
    "pretax_income": ["Pretax Income"],
    "income_tax": ["Tax Provision"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "interest_expense": ["Interest Expense"],
    "rnd": ["Research And Development"],
}
_BS_MAP = {
    "cash": ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"],
    "debt": ["Total Debt"],
    "equity": ["Stockholders Equity", "Common Stock Equity"],
    "minority_interest": ["Minority Interest"],
    "total_assets": ["Total Assets"],
    "lease_liabilities": ["Long Term Capital Lease Obligation"],
}
_CF_MAP = {
    "dividends_paid": ["Cash Dividends Paid", "Common Stock Dividend Paid"],
    "buybacks": ["Repurchase Of Capital Stock"],
    "capex": ["Capital Expenditure"],
    "depreciation": ["Depreciation And Amortization"],
}


def financials_fallback(ticker: str, years: int = 5) -> dict[str, Any]:
    """Annual statements from Yahoo Finance for non-SEC filers."""
    t = _yf().Ticker(ticker)
    frames = [(t.income_stmt, _IS_MAP), (t.balance_sheet, _BS_MAP), (t.cashflow, _CF_MAP)]
    by_year: dict[str, dict[str, Any]] = {}
    for df, mapping in frames:
        if df is None or df.empty:
            continue
        for col in df.columns:
            end = str(col.date())
            row = by_year.setdefault(end, {"period_end": end, "fiscal_year": int(end[:4])})
            for key, labels in mapping.items():
                for lab in labels:
                    if lab in df.index and _num(df.loc[lab, col]) is not None:
                        v = _num(df.loc[lab, col])
                        row[key] = abs(v) if key in {"dividends_paid", "buybacks", "capex"} else v
                        break
    history = [by_year[k] for k in sorted(by_year)][-years:]
    return {"history": history, "filings": [],
            "source": {"label": "Yahoo Finance financial statements", "url": f"https://finance.yahoo.com/quote/{ticker}/financials"}}
