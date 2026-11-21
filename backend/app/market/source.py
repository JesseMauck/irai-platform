"""Market data sources.

`YahooSource` is the live source: Yahoo Finance's public chart endpoint for quotes and daily history
(one request returns both), its search endpoint for symbol lookup, and yfinance for fundamentals and
fund NAVs. `DemoSource` produces deterministic, clearly-labelled fictional data so the product runs
with no network (IRAI_MARKET_MODE=demo) and in tests.

Every quote carries `source`: LIVE (fetched from the live feed) or DEMO (synthetic).
Quotes from Yahoo's free endpoints are typically real-time for US listings and delayed 15-20 minutes
for many non-US exchanges; `delayed_minutes` is filled from the feed's metadata where available.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import random
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

import httpx

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
CHART_HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")
CHART_URL = CHART_HOSTS[0] + "/v8/finance/chart/{symbol}"
SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"


class SourceError(RuntimeError):
    pass


class RateLimited(SourceError):
    """The feed refused us for sending too many requests (HTTP 429). Callers should back off."""


def _browser_session():
    """A curl_cffi session that presents a real browser TLS fingerprint. Yahoo rate-limits generic HTTP
    clients from cloud IPs far more aggressively than browsers; falls back to httpx if unavailable."""
    try:
        from curl_cffi import requests as creq

        return creq.Session(impersonate="chrome", timeout=10)
    except Exception:  # noqa: BLE001
        return None


class MarketSource(Protocol):
    name: str

    def chart(self, symbol: str, range_: str = "1y", interval: str = "1d") -> dict[str, Any]: ...
    def info(self, symbol: str) -> dict[str, Any]: ...
    def search(self, q: str) -> list[dict[str, Any]]: ...


def parse_bars(symbol: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Yahoo v8 chart -> OHLCV bars with full UTC timestamps (works for intraday, daily and weekly intervals)."""
    try:
        res = payload["chart"]["result"][0]
    except (KeyError, IndexError, TypeError):
        raise SourceError(f"No bars for {symbol}")
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    out = []
    for i, t in enumerate(res.get("timestamp") or []):
        c = _num((q.get("close") or [None])[i] if i < len(q.get("close") or []) else None)
        if c is None or c <= 0:
            continue
        g = lambda k: _num((q.get(k) or [None] * (i + 1))[i]) if i < len(q.get(k) or []) else None  # noqa: E731
        o, h, lo = g("open") or c, g("high") or c, g("low") or c
        out.append({"t": dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(), "o": o, "h": max(h, o, c), "l": min(lo, o, c), "c": c, "v": g("volume") or 0.0})
    return out


BAR_STEPS = {"15m": 15, "1h": 60, "60m": 60, "1d": 1440, "1wk": 10080}
BAR_COUNTS = {"15m": 60 * 26, "1h": 500 * 7, "60m": 500 * 7, "1d": 2520, "1wk": 1000}


def _num(x: Any) -> float | None:
    try:
        f = float(x)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def parse_chart(symbol: str, payload: dict[str, Any], source: str = "LIVE") -> dict[str, Any]:
    """Normalise a Yahoo v8 chart response into {quote, history}."""
    try:
        res = payload["chart"]["result"][0]
    except (KeyError, IndexError, TypeError):
        err = (payload.get("chart") or {}).get("error") if isinstance(payload, dict) else None
        raise SourceError(f"No chart data for {symbol}: {err or 'empty response'}")
    meta = res.get("meta") or {}
    ts = res.get("timestamp") or []
    closes = ((res.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    history = [{"date": dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(), "close": _num(c)}
               for t, c in zip(ts, closes) if _num(c) is not None]
    price = _num(meta.get("regularMarketPrice"))
    if price is None and history:
        price = history[-1]["close"]
    if price is None:
        raise SourceError(f"No price for {symbol}")
    prev = _num(meta.get("previousClose")) or _num(meta.get("chartPreviousClose"))
    if len(history) >= 2 and (prev is None or meta.get("range") not in (None, "1d", "5d")):
        # chartPreviousClose is the close before the *range*, not yesterday: use the series instead.
        last_date = dt.datetime.fromtimestamp(meta.get("regularMarketTime") or ts[-1], dt.timezone.utc).date().isoformat()
        prior = [h for h in history if h["date"] < last_date]
        if prior:
            prev = prior[-1]["close"]
    market_time = meta.get("regularMarketTime")
    period = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    is_open = bool(period.get("start") and period.get("end") and period["start"] <= now <= period["end"])
    quote = {
        "symbol": meta.get("symbol") or symbol,
        "name": meta.get("longName") or meta.get("shortName") or symbol,
        "price": price,
        "prev_close": prev,
        "change": (price - prev) if prev else None,
        "change_pct": (price / prev - 1) if prev else None,
        "currency": meta.get("currency"),
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
        "instrument_type": meta.get("instrumentType"),
        "market_time": dt.datetime.fromtimestamp(market_time, dt.timezone.utc).isoformat() if market_time else None,
        "market_open": is_open,
        "timezone": meta.get("exchangeTimezoneName"),
        "delayed_minutes": _num(meta.get("exchangeDataDelayedBy")),
        "day_high": _num(meta.get("regularMarketDayHigh")),
        "day_low": _num(meta.get("regularMarketDayLow")),
        "volume": _num(meta.get("regularMarketVolume")),
        "fifty_two_week_high": _num(meta.get("fiftyTwoWeekHigh")),
        "fifty_two_week_low": _num(meta.get("fiftyTwoWeekLow")),
        "source": source,
    }
    return {"quote": quote, "history": history}


class YahooSource:
    name = "Yahoo Finance"

    def __init__(self, timeout: float = 10.0, client: httpx.Client | None = None):
        self._client = client or httpx.Client(headers={"User-Agent": UA, "Accept": "application/json"},
                                              timeout=timeout, follow_redirects=True)
        # Tests inject an httpx client; production uses the browser-fingerprint session when available.
        self._browser = None if client is not None else _browser_session()

    def _get(self, url: str, params: dict[str, Any]) -> tuple[int, Any]:
        if self._browser is not None:
            try:
                r = self._browser.get(url, params=params)
                return r.status_code, r
            except Exception as e:  # noqa: BLE001  (curl errors -> treat like a network error)
                raise SourceError(type(e).__name__) from e
        try:
            r = self._client.get(url, params=params)
        except httpx.HTTPError as e:
            raise SourceError(type(e).__name__) from e
        return r.status_code, r

    def chart(self, symbol: str, range_: str = "1y", interval: str = "1d") -> dict[str, Any]:
        params = {"range": range_, "interval": interval, "includePrePost": "false"}
        last = 0
        for host in CHART_HOSTS:  # query2 is a separate pool; try it once if query1 refuses
            try:
                status, r = self._get(f"{host}/v8/finance/chart/{symbol}", params)
            except SourceError as e:
                raise SourceError(f"{symbol}: {e}") from e
            last = status
            if status == 404:
                raise SourceError(f"Unknown symbol {symbol}")
            if status == 429:
                continue
            if status >= 400:
                raise SourceError(f"{symbol}: HTTP {status}")
            return parse_chart(symbol, r.json())
        raise RateLimited(f"{symbol}: HTTP {last}")

    def bars(self, symbol: str, range_: str, interval: str) -> list[dict[str, Any]]:
        params = {"range": range_, "interval": interval, "includePrePost": "false"}
        last = 0
        for host in CHART_HOSTS:
            status, r = self._get(f"{host}/v8/finance/chart/{symbol}", params)
            last = status
            if status == 404:
                raise SourceError(f"Unknown symbol {symbol}")
            if status == 429:
                continue
            if status >= 400:
                raise SourceError(f"{symbol}: HTTP {status}")
            return parse_bars(symbol, r.json())
        raise RateLimited(f"{symbol}: HTTP {last}")

    def info(self, symbol: str) -> dict[str, Any]:
        try:
            import yfinance as yf

            info = yf.Ticker(symbol).info or {}
        except Exception as e:  # noqa: BLE001
            raise SourceError(f"{symbol} fundamentals: {e}") from e
        if not info or (len(info) <= 2 and "trailingPegRatio" in info):
            raise SourceError(f"No fundamentals for {symbol}")
        return normalise_info(info)

    def search(self, q: str) -> list[dict[str, Any]]:
        try:
            status, r = self._get(SEARCH_URL, {"q": q, "quotesCount": 10, "newsCount": 0})
            if status == 429:
                raise RateLimited("search: HTTP 429")
            if status >= 400:
                raise SourceError(f"search: HTTP {status}")
            quotes = r.json().get("quotes") or []
        except ValueError as e:
            raise SourceError(f"search: {e}") from e
        return [{"symbol": x.get("symbol"), "name": x.get("longname") or x.get("shortname") or x.get("symbol"),
                 "exchange": x.get("exchDisp") or x.get("exchange"), "type": x.get("quoteType")}
                for x in quotes if x.get("symbol")]


def _frac_yield(info: dict[str, Any]) -> float | None:
    """Dividend yield as a fraction (0.025 = 2.5%). yfinance's dividendYield is in percent; the trailing and
    fund `yield` fields are fractions, so prefer those."""
    for k in ("trailingAnnualDividendYield", "yield"):
        v = _num(info.get(k))
        if v is not None and 0 < v < 1:  # Yahoo reports 0 for some funds that do pay; fall through to the next field
            return v
    v = _num(info.get("dividendYield"))
    return v / 100 if v is not None else None


def _frac_expense(info: dict[str, Any]) -> float | None:
    """Expense ratio as a fraction (0.0003 = 0.03%). annualReportExpenseRatio is a fraction; netExpenseRatio is percent."""
    v = _num(info.get("annualReportExpenseRatio"))
    if v is not None and 0 <= v < 0.1:
        return v
    v = _num(info.get("netExpenseRatio"))
    return v / 100 if v is not None else None


def normalise_info(info: dict[str, Any]) -> dict[str, Any]:
    """The subset of yfinance's .info the platform uses, with stable key names."""
    g = info.get
    return {
        "name": g("longName") or g("shortName"),
        "sector": g("sector"), "industry": g("industry"), "country": g("country"),
        "summary": g("longBusinessSummary"), "website": g("website"),
        "quote_type": g("quoteType"), "currency": g("currency"),
        "market_cap": _num(g("marketCap")), "enterprise_value": _num(g("enterpriseValue")),
        "trailing_pe": _num(g("trailingPE")), "forward_pe": _num(g("forwardPE")),
        "ev_ebitda": _num(g("enterpriseToEbitda")), "ev_revenue": _num(g("enterpriseToRevenue")),
        "price_to_book": _num(g("priceToBook")),
        "roe": _num(g("returnOnEquity")), "roa": _num(g("returnOnAssets")),
        "operating_margin": _num(g("operatingMargins")), "gross_margin": _num(g("grossMargins")),
        "profit_margin": _num(g("profitMargins")),
        "debt_to_equity": _num(g("debtToEquity")), "revenue_growth": _num(g("revenueGrowth")),
        "earnings_growth": _num(g("earningsGrowth")), "beta": _num(g("beta")),
        "dividend_yield": _frac_yield(info),
        "target_mean_price": _num(g("targetMeanPrice")), "recommendation": g("recommendationKey"),
        "target_high_price": _num(g("targetHighPrice")), "target_low_price": _num(g("targetLowPrice")),
        "target_median_price": _num(g("targetMedianPrice")), "recommendation_mean": _num(g("recommendationMean")),
        "analyst_count": _num(g("numberOfAnalystOpinions")),
        "average_volume": _num(g("averageVolume")) or _num(g("averageDailyVolume3Month")),
        "average_volume_10d": _num(g("averageVolume10days")) or _num(g("averageDailyVolume10Day")),
        "short_ratio": _num(g("shortRatio")), "short_percent_float": _num(g("shortPercentOfFloat")),
        "held_by_insiders": _num(g("heldPercentInsiders")), "held_by_institutions": _num(g("heldPercentInstitutions")),
        "free_cash_flow": _num(g("freeCashflow")), "revenue": _num(g("totalRevenue")),
        "current_ratio": _num(g("currentRatio")), "peg_ratio": _num(g("trailingPegRatio")) or _num(g("pegRatio")),
        "price_to_sales": _num(g("priceToSalesTrailing12Months")),
        # funds
        "nav_price": _num(g("navPrice")), "total_assets": _num(g("totalAssets")),
        "expense_ratio": _frac_expense(info),
        "fund_family": g("fundFamily"), "category": g("category"),
        "ytd_return": _num(g("ytdReturn")),
    }


# ── demo source ───────────────────────────────────────────────────────────────────────────────────
def _seed(symbol: str) -> int:
    return int(hashlib.sha256(symbol.upper().encode()).hexdigest()[:12], 16)


DEMO_LEVELS = {"^GSPC": 5900.0, "^IXIC": 19000.0, "^DJI": 43000.0, "^STOXX50E": 4800.0, "^N225": 38500.0,
               "^TNX": 4.2, "EURUSD=X": 1.06, "JPY=X": 154.0, "GBPUSD=X": 1.27, "BTC-USD": 92000.0,
               "JPYUSD=X": 0.0065, "TWDUSD=X": 0.031, "HKDUSD=X": 0.128, "CHFUSD=X": 1.13,
               "INRUSD=X": 0.0118, "BRLUSD=X": 0.17, "DKKUSD=X": 0.142}
SUFFIX_CCY = {".T": "JPY", ".TW": "TWD", ".HK": "HKD", ".L": "GBp", ".SW": "CHF", ".NS": "INR", ".SA": "BRL",
              ".CO": "DKK", ".AS": "EUR", ".PA": "EUR", ".DE": "EUR"}


def _demo_ccy(symbol: str) -> str:
    for suf, ccy in SUFFIX_CCY.items():
        if symbol.endswith(suf):
            return ccy
    return "USD"


class DemoSource:
    """Deterministic fictional data: same symbol, same day → same numbers. Labelled DEMO everywhere."""

    name = "Demo data"

    def __init__(self):
        # local symbol -> (adr symbol, ratio): lets demo local lines track their ADR so demo
        # premiums look like real ones (a few tenths of a percent plus noise) instead of random.
        self.links: dict[str, tuple[str, float]] = {}

    def link_pair(self, adr: str, local: str, ratio: float) -> None:
        self.links[local.upper()] = (adr.upper(), float(ratio))

    def _base(self, symbol: str) -> float:
        if symbol in DEMO_LEVELS:
            return DEMO_LEVELS[symbol]
        rnd = random.Random(_seed(symbol))
        return round(rnd.uniform(15, 400), 2)

    def bars(self, symbol: str, range_: str, interval: str) -> list[dict[str, Any]]:
        """Synthetic OHLCV at any interval: a random walk with volatility clustering. Labelled DEMO."""
        symbol = symbol.upper()
        rnd = random.Random(_seed(symbol + interval))
        step = BAR_STEPS.get(interval, 1440)
        n = BAR_COUNTS.get(interval, 2520)
        per_day = 1440 / step if step < 1440 else 1
        base_vol = (0.003 if symbol.endswith("=X") else 0.012) * math.sqrt(step / 1440 if step >= 1440 else 1 / per_day * 1.5)
        px, var, bars = self._base(symbol), base_vol ** 2, []
        t = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0) - dt.timedelta(minutes=step * n)
        for _ in range(n):
            var = 0.94 * var + 0.06 * (base_vol ** 2) * rnd.uniform(0.2, 2.5)
            sd = math.sqrt(var)
            o = px * math.exp(rnd.gauss(0, sd * 0.2))
            c = o * math.exp(rnd.gauss(0.00005, sd))
            hi = max(o, c) * math.exp(abs(rnd.gauss(0, sd * 0.5)))
            lo = min(o, c) * math.exp(-abs(rnd.gauss(0, sd * 0.5)))
            bars.append({"t": t.isoformat(), "o": o, "h": hi, "l": lo, "c": c, "v": rnd.lognormvariate(13, 0.4) * (1 + abs(c / o - 1) / sd)})
            px = c
            t += dt.timedelta(minutes=step)
        return bars

    def chart(self, symbol: str, range_: str = "1y", interval: str = "1d") -> dict[str, Any]:
        symbol = symbol.upper()
        rnd = random.Random(_seed(symbol))
        days = {"1mo": 22, "3mo": 64, "6mo": 128, "1y": 252, "2y": 504, "5y": 1260}.get(range_, 252)
        base = self._base(symbol)
        vol = rnd.uniform(0.002, 0.006) if symbol.endswith("=X") or symbol.startswith("^TNX") else rnd.uniform(0.008, 0.025)
        today = dt.date.today()
        # Walk backwards from today so the last close is anchored near `base`.
        px, closes = base, []
        for _ in range(days):
            closes.append(px)
            px = px / math.exp(rnd.gauss(0.0003, vol))
        closes.reverse()
        dates, d = [], today
        while len(dates) < days:
            if d.weekday() < 5:
                dates.append(d)
            d -= dt.timedelta(days=1)
        dates.reverse()
        ccy = _demo_ccy(symbol)
        if symbol in self.links:
            adr, ratio = self.links[symbol]
            a_hist = self.chart(adr, range_)["history"]
            fx_sym = f"{'GBP' if ccy == 'GBp' else ccy}USD=X"
            fx_hist = {h["date"]: h["close"] for h in self.chart(fx_sym, range_)["history"]} if ccy != "USD" else {}
            minor = 100.0 if ccy == "GBp" else 1.0
            basis = rnd.uniform(-0.006, 0.006)
            dates = [dt.date.fromisoformat(h["date"]) for h in a_hist]
            closes, dev = [], 0.0
            for h in a_hist:
                dev = 0.8 * dev + rnd.gauss(0, 0.004)  # mean-reverting deviation from the basis
                fx = fx_hist.get(h["date"], 1.0)
                closes.append(h["close"] / ((1 + basis + dev) * ratio * fx) * minor)
        history = [{"date": x.isoformat(), "close": round(c, 4)} for x, c in zip(dates, closes)]
        price, prev = history[-1]["close"], history[-2]["close"]
        quote = {"symbol": symbol, "name": f"{symbol} (demo)", "price": price, "prev_close": prev,
                 "change": price - prev, "change_pct": price / prev - 1, "currency": ccy, "exchange": "DEMO",
                 "instrument_type": "EQUITY", "market_time": dt.datetime.now(dt.timezone.utc).isoformat(),
                 "market_open": True, "timezone": "UTC", "delayed_minutes": 0,
                 "day_high": price * 1.01, "day_low": price * 0.99, "volume": rnd.randint(1, 50) * 1e6,
                 "fifty_two_week_high": max(closes), "fifty_two_week_low": min(closes), "source": "DEMO"}
        return {"quote": quote, "history": history}

    def info(self, symbol: str) -> dict[str, Any]:
        rnd = random.Random(_seed(symbol) ^ 0xBEEF)
        return {"name": f"{symbol} (demo)", "sector": "Demo", "industry": "Demo", "country": "Demo",
                "summary": "Fictional demo company. Switch IRAI_MARKET_MODE=live for real data.",
                "quote_type": "EQUITY", "currency": "USD", "market_cap": rnd.uniform(5e9, 5e11),
                "enterprise_value": rnd.uniform(5e9, 5e11), "trailing_pe": rnd.uniform(8, 40),
                "forward_pe": rnd.uniform(8, 35), "ev_ebitda": rnd.uniform(5, 30), "ev_revenue": rnd.uniform(1, 12),
                "price_to_book": rnd.uniform(1, 10), "roe": rnd.uniform(0.02, 0.4), "roa": rnd.uniform(0.01, 0.2),
                "operating_margin": rnd.uniform(0.05, 0.45), "gross_margin": rnd.uniform(0.3, 0.8),
                "profit_margin": rnd.uniform(0.03, 0.35), "debt_to_equity": rnd.uniform(0, 200),
                "revenue_growth": rnd.uniform(-0.05, 0.3), "earnings_growth": rnd.uniform(-0.1, 0.4),
                "beta": rnd.uniform(0.6, 1.8), "dividend_yield": rnd.uniform(0, 0.04),
                "target_mean_price": None, "recommendation": None, "analyst_count": None,
                "average_volume": rnd.randint(1, 50) * 1e6,
                "nav_price": self.chart(symbol)["quote"]["price"] * (1 + rnd.uniform(-0.004, 0.004)),
                "total_assets": rnd.uniform(1e9, 5e11), "expense_ratio": rnd.uniform(0.0003, 0.007),
                "fund_family": "Demo Funds", "category": "Demo", "ytd_return": rnd.uniform(-0.1, 0.3)}

    def search(self, q: str) -> list[dict[str, Any]]:
        q = q.upper().strip()
        return [{"symbol": q, "name": f"{q} (demo)", "exchange": "DEMO", "type": "EQUITY"}] if q else []


def parallel(fn, items: list[str], workers: int = 8) -> dict[str, Any]:
    """Run fn over items concurrently; returns {item: result or Exception}."""
    out: dict[str, Any] = {}
    if not items:
        return out
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as ex:
        futs = {it: ex.submit(fn, it) for it in items}
        for it, f in futs.items():
            try:
                out[it] = f.result()
            except Exception as e:  # noqa: BLE001
                out[it] = e
    return out
