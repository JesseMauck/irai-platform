"""Ticker-report datasets: dividends, earnings (quarterly + annual), full financial statements, technicals,
peers & ratios and preferred securities. Every response names its source.

Sources
* Yahoo Finance (via yfinance) — statements, dividends, earnings dates/EPS surprises, preferred listings.
  Yahoo standardises figures from company filings; SEC EDGAR links are attached for verification.
* SEC EDGAR XBRL — annual diluted EPS and net income history for US registrants.
* Computed — technical indicators are calculated here from daily closes.
"""
from __future__ import annotations

import datetime as dt
import math
import threading
import time
from typing import Any

from .config import settings
from .market import service
from .market.source import _num

YAHOO = {"label": "Yahoo Finance (standardised from company filings)", "url": "https://finance.yahoo.com/quote/{s}"}
_cache: dict[tuple[str, str], tuple[float, Any]] = {}
_lock = threading.Lock()


def _memo(kind: str, key: str, ttl: float, fn):
    now = time.time()
    with _lock:
        hit = _cache.get((kind, key))
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    with _lock:
        _cache[(kind, key)] = (now, val)
    return val


def _src(symbol: str, extra: dict | None = None) -> dict:
    return {"label": YAHOO["label"], "url": YAHOO["url"].format(s=symbol), **(extra or {})}


def _ticker(symbol: str):
    import yfinance as yf

    return yf.Ticker(symbol)


def _clean(v: Any) -> Any:
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return v


def _frame_to_rows(df) -> tuple[list[str], list[dict[str, Any]]]:
    """yfinance statement frame (rows = line items, columns = period ends) → (periods, rows)."""
    if df is None or getattr(df, "empty", True):
        return [], []
    cols = list(df.columns)[:8]
    periods = [c.date().isoformat() if hasattr(c, "date") else str(c) for c in cols]
    rows = []
    for item, series in df[cols].iterrows():
        vals = [_clean(series[c]) for c in cols]
        if all(v is None for v in vals):
            continue
        rows.append({"item": str(item), "values": vals})
    return periods, rows


# ── financial statements ─────────────────────────────────────────────────────────────────────────
STATEMENT_ORDER = {
    "income": ["Total Revenue", "Cost Of Revenue", "Gross Profit", "Research And Development", "Selling General And Administration",
               "Operating Expense", "Operating Income", "Interest Expense", "Pretax Income", "Tax Provision", "Net Income",
               "Diluted EPS", "Basic EPS", "Diluted Average Shares", "EBITDA", "EBIT"],
    "balance": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Receivables", "Inventory",
                "Current Assets", "Net PPE", "Goodwill And Other Intangible Assets", "Total Assets", "Current Liabilities",
                "Total Debt", "Long Term Debt", "Total Liabilities Net Minority Interest", "Stockholders Equity",
                "Total Equity Gross Minority Interest", "Ordinary Shares Number", "Working Capital", "Net Debt"],
    "cashflow": ["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow", "Depreciation And Amortization",
                 "Stock Based Compensation", "Change In Working Capital", "Investing Cash Flow", "Financing Cash Flow",
                 "Repurchase Of Capital Stock", "Cash Dividends Paid", "Issuance Of Debt", "Repayment Of Debt", "End Cash Position"],
}


def statements(symbol: str, period: str = "annual") -> dict[str, Any]:
    symbol = service.normalise_symbol(symbol)
    if not settings.live:
        return {"symbol": symbol, "period": period, "income": None, "balance": None, "cashflow": None, "source": "DEMO",
                "note": "Financial statements need live mode."}

    def fetch():
        t = _ticker(symbol)
        q = period == "quarterly"
        frames = {"income": t.quarterly_income_stmt if q else t.income_stmt,
                  "balance": t.quarterly_balance_sheet if q else t.balance_sheet,
                  "cashflow": t.quarterly_cashflow if q else t.cashflow}
        out: dict[str, Any] = {"symbol": symbol, "period": period, "source": "LIVE", "provider": _src(symbol),
                               "verify": _edgar(symbol)}
        for k, df in frames.items():
            periods, rows = _frame_to_rows(df)
            order = {n: i for i, n in enumerate(STATEMENT_ORDER[k])}
            rows.sort(key=lambda r: (order.get(r["item"], 999), r["item"]))
            out[k] = {"periods": periods, "rows": rows, "key_items": [r["item"] for r in rows if r["item"] in order]}
        return out

    try:
        return _memo("stmt:" + period, symbol, 6 * 3600, fetch)
    except Exception as e:  # noqa: BLE001
        return {"symbol": symbol, "period": period, "income": None, "balance": None, "cashflow": None, "source": "ERROR",
                "note": f"Statements unavailable: {type(e).__name__}"}


def _edgar(symbol: str) -> dict | None:
    try:
        from valuebot.data import sec

        cik = sec.ticker_map().get(symbol, {}).get("cik")
    except Exception:  # noqa: BLE001
        cik = None
    if not cik:
        return None
    return {"label": "SEC EDGAR filings", "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K"}


# ── dividends ────────────────────────────────────────────────────────────────────────────────────
def dividends(symbol: str) -> dict[str, Any]:
    symbol = service.normalise_symbol(symbol)
    price = service.quote(symbol).get("price")
    if not settings.live:
        return {"symbol": symbol, "history": [], "source": "DEMO", "note": "Dividend history needs live mode."}

    def fetch():
        t = _ticker(symbol)
        s = t.dividends
        hist = [{"date": d.date().isoformat(), "amount": float(v)} for d, v in (s.items() if s is not None else [])][-80:]
        try:
            info = service.info(symbol)
        except Exception:  # noqa: BLE001
            info = {}
        cutoff = (dt.date.today() - dt.timedelta(days=365)).isoformat()
        ttm = sum(h["amount"] for h in hist if h["date"] >= cutoff)
        by_year: dict[int, float] = {}
        for h in hist:
            by_year[int(h["date"][:4])] = by_year.get(int(h["date"][:4]), 0.0) + h["amount"]
        years = sorted(y for y in by_year if y < dt.date.today().year)
        growth = None
        if len(years) >= 6 and by_year[years[-6]] > 0:
            growth = (by_year[years[-1]] / by_year[years[-6]]) ** (1 / 5) - 1
        streak = 0
        for a, b in zip(reversed(years[:-1]), reversed(years[1:])):
            if by_year[b] > by_year[a] * 1.0001:
                streak += 1
            else:
                break
        tinfo = t.info or {}
        return {"symbol": symbol, "history": hist, "annual": [{"year": y, "total": round(by_year[y], 6)} for y in years[-15:]],
                "ttm_per_share": ttm or None, "yield_ttm": (ttm / price) if ttm and price else None,
                "forward_rate": _num(tinfo.get("dividendRate")), "forward_yield": _num(tinfo.get("dividendYield")),
                "payout_ratio": _num(tinfo.get("payoutRatio")), "ex_dividend_date": _epoch(tinfo.get("exDividendDate")),
                "five_year_growth": growth, "consecutive_increases": streak, "source": "LIVE", "provider": _src(symbol),
                "fund_note": "For funds and CEFs, distributions may include return of capital." if info.get("quote_type") in ("ETF", "MUTUALFUND") else None}

    try:
        return _memo("div", symbol, 6 * 3600, fetch)
    except Exception as e:  # noqa: BLE001
        return {"symbol": symbol, "history": [], "source": "ERROR", "note": f"Dividends unavailable: {type(e).__name__}"}


def _epoch(v) -> str | None:
    try:
        return dt.datetime.fromtimestamp(int(v), dt.timezone.utc).date().isoformat() if v else None
    except (TypeError, ValueError, OSError):
        return None


# ── earnings ─────────────────────────────────────────────────────────────────────────────────────
def earnings(symbol: str) -> dict[str, Any]:
    """Quarterly EPS (estimate vs actual, surprise) and annual earnings history."""
    symbol = service.normalise_symbol(symbol)
    if not settings.live:
        return {"symbol": symbol, "quarterly": [], "annual": [], "source": "DEMO", "note": "Earnings need live mode."}

    def fetch():
        t = _ticker(symbol)
        quarterly = []
        try:
            ed = t.get_earnings_dates(limit=16)
        except Exception:  # noqa: BLE001
            ed = None
        if ed is not None and not ed.empty:
            for d, r in ed.iterrows():
                est, act = _clean(r.get("EPS Estimate")), _clean(r.get("Reported EPS"))
                quarterly.append({"date": d.date().isoformat(), "eps_estimate": est, "eps_actual": act,
                                  "surprise_pct": _clean(r.get("Surprise(%)")),
                                  "upcoming": act is None and d.date() >= dt.date.today()})
        q_inc = t.quarterly_income_stmt
        q_rev = []
        if q_inc is not None and not q_inc.empty:
            for c in list(q_inc.columns)[:8]:
                q_rev.append({"period_end": c.date().isoformat(),
                              "revenue": _clean(q_inc.at["Total Revenue", c]) if "Total Revenue" in q_inc.index else None,
                              "net_income": _clean(q_inc.at["Net Income", c]) if "Net Income" in q_inc.index else None,
                              "diluted_eps": _clean(q_inc.at["Diluted EPS", c]) if "Diluted EPS" in q_inc.index else None})
        annual = _sec_annual_eps(symbol)
        if not annual:
            inc = t.income_stmt
            if inc is not None and not inc.empty:
                for c in list(inc.columns)[:10]:
                    annual.append({"fiscal_year_end": c.date().isoformat(),
                                   "net_income": _clean(inc.at["Net Income", c]) if "Net Income" in inc.index else None,
                                   "diluted_eps": _clean(inc.at["Diluted EPS", c]) if "Diluted EPS" in inc.index else None,
                                   "revenue": _clean(inc.at["Total Revenue", c]) if "Total Revenue" in inc.index else None,
                                   "source": "Yahoo Finance"})
        return {"symbol": symbol, "quarterly": quarterly, "quarterly_financials": q_rev, "annual": annual, "source": "LIVE",
                "provider": _src(symbol), "annual_provider": annual[0]["source"] if annual else None}

    try:
        return _memo("earn", symbol, 3 * 3600, fetch)
    except Exception as e:  # noqa: BLE001
        return {"symbol": symbol, "quarterly": [], "annual": [], "source": "ERROR", "note": f"Earnings unavailable: {type(e).__name__}"}


def _sec_annual_eps(symbol: str, years: int = 10) -> list[dict[str, Any]]:
    """Annual diluted EPS, net income and revenue straight from SEC XBRL (US registrants)."""
    try:
        from valuebot.data import sec

        tm = sec.ticker_map()
        if symbol not in tm:
            return []
        with sec._client() as c:
            facts = c.get(sec.FACTS_URL.format(cik=tm[symbol]["cik"])).raise_for_status().json()
    except Exception:  # noqa: BLE001
        return []
    eps = {}
    node = facts.get("facts", {}).get("us-gaap", {}).get("EarningsPerShareDiluted")
    if node:
        for o in next(iter(node["units"].values()), []):
            if o.get("form") in sec.ANNUAL_FORMS and "start" in o and 350 <= sec._days(o["start"], o["end"]) <= 380:
                if o["end"] not in eps or o.get("filed", "") > eps[o["end"]][0]:
                    eps[o["end"]] = (o.get("filed", ""), float(o["val"]))
    ni, _ = sec._first(facts, sec.DURATION_TAGS["net_income"], False)
    rev, _ = sec._first(facts, sec.DURATION_TAGS["revenue"], False)
    ends = sorted(set(eps) | set(ni))[-years:]
    url = sec.FACTS_URL.format(cik=tm[symbol]["cik"])
    return [{"fiscal_year_end": e, "diluted_eps": eps.get(e, (None, None))[1], "net_income": ni.get(e), "revenue": rev.get(e),
             "source": "SEC EDGAR XBRL", "source_url": url} for e in reversed(ends)]


# ── technicals ───────────────────────────────────────────────────────────────────────────────────
def _sma(xs: list[float], n: int) -> float | None:
    return sum(xs[-n:]) / n if len(xs) >= n else None


def _ema_series(xs: list[float], n: int) -> list[float]:
    k, out = 2 / (n + 1), []
    for x in xs:
        out.append(x if not out else out[-1] + k * (x - out[-1]))
    return out


def _rsi(xs: list[float], n: int = 14) -> float | None:
    """Wilder's RSI."""
    if len(xs) <= n:
        return None
    gains = [max(0.0, b - a) for a, b in zip(xs, xs[1:])]
    losses = [max(0.0, a - b) for a, b in zip(xs, xs[1:])]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag, al = (ag * (n - 1) + g) / n, (al * (n - 1) + l) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def technicals(symbol: str) -> dict[str, Any]:
    symbol = service.normalise_symbol(symbol)
    c = service.chart(symbol, "2y")
    closes = [h["close"] for h in c["history"] if h.get("close")]
    q = c["quote"]
    px = q.get("price") or (closes[-1] if closes else None)
    if len(closes) < 30 or not px:
        return {"symbol": symbol, "source": q.get("source"), "note": "Not enough price history for technicals."}
    sma = {n: _sma(closes, n) for n in (20, 50, 100, 200)}
    ema12, ema26 = _ema_series(closes, 12), _ema_series(closes, 26)
    macd_line = [a - b for a, b in zip(ema12, ema26)]
    signal = _ema_series(macd_line, 9)
    mid = sma[20]
    sd = (sum((x - mid) ** 2 for x in closes[-20:]) / 20) ** 0.5 if mid else None
    rets = [b / a - 1 for a, b in zip(closes, closes[1:]) if a]
    vol20 = (sum(r * r for r in rets[-20:]) / 20) ** 0.5 * math.sqrt(252) if len(rets) >= 20 else None
    hi52, lo52 = max(closes[-252:]), min(closes[-252:])

    def perf(n):
        return closes[-1] / closes[-1 - n] - 1 if len(closes) > n else None

    rsi = _rsi(closes)
    trend = ("Uptrend" if sma[50] and sma[200] and px > sma[50] > sma[200] else
             "Downtrend" if sma[50] and sma[200] and px < sma[50] < sma[200] else "Mixed")
    signals = []
    if sma[50] and sma[200]:
        prev50, prev200 = _sma(closes[:-5], 50), _sma(closes[:-5], 200)
        if prev50 and prev200 and (prev50 - prev200) * (sma[50] - sma[200]) < 0:
            signals.append("Golden cross (50-day crossed above 200-day) in the last week" if sma[50] > sma[200]
                           else "Death cross (50-day crossed below 200-day) in the last week")
    if rsi is not None and rsi >= 70:
        signals.append(f"RSI {rsi:.0f}: overbought territory")
    if rsi is not None and rsi <= 30:
        signals.append(f"RSI {rsi:.0f}: oversold territory")
    if sd and mid and px > mid + 2 * sd:
        signals.append("Price above the upper Bollinger band")
    if sd and mid and px < mid - 2 * sd:
        signals.append("Price below the lower Bollinger band")
    return {"symbol": symbol, "price": px, "sma": sma, "distance_from_sma": {n: (px / v - 1) if v else None for n, v in sma.items()},
            "rsi14": rsi, "macd": {"macd": macd_line[-1], "signal": signal[-1], "histogram": macd_line[-1] - signal[-1]},
            "bollinger": {"middle": mid, "upper": mid + 2 * sd if sd else None, "lower": mid - 2 * sd if sd else None},
            "volatility_20d_ann": vol20, "high_52w": hi52, "low_52w": lo52, "from_high_52w": px / hi52 - 1,
            "from_low_52w": px / lo52 - 1,
            "performance": {"1w": perf(5), "1m": perf(21), "3m": perf(63), "6m": perf(126), "1y": perf(252)},
            "trend": trend, "signals": signals, "source": q.get("source"),
            "provider": {"label": "Computed by Irradiance from daily closes", "url": None},
            "note": "Technical indicators describe past price behaviour; they are not predictions."}


# ── peers and ratios ─────────────────────────────────────────────────────────────────────────────
RATIO_KEYS = [("market_cap", "Market cap"), ("trailing_pe", "P/E (ttm)"), ("forward_pe", "P/E (fwd)"),
              ("ev_ebitda", "EV/EBITDA"), ("price_to_sales", "P/S"), ("price_to_book", "P/B"), ("peg_ratio", "PEG"),
              ("gross_margin", "Gross margin"), ("operating_margin", "Operating margin"), ("profit_margin", "Net margin"),
              ("roe", "ROE"), ("revenue_growth", "Revenue growth"), ("earnings_growth", "Earnings growth"),
              ("debt_to_equity", "Debt/Equity (%)"), ("dividend_yield", "Dividend yield"), ("beta", "Beta")]


def peers(symbol: str, extra: list[str] | None = None) -> dict[str, Any]:
    from sqlalchemy import select

    from .db import SessionLocal
    from .models import PeerMember

    symbol = service.normalise_symbol(symbol)
    names: list[str] = []
    group = None
    with SessionLocal() as s:
        m = s.scalar(select(PeerMember).where(PeerMember.symbol == symbol))
        if m:
            group = m.group.name
            names = [x.symbol for x in m.group.members if x.symbol != symbol]
    if not names:
        names = _industry_peers(symbol)
    names = [symbol] + [n for n in (extra or []) + names if n != symbol][:9]
    rows = []
    for sym, inf in service_infos(names).items():
        q = service.quote(sym)
        rows.append({"symbol": sym, "name": inf.get("name") or q.get("name"), "price": q.get("price"),
                     "change_pct": q.get("change_pct"), **{k: inf.get(k) for k, _ in RATIO_KEYS},
                     "source": "DEMO" if "DEMO" in (q.get("source"), inf.get("source")) else q.get("source")})
    med = {}
    for k, _ in RATIO_KEYS:
        vals = sorted(r[k] for r in rows[1:] if isinstance(r.get(k), (int, float)))
        med[k] = vals[len(vals) // 2] if vals else None
    return {"symbol": symbol, "group": group or "Same industry", "columns": [{"key": k, "label": lab} for k, lab in RATIO_KEYS],
            "rows": rows, "peer_median": med, "provider": {"label": "Yahoo Finance key statistics", "url": None},
            "note": "Peers are Irradiance's curated group where available, otherwise companies in the same industry."}


def service_infos(symbols: list[str]) -> dict[str, dict]:
    from .market.source import parallel

    res = parallel(lambda s: service.info(s), symbols, workers=6)
    return {s: (v if isinstance(v, dict) else {}) for s, v in res.items()}


def _industry_peers(symbol: str) -> list[str]:
    """Best-effort industry peers from Yahoo's recommendation list."""
    if not settings.live:
        return []
    try:
        import httpx

        r = httpx.get(f"https://query2.finance.yahoo.com/v6/finance/recommendationsbysymbol/{symbol}",
                      headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        recs = r.json()["finance"]["result"][0]["recommendedSymbols"]
        return [x["symbol"] for x in recs][:8]
    except Exception:  # noqa: BLE001
        return []


# ── preferred securities ─────────────────────────────────────────────────────────────────────────
def preferreds(symbol: str) -> dict[str, Any]:
    """Exchange-listed preferred shares of the same issuer (Yahoo symbols like JPM-PD)."""
    symbol = service.normalise_symbol(symbol)
    if not settings.live:
        return {"symbol": symbol, "preferreds": [], "source": "DEMO"}

    def fetch():
        found: dict[str, dict] = {}
        for q in (f"{symbol} preferred", f"{symbol}-P"):
            try:
                for hit in service.search(q):
                    s = (hit.get("symbol") or "").upper()
                    if s.startswith(symbol + "-P") or s.startswith(symbol + "-") and len(s) <= len(symbol) + 4:
                        found[s] = hit
            except Exception:  # noqa: BLE001
                pass
        rows = []
        for s, hit in sorted(found.items()):
            try:
                qte = service.quote(s)
                inf = service.info(s)
            except Exception:  # noqa: BLE001
                continue
            rate = inf.get("dividend_yield")
            rows.append({"symbol": s, "name": hit.get("name") or qte.get("name"), "price": qte.get("price"),
                         "change_pct": qte.get("change_pct"), "yield": rate, "source": qte.get("source")})
        return {"symbol": symbol, "preferreds": rows, "source": "LIVE",
                "provider": {"label": "Yahoo Finance listings", "url": f"https://finance.yahoo.com/lookup?s={symbol}-P"},
                "note": "Shows exchange-listed preferreds found for this issuer; check each prospectus for call dates, "
                        "coupon resets and cumulative status." if rows else "No exchange-listed preferred shares found."}

    try:
        return _memo("pref", symbol, 12 * 3600, fetch)
    except Exception as e:  # noqa: BLE001
        return {"symbol": symbol, "preferreds": [], "source": "ERROR", "note": f"Unavailable: {type(e).__name__}"}
