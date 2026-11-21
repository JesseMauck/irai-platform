import uuid

import pytest
from fastapi.testclient import TestClient

from app import portfolio as pf
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _user(c, plan="pro"):
    h = "pf" + uuid.uuid4().hex[:8]
    tok = c.post("/api/auth/register", json={"email": f"{h}@test.io", "password": "pw-123456789", "handle": h, "display_name": h}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    if plan:
        c.post("/api/billing/checkout", json={"plan": plan}, headers=hdr)
    c.cookies.clear()
    return hdr


def test_parse_broker_csv():
    text = ('"Positions for account Individual ...123 as of 11/20/2026"\n'
            "Symbol,Description,Quantity,Price,Cost Basis\n"
            'AAPL,APPLE INC,"1,000",$200.00,"$150,000.00"\n'
            "MSFT,MICROSOFT,10,$480,$3000\n"
            "MSFT,MICROSOFT,10,$480,$5000\n"
            "Cash & Cash Investments,--,,,\n"
            "Account Total,,,,\n")
    rows, warn = pf.parse_csv(text)
    by = {r["symbol"]: r for r in rows}
    assert by["AAPL"]["quantity"] == 1000 and by["AAPL"]["cost_basis"] == pytest.approx(150)
    assert by["MSFT"]["quantity"] == 20 and by["MSFT"]["cost_basis"] == pytest.approx(400)
    assert "ACCOUNT TOTAL" not in by
    simple, _ = pf.parse_csv("ticker,shares,avg cost\nko,5,60\n")
    assert simple == [{"symbol": "KO", "quantity": 5.0, "cost_basis": 60.0}]
    assert pf.parse_csv("a,b\n1,2\n")[0] == []


def test_portfolio_flow_and_analysis(client):
    free = _user(client, plan=None)
    assert client.get("/api/portfolio", headers=free).status_code == 402
    hdr = _user(client)
    p = client.post("/api/portfolio", headers=hdr, json={"name": "Core", "cash": 5000, "holdings": [
        {"symbol": "aapl", "quantity": 50, "cost_basis": 150}, {"symbol": "MSFT", "quantity": 20}, {"symbol": "KO", "quantity": 100, "cost_basis": 70},
        {"symbol": "SPY", "quantity": 10}]}).json()
    assert [h["symbol"] for h in p["holdings"]] == ["AAPL", "MSFT", "KO", "SPY"]
    a = client.get(f"/api/portfolio/{p['id']}/analysis", headers=hdr).json()
    s = a["summary"]
    assert s["positions"] == 4 and s["total_value"] == pytest.approx(s["invested"] + 5000)
    assert sum(x["weight"] for x in a["positions"]) == pytest.approx(s["invested"] / s["total_value"])
    aapl = next(x for x in a["positions"] if x["symbol"] == "AAPL")
    assert aapl["unrealized"] == pytest.approx(aapl["value"] - 50 * 150)
    assert a["risk"]["volatility"] and a["series"] and "bench" in a["series"][-1]
    assert 1 <= s["effective_holdings"] <= 4 and a["flags"]
    r = client.post(f"/api/portfolio/{p['id']}/review", headers=hdr).json()
    assert r["engine"] == "rules" and "Overview" in r["markdown"]
    assert not any(w in r["markdown"].lower().split() for w in ("buy", "sell", "rebalance"))
    imp = client.post(f"/api/portfolio/{p['id']}/import", headers=hdr, json={"csv": "Symbol,Quantity\nNVDA,3\n", "mode": "merge"}).json()
    assert imp["imported"] == 5 and imp["source"] == "csv"
    other = _user(client)
    assert client.get(f"/api/portfolio/{p['id']}", headers=other).status_code == 404
    assert client.delete(f"/api/portfolio/{p['id']}", headers=hdr).json()["ok"]


def test_flags_wording():
    s = {"positions": 2, "effective_holdings": 1.2, "cash": 0, "total_value": 100}
    positions = [{"symbol": "X", "weight": 0.8, "unrealized_pct": -0.4, "grade": {"overall": "D"}}]
    fl = pf.flags(s, positions, [{"sector": "Technology", "weight": 0.8}], {"avg_correlation": 0.7, "max_drawdown": -0.3})
    kinds = {f["kind"] for f in fl}
    assert {"concentration", "sector", "correlation", "risk", "loss", "quality"} <= kinds
    assert all("sell" not in f["text"].lower() and "buy" not in f["text"].lower() for f in fl)
