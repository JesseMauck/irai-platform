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
