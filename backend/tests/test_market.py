"""Live-data layer: Yahoo parsing, HTTP source, fallbacks, and the three engines."""
import datetime as dt
import math
import random

import httpx
import pytest

from app.market import engines, service
from app.market.source import DemoSource, SourceError, YahooSource, parse_chart


def chart_payload(symbol, closes, currency="USD", price=None, open_=True, start=None, mtime_last_bar=False):
    start = start or dt.date(2026, 1, 1)
    ts, d = [], start
    while len(ts) < len(closes):
        if d.weekday() < 5:
            ts.append(int(dt.datetime(d.year, d.month, d.day, 20, tzinfo=dt.timezone.utc).timestamp()))
        d += dt.timedelta(days=1)
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    period = {"start": now - 3600, "end": now + 3600} if open_ else {"start": now - 7200, "end": now - 3600}
    return {"chart": {"result": [{"meta": {"symbol": symbol, "currency": currency, "regularMarketPrice": price or closes[-1],
                                           "regularMarketTime": ts[-1] if mtime_last_bar else int(now), "longName": f"{symbol} Inc", "range": "1y",
                                           "chartPreviousClose": closes[0], "fullExchangeName": "TEST",
                                           "currentTradingPeriod": {"regular": period}},
                                  "timestamp": ts, "indicators": {"quote": [{"close": closes}]}}], "error": None}}


def test_parse_chart_uses_series_for_previous_close():
    out = parse_chart("AAPL", chart_payload("AAPL", [100, 101, 102, 104], mtime_last_bar=True))
    q = out["quote"]
    assert q["price"] == 104 and q["prev_close"] == 102
    assert math.isclose(q["change_pct"], 104 / 102 - 1)
    assert q["source"] == "LIVE" and q["market_open"] is True
    assert len(out["history"]) == 4


def test_parse_chart_errors_on_empty():
    with pytest.raises(SourceError):
        parse_chart("ZZZZ", {"chart": {"result": None, "error": {"code": "Not Found"}}})


def test_yahoo_source_over_http_mock():
    def handler(req: httpx.Request):
        sym = req.url.path.rsplit("/", 1)[-1]
        if sym == "NOPE":
            return httpx.Response(404, json={"chart": {"result": None, "error": {"code": "Not Found"}}})
        if req.url.path.endswith("/search"):
            return httpx.Response(200, json={"quotes": [{"symbol": "AAPL", "longname": "Apple Inc.", "exchDisp": "NASDAQ"}]})
        return httpx.Response(200, json=chart_payload(sym, [10, 11, 12]))

    src = YahooSource(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert src.chart("MSFT")["quote"]["price"] == 12
    with pytest.raises(SourceError):
        src.chart("NOPE")
    assert src.search("apple")[0]["symbol"] == "AAPL"


class FakeSource:
    """A 'live' source backed by fixed payloads (stands in for Yahoo in tests)."""
    name = "fake"

    def __init__(self, charts, infos=None, fail=()):
        self.charts, self.infos, self.fail = charts, infos or {}, set(fail)

    def chart(self, symbol, range_="1y", interval="1d"):
        if symbol in self.fail or symbol not in self.charts:
            raise SourceError(f"down: {symbol}")
        return parse_chart(symbol, self.charts[symbol])

    def info(self, symbol):
        if symbol not in self.infos:
            raise SourceError("no info")
        return self.infos[symbol]

    def search(self, q):
        return []


@pytest.fixture
def fake():
    from app.db import init_db
    init_db()
    yield
    service.set_source(None)


def test_fallback_stale_then_demo(fake):
    service.set_source(FakeSource({"AAA": chart_payload("AAA", [5, 6, 7])}))
    assert service.quote("AAA")["source"] == "LIVE"
    # feed goes down → last stored quote, labelled STALE
    service.set_source(FakeSource({}, fail={"AAA"}))
    q = service.quote("AAA")
    assert q["source"] == "STALE" and q["price"] == 7
    # never seen before and feed down → demo, labelled DEMO
    assert service.quote("NEVERSEEN")["source"] == "DEMO"


def test_adr_premium_gbp_pence_and_ratio(fake):
    # AZN-like: 1 ADR = 0.5 local share. Local 12,000p = £120; GBPUSD 1.25 → implied $75. ADR $75.75 → +1%.
    n = 60
    rnd = random.Random(1)
    adr = [75 * (1 + 0.002 * rnd.gauss(0, 1)) for _ in range(n - 1)] + [75.75]
    loc = [12000.0] * n
    fx = [1.25] * n
    service.set_source(FakeSource({"AZN": chart_payload("AZN", adr), "AZN.L": chart_payload("AZN.L", loc, "GBp", open_=False),
                                   "GBPUSD=X": chart_payload("GBPUSD=X", fx)}))
    row = engines.adr_row({"adr_symbol": "AZN", "local_symbol": "AZN.L", "name": "AstraZeneca", "country": "UK",
                           "local_currency": "GBP", "ratio": 0.5, "shortable_local": True, "round_trip_cost_bps": 30})
    assert row["local_currency"] == "GBP" and math.isclose(row["local_price"], 120.0)
    assert math.isclose(row["implied_usd"], 75.0)
    assert math.isclose(row["premium"], 0.01, rel_tol=1e-9)
    assert row["z"] > 2  # a 1% jump vs ~0.2% noise
    assert row["source"] == "PROXY"  # London closed in this fixture
    assert any("Local market closed" in r for r in row["reasons"]) and row["tradable"] is False


def test_half_life_recovers_ar1():
    rnd = random.Random(7)
    x, xs, phi = 0.0, [], 0.7  # true half-life = ln(0.5)/ln(0.7) ≈ 1.94
    for _ in range(3000):
        x = phi * x + rnd.gauss(0, 1)
        xs.append(x)
    assert abs(engines.half_life(xs) - math.log(0.5) / math.log(phi)) < 0.25


def test_rv_ranks_cheap_for_quality_first():
    members = [{"symbol": s, "name": s} for s in "ABCDEF"]
    infos = {  # same quality except E; D is cheapest for its quality
        "A": {"ev_ebitda": 12, "roe": 0.2, "operating_margin": 0.2, "debt_to_equity": 50},
        "B": {"ev_ebitda": 13, "roe": 0.2, "operating_margin": 0.2, "debt_to_equity": 50},
        "C": {"ev_ebitda": 14, "roe": 0.2, "operating_margin": 0.2, "debt_to_equity": 50},
        "D": {"ev_ebitda": 7, "roe": 0.2, "operating_margin": 0.2, "debt_to_equity": 50},
        "E": {"ev_ebitda": 30, "roe": 0.6, "operating_margin": 0.5, "debt_to_equity": 10},  # expensive but high quality
        "F": {"ev_ebitda": 25, "roe": 0.05, "operating_margin": 0.05, "debt_to_equity": 200},  # expensive AND low quality
    }
    rows = engines.score_peer_group("Test", members, infos)
    assert rows[0]["symbol"] == "D" and rows[0]["grade"].startswith("A")
    assert rows[-1]["symbol"] == "F"
    e = next(r for r in rows if r["symbol"] == "E")
    assert e["quality_percentile"] == 100.0


def test_letter_grades():
    assert engines.letter_grade(99) == "A+" and engines.letter_grade(50) == "C+" and engines.letter_grade(1) == "F"


def test_demo_source_deterministic():
    a, b = DemoSource().chart("XYZ"), DemoSource().chart("XYZ")
    assert a["quote"]["price"] == b["quote"]["price"] and a["quote"]["source"] == "DEMO"
