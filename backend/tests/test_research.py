import pytest
from fastapi.testclient import TestClient

from app import research
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_quant_ratings_and_consensus(client):
    r = client.get("/api/insight/AAPL/ratings").json()
    assert set(r["factors"]) == {"valuation", "quality", "growth", "momentum", "risk"}
    assert r["overall_grade"] in research.GRADES and r["overall_label"]
    assert all(f["grade"] in research.GRADES for f in r["factors"].values() if f["score"] is not None)
    c = client.get("/api/insight/AAPL/consensus").json()
    assert c["symbol"] == "AAPL" and "target_mean" in c
    assert client.get("/api/insight/../etc/ratings").status_code in (404, 422)


def test_grade_scale():
    assert research._grade(0) == "F" and research._grade(1) == "A+" and research._grade(None) is None
    assert research._scale(10, 0, 20) == 0.5 and research._scale(30, 0, 20) == 1.0 and research._scale(5, 0, 10, invert=True) == 0.5


def test_buzz_scoring():
    quiet = research.score_buzz(10, [10] * 29, 0.2, 0.9, 0.3, 0)
    loud = research.score_buzz(400, [20, 25, 18, 22, 30] * 6, -4.0, 3.5, 4.0, 2)
    assert quiet["level"] in ("Quiet", "Normal") and loud["level"] in ("High", "Extreme")
    assert loud["score"] > quiet["score"] and loud["tone_label"] == "Negative"
    only_market = research.score_buzz(None, [], None, 2.0, 1.0, 0)
    assert 0 <= only_market["score"] <= 100


def test_parsers():
    tl = {"timeline": [{"series": "Article Count", "data": [{"date": "x", "value": 3}, {"date": "y", "value": 9}]}]}
    assert research.parse_gdelt_timeline(tl) == [3.0, 9.0] and research.parse_gdelt_timeline({}) == []
    rss = "<rss><channel><item><title>Apple beats</title><link>https://x/1</link><pubDate>Fri</pubDate></item></channel></rss>"
    assert research.parse_rss(rss)[0]["title"] == "Apple beats" and research.parse_rss("<bad") == []
    assert research._news_query("Apple Inc.", "AAPL") == "Apple"
    assert research._news_query("Taiwan Semiconductor Manufacturing Company Limited", "TSM").startswith('"Taiwan')


def test_buzz_endpoint_and_trending(client):
    b = client.get("/api/insight/AAPL/buzz").json()
    assert 0 <= b["score"] <= 100 and b["level"] and "components" in b
    assert client.get("/api/buzz/trending").status_code == 200
    assert client.get("/api/insight/AAPL/filings").json()["filings"] == []  # demo mode: no network


def test_ticker_report_datasets(client):
    t = client.get("/api/insight/AAPL/technicals").json()
    assert t["trend"] in ("Uptrend", "Downtrend", "Mixed") and 0 <= t["rsi14"] <= 100
    assert t["bollinger"]["lower"] < t["bollinger"]["middle"] < t["bollinger"]["upper"]
    p = client.get("/api/insight/AAPL/peers?add=MSFT").json()
    assert p["rows"][0]["symbol"] == "AAPL" and any(r["symbol"] == "MSFT" for r in p["rows"])
    for path in ("statements", "dividends", "earnings", "preferreds"):
        r = client.get(f"/api/insight/AAPL/{path}")
        assert r.status_code == 200 and r.json()["source"] == "DEMO"


def test_rsi_and_ema_math():
    from app.fundamentals import _ema_series, _rsi
    assert _rsi([1.0 + i for i in range(30)]) == 100.0
    assert _rsi([30.0 - i for i in range(30)]) < 1
    flat_up_down = [10, 11] * 20
    assert 45 < _rsi(flat_up_down) < 55
    assert _ema_series([1, 1, 1], 3) == [1, 1, 1]
