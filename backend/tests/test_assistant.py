import types
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _user(c, plan=None):
    h = "as" + uuid.uuid4().hex[:8]
    tok = c.post("/api/auth/register", json={"email": f"{h}@test.io", "password": "pw-123456789", "handle": h, "display_name": h}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    if plan:
        c.post("/api/billing/checkout", json={"plan": plan}, headers=hdr)
    c.cookies.clear()
    return hdr


def test_assistant_requires_sign_in_and_falls_back_without_llm(client):
    assert client.post("/api/assistant", json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 401
    hdr = _user(client)
    r = client.post("/api/assistant", headers=hdr, json={"messages": [{"role": "user", "content": "What is MSFT's P/E?"}], "symbol": "MSFT"}).json()
    assert r["engine"] == "rules" and "MSFT" in r["reply"] and r["used"] == 1 and r["limit"] == 10


def test_assistant_quota_and_private_context(client, monkeypatch):
    from app.routers import assistant
    from valuebot.config import settings as vb

    seen = {}

    class Fake:
        def __init__(self, **k):
            self.messages = self

        def create(self, **k):
            seen["prompt"] = k["messages"][-1]["content"]
            assert "Do not tell the member to buy" in k["system"]
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="Answer.")])

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", Fake)
    monkeypatch.setattr(type(vb), "llm_enabled", property(lambda self: True))
    owner = _user(client, plan="pro")
    p = client.post("/api/portfolio", headers=owner, json={"name": "Mine", "holdings": [{"symbol": "AAPL", "quantity": 10}]}).json()
    other = _user(client, plan="pro")
    r = client.post("/api/assistant", headers=other, json={"messages": [{"role": "user", "content": "Review it"}], "portfolio_id": p["id"]}).json()
    assert r["engine"] == "claude" and "portfolio" not in r["context"]  # someone else's portfolio is never read
    r = client.post("/api/assistant", headers=owner, json={"messages": [{"role": "user", "content": "Review it"}], "portfolio_id": p["id"], "symbol": "AAPL"}).json()
    assert set(r["context"]) == {"ticker", "portfolio"} and '"symbol": "AAPL"' in seen["prompt"]
    free = _user(client)
    monkeypatch.setattr(assistant, "limits", lambda u: {"assistant_messages_per_day": 2})
    for _ in range(2):
        assert client.post("/api/assistant", headers=free, json={"messages": [{"role": "user", "content": "q"}]}).status_code == 200
    assert client.post("/api/assistant", headers=free, json={"messages": [{"role": "user", "content": "q"}]}).status_code == 402


def test_news_summary_shape(client):
    r = client.get("/api/insight/MSFT/news-summary").json()
    assert r["symbol"] == "MSFT" and "sources" in r


def test_chats_saved_and_private(client):
    hdr = _user(client)
    r = client.post("/api/assistant", headers=hdr, json={"messages": [{"role": "user", "content": "What is EV/EBITDA?"}]}).json()
    cid = r["chat_id"]
    r2 = client.post("/api/assistant", headers=hdr, json={"chat_id": cid, "messages": [{"role": "user", "content": "What is EV/EBITDA?"}, {"role": "assistant", "content": r["reply"]}, {"role": "user", "content": "And P/E?"}]}).json()
    assert r2["chat_id"] == cid
    lst = client.get("/api/assistant/chats", headers=hdr).json()
    assert lst[0]["id"] == cid and lst[0]["title"].startswith("What is EV/EBITDA") and lst[0]["messages"] == 4
    other = _user(client)
    assert client.get(f"/api/assistant/chats/{cid}", headers=other).status_code == 404
    r3 = client.post("/api/assistant", headers=other, json={"chat_id": cid, "messages": [{"role": "user", "content": "hijack"}]}).json()
    assert r3["chat_id"] != cid  # can't append to someone else's chat
    assert client.delete(f"/api/assistant/chats/{cid}", headers=hdr).json()["ok"]
