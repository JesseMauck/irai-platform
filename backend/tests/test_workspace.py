import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _user(c, plan=None):
    h = "ws" + uuid.uuid4().hex[:8]
    tok = c.post("/api/auth/register", json={"email": f"{h}@test.io", "password": "pw-123456789", "handle": h,
                                             "display_name": h}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    if plan:
        c.post("/api/billing/checkout", json={"plan": plan}, headers=hdr)
    c.cookies.clear()
    return hdr


def test_search_and_curated_themes(client):
    s = client.get("/api/workspace/search?q=semi").json()
    assert any(t["slug"] == "ai-semiconductors" for t in s["themes"])
    themes = client.get("/api/workspace/themes").json()
    assert len(themes) >= 10
    t = client.get("/api/workspace/themes/ai-semiconductors").json()
    assert t["constituents"] and t["drivers"] and "breadth" in t
    p = client.get("/api/workspace/themes/ai-semiconductors/pestel").json()
    assert [f["key"] for f in p["factors"]] == ["political", "economic", "social", "technological", "environmental", "legal"]


def test_custom_theme_and_pins(client):
    h = _user(client, "pro")
    t = client.post("/api/workspace/themes", json={"name": "My robotics", "tickers": ["isrg", "ABB", "bad ticker!"],
                                                    "keywords": ["robotics"], "drivers": [{"name": "Labor costs", "why": "..."}],
                                                    "notes_md": "## Why"}, headers=h).json()
    assert t["mine"] and t["tickers"] == ["ISRG", "ABB"] and t["pinned"]
    assert client.get(f"/api/workspace/themes/{t['slug']}").status_code == 404  # private: anonymous can't see
    assert client.get(f"/api/workspace/themes/{t['slug']}", headers=h).json()["notes_md"] == "## Why"
    pins = client.post("/api/workspace/pins", json={"kind": "ticker", "ref": "nvda"}, headers=h).json()
    assert {(p["kind"], p["ref"]) for p in pins} >= {("theme", t["slug"]), ("ticker", "NVDA")}
    other = _user(client)
    assert client.put(f"/api/workspace/themes/{t['slug']}", json={"name": "x" * 5}, headers=other).status_code == 404
    assert client.delete(f"/api/workspace/themes/{t['slug']}", headers=h).json()["ok"]
    assert all(p["kind"] != "theme" for p in client.get("/api/workspace/pins", headers=h).json())


def test_compare(client):
    r = client.post("/api/workspace/compare", json={"symbols": ["AAPL", "MSFT", "GOOGL"]}).json()
    assert r["symbols"] == ["AAPL", "MSFT", "GOOGL"] and r["analysis"]["engine"] == "rules"
    assert "rating" in r["rows"][0] and r["rows"][0]["valuation"]
    assert client.post("/api/workspace/compare", json={"symbols": ["A", "B", "C", "D"]}).status_code == 401
    h = _user(client)
    r = client.post("/api/workspace/compare", json={"symbols": ["AAPL", "MSFT", "NVDA", "AMD"], "question": "Who is cheapest?"},
                    headers=h).json()
    assert len(r["rows"]) == 4 and r["analysis"]["markdown"]


def test_analysis_posts_by_ticker(client):
    h = _user(client, "essential")
    comm = client.get("/api/community/communities").json()[0]["slug"]
    short = client.post("/api/community/threads", json={"community": comm, "title": "Short note", "body": "too short",
                                                         "kind": "analysis", "tickers": ["AAPL"]}, headers=h)
    assert short.status_code == 422
    body = "Thesis. " * 60
    t = client.post("/api/community/threads", json={"community": comm, "title": "Apple services mix shift", "body": body,
                                                     "kind": "analysis", "outlook": "bullish", "tickers": ["aapl", "msft"]}, headers=h).json()
    assert t["kind"] == "analysis" and t["outlook"] == "bullish" and t["ticker"] == "AAPL"
    by = client.get("/api/community/threads?ticker=MSFT&kind=analysis").json()
    assert any(x["id"] == t["id"] for x in by)


def test_theme_analytics_index_and_news(client):
    t = client.get("/api/workspace/themes/ai-semiconductors").json()
    idx = t["index"]
    assert idx["series"] and idx["series"][0]["theme"] == pytest.approx(100, rel=0.05)
    assert "bench" in idx["series"][-1] and idx["bench"]["symbol"] == "SPY"
    assert idx["stats"]["volatility"] and idx["stats"]["volatility"] > 0
    c = t["correlation"]["avg_pairwise_6m"]
    assert c is None or -1 <= c <= 1
    assert t["breadth"]["above_200d_pct"] is not None
    row = t["constituents"][0]
    for k in ("ret_3m", "ret_1y", "volatility", "forward_pe", "buzz"):
        assert k in row
    assert len(t["leaders"]) == 3
    n = client.get("/api/workspace/themes/ai-semiconductors/news").json()
    assert "headlines" in n and "catalysts" in n


def test_corr_helper():
    from app.routers.workspace import _corr, _when
    xs = [float(i % 7) for i in range(60)]
    assert _corr(xs, xs) == pytest.approx(1.0)
    assert _corr(xs, [-x for x in xs]) == pytest.approx(-1.0)
    assert _when("Fri, 20 Nov 2026 15:30:00 GMT").startswith("2026-11-20T15:30")
    assert _when("20261120T153000Z").startswith("2026-11-20T15:30")


def test_preferences_roundtrip_and_custom_tickerbar(client):
    hdr = _user(client)
    p = client.get("/api/me/preferences", headers=hdr).json()
    assert p["theme"] == "system" and p["ticker_bar"] == []
    r = client.put("/api/me/preferences", headers=hdr, json={**p, "accent": "ocean", "ticker_bar": ["aapl", "MSFT", "AAPL", "bad sym!"], "benchmark": "QQQ"})
    assert r.status_code == 200 and r.json()["ticker_bar"] == ["AAPL", "MSFT"]
    assert client.put("/api/me/preferences", headers=hdr, json={**p, "accent": "neon"}).status_code == 422
    bar = client.get("/api/market/tickerbar", headers=hdr).json()
    assert [x["symbol"] for x in bar] == ["AAPL", "MSFT"]
    assert client.get("/api/auth/me", headers=hdr).json()["preferences"]["accent"] == "ocean"
    assert len(client.get("/api/market/tickerbar").json()) > 2  # anonymous users keep the default bar
    t = client.get("/api/workspace/themes/ai-semiconductors?bench=QQQ").json()
    assert t["index"]["bench"]["symbol"] == "QQQ"


def test_algotrader_waitlist(client):
    r = client.post("/api/waitlist/algotrader", json={"email": "Wait@Test.io", "brokers": ["schwab", "ibkr", "nope"]})
    assert r.status_code == 200 and r.json()["brokers"] == ["ibkr", "schwab"]
    assert client.post("/api/waitlist/algotrader", json={"email": "wait@test.io", "brokers": ["webull"]}).json()["brokers"] == ["webull"]
    assert client.post("/api/waitlist/nothing", json={"email": "a@b.io"}).status_code == 404
    assert client.post("/api/waitlist/algotrader", json={}).status_code == 422
    hdr = _user(client)
    client.post("/api/waitlist/algotrader", json={"brokers": ["fidelity"]}, headers=hdr)
    assert client.get("/api/waitlist/algotrader/me", headers=hdr).json()["joined"] is True
