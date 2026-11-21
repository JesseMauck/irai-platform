import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _user(c):
    h = "an" + uuid.uuid4().hex[:8]
    tok = c.post("/api/auth/register", json={"email": f"{h}@test.io", "password": "pw-123456789", "handle": h, "display_name": h}).json()["token"]
    c.cookies.clear()
    return {"Authorization": f"Bearer {tok}"}


def test_analyst_run_progress_and_report(client):
    assert client.post("/api/analyst/MSFT").status_code == 401
    hdr = _user(client)
    r = client.post("/api/analyst/MSFT", headers=hdr).json()
    assert r["stages"] and r["stages"][0]["key"] == "market"
    for _ in range(120):
        r = client.get(f"/api/analyst/reports/{r['id']}").json()
        if r["status"] in ("done", "error"):
            break
        time.sleep(0.25)
    assert r["status"] == "done", r
    assert r["progress"] == 1
    res = r["result"]
    a = res["analysis"]
    for k in ("headline", "summary", "whats_new", "bull_case", "bear_case", "valuation", "data_gaps"):
        assert k in a
    ids = {s["id"] for s in res["sources"]}
    assert ids and all(set(i["sources"]) <= ids for i in a["bull_case"] + a["bear_case"])
    text = (a["headline"] + a["summary"]).lower()
    assert not any(w in text.split() for w in ("buy", "sell"))
    # second request within the reuse window is served from the same report
    again = client.post("/api/analyst/MSFT", headers=hdr).json()
    assert again["id"] == r["id"] and again.get("reused")
    assert client.get("/api/analyst/MSFT/latest").json()["id"] == r["id"]
    assert client.get("/api/analyst", headers=hdr).json()[0]["symbol"] == "MSFT"


def test_free_plan_daily_cap(client):
    hdr = _user(client)
    assert client.post("/api/analyst/AAPL?fresh=true", headers=hdr).status_code == 200
    time.sleep(0.5)
    r = client.post("/api/analyst/KO?fresh=true", headers=hdr)
    assert r.status_code == 402


def test_llm_writer_drops_unknown_citations(monkeypatch):
    import types

    import anthropic

    from app import analyst
    from valuebot.config import settings as vb

    note = {"headline": "h", "summary": "s", "whats_new": [{"point": "p", "sources": ["S1", "S99"]}], "bull_case": [], "bear_case": [],
            "valuation": "v", "technical": "t", "sentiment": "x", "catalysts": [], "risks": [], "questions": [], "data_gaps": []}

    class Fake:
        def __init__(self, **k):
            self.messages = self

        def create(self, **k):
            assert k["tool_choice"]["name"] == "submit_note" and "buy" in k["system"]
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="tool_use", input=note)])

    monkeypatch.setattr(anthropic, "Anthropic", Fake)
    monkeypatch.setattr(type(vb), "llm_enabled", property(lambda self: True))
    out, engine = analyst.write({"symbol": "X"}, [{"id": "S1", "label": "a"}])
    assert engine.startswith("Claude") and out["whats_new"][0]["sources"] == ["S1"]
