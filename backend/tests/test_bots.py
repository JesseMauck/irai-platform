import datetime as dt
import math
import uuid

import pytest
from fastapi.testclient import TestClient

from app import paper
from app.algo import tearsheet
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _user(c, plan="pro"):
    h = "bt" + uuid.uuid4().hex[:8]
    tok = c.post("/api/auth/register", json={"email": f"{h}@test.io", "password": "pw-123456789", "handle": h, "display_name": h}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    if plan:
        c.post("/api/billing/checkout", json={"plan": plan}, headers=hdr)
    c.cookies.clear()
    return hdr


def test_tearsheet_known_series():
    dates = [(dt.date(2025, 1, 1) + dt.timedelta(days=i)).isoformat() for i in range(300)]
    eq = [100 * (1.001 ** i) for i in range(300)]
    eq[150] = eq[149] * 0.9  # one bad day
    s = tearsheet.compute(dates, eq, [10, -5, 20, -2, 7], bench=[100 + i * 0.05 for i in range(300)], exposure=[i % 2 == 0 for i in range(300)])
    assert len(tearsheet.METRICS) >= 45
    assert s["total_return"] == pytest.approx(eq[-1] / eq[0] - 1)
    assert s["worst_day"] == pytest.approx(-0.1, rel=1e-6)
    assert s["max_drawdown"] < -0.09 and s["max_drawdown_days"] >= 1
    assert s["win_rate"] == pytest.approx(0.6) and s["profit_factor"] == pytest.approx(37 / 7)
    assert s["max_consecutive_wins"] == 1 and s["exposure"] == pytest.approx(0.5)
    assert s["beta"] is not None and math.isfinite(s["sharpe"])
    rows = tearsheet.compare(s, s)
    assert all(r["difference"] in (0, None) for r in rows)


def test_paper_bot_lifecycle(client, monkeypatch):
    assert client.get("/api/bots", headers=_user(client, plan=None)).status_code == 402
    hdr = _user(client)
    a1 = client.post("/api/paper/accounts", headers=hdr, json={"name": "Main", "starting_cash": 100000}).json()
    a2 = client.post("/api/paper/accounts", headers=hdr, json={"name": "IRA", "starting_cash": 50000}).json()
    # over-allocation is refused
    bad = client.post("/api/bots", headers=hdr, json={"name": "x", "strategy": "sma_cross", "symbols": ["AAPL"], "accounts": [{"account_id": a1["id"], "capital": 200000}]})
    assert bad.status_code == 422
    b = client.post("/api/bots", headers=hdr, json={
        "name": "Trend", "strategy": "buy_hold", "symbols": ["aapl", "MSFT"], "stop_loss_pct": 0.1, "take_profit_pct": 0.5,
        "accounts": [{"account_id": a1["id"], "capital": 40000}, {"account_id": a2["id"], "capital": 10000}]}).json()
    assert b["capital"] == 50000 and b["accounts"] == 2 and b["symbols"] == ["AAPL", "MSFT"]
    assert b["backtest"]["stats"]["cagr"] is not None and len(b["comparison"]) > 5
    acct = client.get(f"/api/paper/accounts/{a1['id']}", headers=hdr).json()
    assert acct["cash"] == pytest.approx(60000) and acct["equity"] == pytest.approx(100000, rel=1e-6)
    r = client.post(f"/api/bots/{b['id']}/run", headers=hdr).json()
    d = r["bot"]
    assert len(d["positions"]) == 4  # 2 symbols x 2 accounts, half of each sleeve per symbol
    main_aapl = next(p for p in d["positions"] if p["account_id"] == a1["id"] and p["symbol"] == "AAPL")
    assert main_aapl["value"] == pytest.approx(20000, rel=0.01)
    # stop-loss fires when price falls 15% below cost
    real = paper.price
    monkeypatch.setattr(paper, "price", lambda s: (real(s)[0] * 0.85, "LIVE"))
    with paper_session() as db:
        from app.models import Bot
        bot = db.get(Bot, b["id"])
        assert paper.risk_checks(db, bot) == 4
        db.commit()
    monkeypatch.setattr(paper, "price", real)
    d = client.get(f"/api/bots/{b['id']}", headers=hdr).json()
    assert not d["positions"] and {t["reason"] for t in d["trades"]} >= {"stop_loss", "signal"}
    assert d["live"]["stats"]["trades"] == 4
    # another user can't see it
    assert client.get(f"/api/bots/{b['id']}", headers=_user(client)).status_code == 404
    # deleting returns the sleeves' cash
    out = client.delete(f"/api/bots/{b['id']}", headers=hdr).json()
    assert out["returned_to_accounts"] > 40000
    acct = client.get(f"/api/paper/accounts/{a1['id']}", headers=hdr).json()
    assert acct["cash"] == pytest.approx(acct["equity"]) and acct["equity"] < 100000


def paper_session():
    from app.db import SessionLocal
    return SessionLocal()


def test_webhook_feeds_every_account_and_auto_close(client):
    hdr = _user(client)
    a1 = client.post("/api/paper/accounts", headers=hdr, json={"starting_cash": 20000}).json()
    a2 = client.post("/api/paper/accounts", headers=hdr, json={"starting_cash": 20000}).json()
    b = client.post("/api/bots", headers=hdr, json={"name": "Signals", "mode": "webhook", "symbols": ["NVDA"], "max_position_pct": 0.5,
                                                   "daily_auto_close": True,
                                                   "accounts": [{"account_id": a1["id"], "capital": 10000}, {"account_id": a2["id"], "capital": 10000}]}).json()
    url = b["webhook_path"]
    assert client.post(url, json={"ticker": "NVDA", "action": "buy"}).json()["fills"] == 2
    d = client.get(f"/api/bots/{b['id']}", headers=hdr).json()
    assert len(d["positions"]) == 2 and all(p["value"] == pytest.approx(5000, rel=0.01) for p in d["positions"])
    assert client.post(url, json={"ticker": "AAPL", "action": "buy"}).json()["status"] == "ignored"  # not in its symbols
    assert client.post(url, json={"ticker": "NVDA"}).status_code == 422
    assert client.post("/api/bots/hook/not-a-real-token-xxxxxxxx", json={"ticker": "NVDA", "action": "buy"}).status_code == 404
    # daily auto-close at 15:55 ET on a weekday
    with paper_session() as db:
        t = dt.datetime(2026, 11, 20, 15, 56, tzinfo=paper.ET)
        out = paper.run_schedule(db, t)
        assert out["auto_closed"] == 2
    d = client.get(f"/api/bots/{b['id']}", headers=hdr).json()
    assert not d["positions"] and any(t["reason"] == "auto_close" for t in d["trades"])
    assert client.post(url, json={"ticker": "NVDA", "action": "exit"}).json()["status"] == "ignored"


def test_market_hours_and_rules_draft(client):
    assert paper.market_open(dt.datetime(2026, 11, 20, 10, 0, tzinfo=paper.ET))
    assert not paper.market_open(dt.datetime(2026, 11, 21, 10, 0, tzinfo=paper.ET))  # Saturday
    assert not paper.market_open(dt.datetime(2026, 11, 20, 16, 0, tzinfo=paper.ET))
    hdr = _user(client)
    d = client.post("/api/bots/draft", headers=hdr, json={"prompt": "Buy AAPL and MSFT when RSI is oversold, 8% stop loss, take profit 20%"}).json()
    assert d["strategy"] == "rsi_reversion" and d["symbols"] == ["AAPL", "MSFT"]
    assert d["stop_loss_pct"] == pytest.approx(0.08) and d["take_profit_pct"] == pytest.approx(0.2)
    d2 = client.post("/api/bots/draft", headers=hdr, json={"prompt": "golden cross 50 and 200 day on SPY"}).json()
    assert d2["strategy"] == "sma_cross" and d2["params"] == {"short": 50, "long": 200} and d2["symbols"] == ["SPY"]


def test_rules_draft_ignores_percentages_for_params():
    from app.routers.bots import _rules_draft
    d = _rules_draft("RSI 10 day oversold on QQQ with 8% stop loss")
    assert d["params"]["length"] == 10 and d["stop_loss_pct"] == pytest.approx(0.08)
