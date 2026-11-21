import uuid

import pytest
from fastapi.testclient import TestClient

from app import signals
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _user(c, plan=None):
    h = "dc" + uuid.uuid4().hex[:8]
    tok = c.post("/api/auth/register", json={"email": f"{h}@test.io", "password": "pw-123456789", "handle": h, "display_name": h}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    if plan:
        c.post("/api/billing/checkout", json={"plan": plan}, headers=hdr)
    c.cookies.clear()
    return hdr


def test_detect_events():
    down = [200 - i * 0.5 for i in range(200)]
    up = [down[-1] + i * 3 for i in range(1, 40)]  # sharp rally pulls the 50-day back above the 200-day
    closes = down + up
    kinds = set()
    for k in range(len(down) + 1, len(closes) + 1):
        kinds |= {s["kind"] for s in signals.detect("X", closes[:k], [str(i) for i in range(k)])}
    assert "golden_cross" in kinds and "rsi_overbought" in kinds
    flat = [100 + (i % 2) * 0.1 for i in range(260)] + [104]
    ev = {s["kind"]: s for s in signals.detect("Y", flat, [str(i) for i in range(len(flat))])}
    assert "unusual_move" in ev and "breakout_high" in ev and 0 <= ev["unusual_move"]["strength"] <= 100


def test_scan_and_access(client):
    from app.db import SessionLocal
    with SessionLocal() as db:
        out = signals.scan(db, universe=["AAPL", "MSFT", "NVDA", "SPY", "KO", "XOM"], day="2026-11-20")
    assert out["universe"] == 6
    free = client.get("/api/signals", headers=_user(client)).json()
    assert free["pro"] is False and len(free["signals"]) <= 3
    pro = client.get("/api/signals", headers=_user(client, "pro")).json()
    assert pro["pro"] and len(pro["signals"]) >= len(free["signals"]) and free["locked"] == max(0, len(pro["signals"]) - 3)
    assert client.get("/api/signals/track-record", headers=_user(client)).status_code == 402
    tr = client.get("/api/signals/track-record?days=120", headers=_user(client, "pro")).json()
    assert "summary" in tr


def test_heatmap_macro_options_shapes(client):
    h = client.get("/api/discover/heatmap").json()
    assert h["count"] > 20 and h["sectors"] and all("tiles" in s for s in h["sectors"])
    m = client.get("/api/discover/macro").json()
    assert {r["region"] for r in m["regions"]} == {"Americas", "Europe", "Asia-Pacific"} and m["groups"]
    o = client.get("/api/discover/options/AAPL").json()
    assert o["symbol"] == "AAPL" and "expiries" in o
    e = client.get("/api/discover/earnings").json()
    assert "upcoming" in e and e["tracked"] > 20


def test_library_and_history(client):
    hdr = _user(client, "pro")
    a = client.post("/api/paper/accounts", headers=hdr, json={"starting_cash": 20000}).json()
    b = client.post("/api/bots", headers=hdr, json={"name": "Hook", "mode": "webhook", "accounts": [{"account_id": a["id"], "capital": 10000}]}).json()
    client.post(b["webhook_path"], json={"ticker": "AAPL", "action": "buy"})
    client.post("/api/assistant", headers=hdr, json={"messages": [{"role": "user", "content": "Explain beta"}]})
    hist = client.get("/api/me/history", headers=hdr).json()
    kinds = {e["kind"] for e in hist}
    assert {"trade", "signal", "chat"} <= kinds
    lib = client.get("/api/me/library", headers=hdr).json()
    assert lib["chats"] and "valuations" in lib
