"""Open, key-free data sources used when the main feed is unavailable.

* FX: European Central Bank euro reference rates (published each business day ~16:00 CET; free reuse with
  attribution). Crossed through EUR to give USD rates in the same symbols the app uses (GBPUSD=X, JPY=X).
* US 10-year Treasury yield (^TNX): U.S. Treasury daily par yield curve (public domain).
* Crypto (BTC-USD, ETH-USD, ...): Coinbase Exchange public market data (real time, no key).

ECB and Treasury values are end-of-day, so their quotes are labelled EOD, never LIVE.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import threading
import time
from typing import Any

import httpx

from .source import SourceError

ECB_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D..EUR.SP00.A"
TREASURY_URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
                "{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv")
COINBASE = "https://api.exchange.coinbase.com/products/{pair}"
UA = "IrradianceResearch/1.0 (support@irradiance.ai)"
CRYPTO = {"BTC-USD", "ETH-USD", "SOL-USD"}


def parse_ecb_csv(text: str) -> dict[str, list[tuple[str, float]]]:
    """{currency: [(date, units per EUR), ...]} sorted by date."""
    out: dict[str, list[tuple[str, float]]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            out.setdefault(row["CURRENCY"], []).append((row["TIME_PERIOD"], float(row["OBS_VALUE"])))
        except (KeyError, ValueError, TypeError):
            continue
    for v in out.values():
        v.sort()
    return out


def fx_from_ecb(symbol: str, rates: dict[str, list[tuple[str, float]]]) -> list[tuple[str, float]] | None:
    """Daily series for an app FX symbol: 'GBPUSD=X' (USD per GBP), 'EURUSD=X', or 'JPY=X' (JPY per USD)."""
    usd = dict(rates.get("USD") or [])
    if not usd:
        return None

    def per_eur(ccy: str) -> dict[str, float] | None:
        return {d: 1.0 for d in usd} if ccy == "EUR" else (dict(rates[ccy]) if ccy in rates else None)

    s = symbol.upper()
    if s.endswith("USD=X") and len(s) == 8:          # XXXUSD=X -> USD per XXX
        base = per_eur(s[:3])
        if base is None:
            return None
        return [(d, usd[d] / base[d]) for d in sorted(usd) if d in base and base[d]]
    if s.endswith("=X") and len(s) == 5:              # XXX=X -> XXX per USD
        quote = per_eur(s[:3])
        if quote is None:
            return None
        return [(d, quote[d] / usd[d]) for d in sorted(usd) if d in quote and usd[d]]
    return None


def parse_treasury_csv(text: str, column: str = "10 Yr") -> list[tuple[str, float]]:
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            m, d, y = row["Date"].split("/")
            out.append((f"{y}-{m}-{d}", float(row[column])))
        except (KeyError, ValueError):
            continue
    return sorted(out)


def _quote(symbol: str, name: str, series: list[tuple[str, float]], source: str, currency: str | None,
           provider: str, price: float | None = None) -> dict[str, Any]:
    if not series and price is None:
        raise SourceError(f"No open data for {symbol}")
    last = price if price is not None else series[-1][1]
    if price is None or (series and series[-1][0] == dt.datetime.now(dt.timezone.utc).date().isoformat()):
        prev = series[-2][1] if len(series) >= 2 else None  # last point is today's: compare with the one before
    else:
        prev = series[-1][1] if series else None
    when = series[-1][0] if series else dt.date.today().isoformat()
    q = {"symbol": symbol, "name": name, "price": last, "prev_close": prev,
         "change": (last - prev) if prev else None, "change_pct": (last / prev - 1) if prev else None,
         "currency": currency, "exchange": provider, "instrument_type": None,
         "market_time": f"{when}T16:00:00+00:00" if source == "EOD" else dt.datetime.now(dt.timezone.utc).isoformat(),
         "market_open": source == "LIVE", "timezone": "UTC", "delayed_minutes": None, "day_high": None, "day_low": None,
         "volume": None, "fifty_two_week_high": max((v for _, v in series[-252:]), default=None),
         "fifty_two_week_low": min((v for _, v in series[-252:]), default=None), "source": source, "provider": provider}
    return {"quote": q, "history": [{"date": d, "close": v} for d, v in series[-260:]]}


class OpenDataSource:
    name = "Open data (ECB, U.S. Treasury, Coinbase)"

    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(headers={"User-Agent": UA}, timeout=10, follow_redirects=True)
        self._lock = threading.Lock()
        self._ecb: tuple[float, dict] | None = None
        self._tsy: tuple[float, list] | None = None

    @staticmethod
    def supports(symbol: str) -> bool:
        s = symbol.upper()
        return s == "^TNX" or s in CRYPTO or (s.endswith("=X") and len(s) in (5, 8))

    def _get(self, url: str, **params) -> httpx.Response:
        try:
            r = self._client.get(url, params=params or None)
        except httpx.HTTPError as e:
            raise SourceError(f"open data: {type(e).__name__}") from e
        if r.status_code >= 400:
            raise SourceError(f"open data: HTTP {r.status_code}")
        return r

    def _ecb_rates(self) -> dict:
        with self._lock:
            if self._ecb and time.time() - self._ecb[0] < 3600:
                return self._ecb[1]
        r = self._get(ECB_URL, lastNObservations="270", format="csvdata")
        rates = parse_ecb_csv(r.text)
        if not rates.get("USD"):
            raise SourceError("ECB: no USD rates in response")
        with self._lock:
            self._ecb = (time.time(), rates)
        return rates

    def _treasury(self) -> list:
        with self._lock:
            if self._tsy and time.time() - self._tsy[0] < 3600:
                return self._tsy[1]
        year = dt.date.today().year
        series: list = []
        for y in (year - 1, year):
            try:
                series += parse_treasury_csv(self._get(TREASURY_URL.format(year=y)).text)
            except SourceError:
                if y == year:
                    raise
        series.sort()
        with self._lock:
            self._tsy = (time.time(), series)
        return series

    def chart(self, symbol: str, range_: str = "1y", interval: str = "1d") -> dict[str, Any]:
        s = symbol.upper()
        if s in CRYPTO:
            candles = self._get(COINBASE.format(pair=s) + "/candles", granularity="86400").json()
            series = sorted((dt.datetime.fromtimestamp(c[0], dt.timezone.utc).date().isoformat(), float(c[4])) for c in candles)
            tick = self._get(COINBASE.format(pair=s) + "/ticker").json()
            return _quote(s, s.replace("-", "/"), series, "LIVE", "USD", "Coinbase", price=float(tick["price"]))
        if s == "^TNX":
            return _quote(s, "US 10-Year Treasury Yield", self._treasury(), "EOD", None, "U.S. Treasury")
        if s.endswith("=X"):
            series = fx_from_ecb(s, self._ecb_rates())
            if not series:
                raise SourceError(f"ECB does not publish {s}")
            name = f"{s[:3]}/USD" if len(s) == 8 else f"USD/{s[:3]}"
            return _quote(s, name, series, "EOD", "USD" if len(s) == 8 else s[:3], "ECB reference rate")
        raise SourceError(f"No open data for {s}")
