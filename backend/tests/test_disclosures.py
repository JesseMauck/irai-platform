import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.disclosures import congress, thirteenf
from app.main import app
from app.models import CongressTrade, Filing13F

HOUSE = """P T R
Clerk of the House of Representatives • Legislative Resource Center • B81 Cannon Building • Washington, DC 20515
Name: Hon. April McClain Delaney
Status: Member
State/District: MD06
ID Owner Asset Transaction
Type
Date Notification
Date
Amount Cap.
Gains >
$200?
DC Brown & Brown, Inc. Common Stock
(BRO) [ST]
S 08/25/2026 09/01/2026 $100,001 -
$250,000
F      S     : New
DC BWX Technologies, Inc. Common
Stock (BWXT) [ST]
P 08/03/2026 09/01/2026 $1,001 - $15,000
F      S     : New
S          O : UBS IRA Account
International Business Machines
Corporation Common Stock (IBM)
[ST]
S (partial) 08/24/2026 09/01/2026 $1,001 - $15,000
F      S     : New
DC C.H. Robinson Worldwide, Inc. - P 08/05/2026 09/01/2026 $1,001 - $15,000
Filing ID #20035408
ID Owner Asset Transaction
Type
Date Notification
Date
Amount Cap.
Gains >
$200?
Common Stock (CHRW) [ST]
F      S     : New
RSP ETF [OT] P 08/13/2026 08/13/2026 $50,001 -
$100,000
F      S     : New
* For the complete list of asset type abbreviations, please visit https://fd.house.gov/reference/asset-type-codes.aspx.
"""

SENATE = """<table><thead><tr><th>#</th></tr></thead><tbody>
<tr><td>1</td><td>11/11/2026</td><td>Spouse</td><td><a href="x">GS</a></td><td>Goldman Sachs Group, Inc. (The) Common Stock</td><td>Stock</td><td>Sale (Partial)</td><td>$250,001 - $500,000</td><td>--</td></tr>
<tr><td>2</td><td>10/30/2026</td><td>Joint</td><td>--</td><td>Alabama Toll Rd Brdg &amp; Tunl Auth Revenue Bond</td><td>Municipal Security</td><td>Purchase</td><td>$1,001 - $15,000</td><td>--</td></tr>
</tbody></table>"""

INFO = """<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip><value>2000</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip><value>1000</value><shrsOrPrnAmt><sshPrnamt>5</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
<infoTable><nameOfIssuer>COCA COLA CO</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>191216100</cusip><value>500</value><shrsOrPrnAmt><sshPrnamt>8</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>CALL</titleOfClass><cusip>037833100</cusip><value>300</value><shrsOrPrnAmt><sshPrnamt>1</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><putCall>Call</putCall></infoTable>
</informationTable>"""


def test_house_parser_handles_owners_page_breaks_and_partials():
    rows = congress.parse_house_text(HOUSE)
    assert [r["ticker"] for r in rows] == ["BRO", "BWXT", "IBM", "CHRW", None]
    assert [r["tx_type"] for r in rows] == ["sell", "buy", "sell_partial", "buy", "buy"]
    assert rows[0]["owner"] == "dependent" and rows[2]["owner"] == "self"
    assert rows[0]["amount_low"] == 100001 and rows[0]["amount_high"] == 250000
    assert rows[0]["traded"] == dt.date(2026, 8, 25)
    assert "Robinson" in rows[3]["asset"] and "Filing ID" not in rows[3]["asset"]


def test_house_parser_strips_nul_bytes():
    rows = congress.parse_house_text(HOUSE.replace("Brown & Brown", "Brown\x00 & Brown"))
    assert rows[0]["ticker"] == "BRO" and "\x00" not in rows[0]["asset"]


def test_senate_parser_and_amounts():
    rows = congress.parse_senate_html(SENATE)
    assert rows[0]["ticker"] == "GS" and rows[0]["tx_type"] == "sell_partial" and rows[0]["owner"] == "spouse"
    assert rows[1]["ticker"] is None and "&amp;" not in rows[1]["asset"]
    assert congress.amount_bounds("Over $50,000,000") == (50000000.0, None)


def test_member_matching():
    leg = [{"name": {"first": "April", "last": "McClain Delaney", "official_full": "April McClain Delaney"}, "terms": [{"type": "rep", "state": "MD", "party": "Democrat"}]},
           {"name": {"first": "Rafael", "nickname": "Ted", "last": "Cruz", "official_full": "Ted Cruz"}, "terms": [{"type": "sen", "state": "TX", "party": "Republican"}]}]
    assert congress.match_member(leg, "Delaney", "April McClain", "house", "MD")["party"] == "Democrat"
    assert congress.match_member(leg, "Cruz", "Rafael E", "senate")["member"] == "Ted Cruz"


def test_13f_aggregation_and_changes():
    rows = thirteenf.parse_info_table(INFO)
    aapl = next(r for r in rows if r["cusip"] == "037833100" and not r["put_call"])
    assert aapl["value"] == 3000 and aapl["shares"] == 15
    assert any(r["put_call"] == "call" for r in rows)
    cur = Filing13F(holdings=[{**r, "ticker": "AAPL" if r["cusip"] == "037833100" else "KO", "weight": r["value"] / 3800} for r in rows], positions=3, total_value=3800)
    prev = Filing13F(holdings=[{"cusip": "037833100", "put_call": None, "shares": 10, "value": 1000, "weight": 0.5, "ticker": "AAPL", "name": "APPLE"},
                               {"cusip": "999999999", "put_call": None, "shares": 4, "value": 200, "weight": 0.1, "ticker": "XYZ", "name": "XYZ CO"}], positions=2, total_value=2000)
    ch = {(r["ticker"], r.get("put_call")): r for r in thirteenf.compare(cur, prev)}
    assert ch[("AAPL", None)]["status"] == "added" and ch[("KO", None)]["status"] == "new" and ch[("XYZ", None)]["status"] == "sold_out"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_disclosure_endpoints(client):
    with SessionLocal() as db:
        for i, (m, p, t, ty) in enumerate([("Nancy Test", "Democrat", "AAPL", "buy"), ("Ted Test", "Republican", "MSFT", "sell"), ("Nancy Test", "Democrat", "AAPL", "sell_partial")]):
            db.add(CongressTrade(row_key=uuid.uuid4().hex, chamber="house", member=m, party=p, state="CA", ticker=t, asset=t, tx_type=ty, amount="$1,001 - $15,000",
                                 amount_low=1001, amount_high=15000, traded=dt.date.today() - dt.timedelta(days=40 + i), filed=dt.date.today() - dt.timedelta(days=5), doc_id=f"d{i}", url="https://example.gov/x.pdf"))
        db.add(Filing13F(fund_key="berkshire", cik=1067983, period=dt.date.today() - dt.timedelta(days=60), filed=dt.date.today() - dt.timedelta(days=10), accession=uuid.uuid4().hex[:20],
                         total_value=3000, positions=1, holdings=[{"cusip": "037833100", "ticker": "AAPL", "name": "APPLE INC", "class": "COM", "put_call": None, "value": 3000, "shares": 15, "weight": 1.0}]))
        db.commit()
    t = client.get("/api/congress/trades?symbol=AAPL").json()
    assert t["total"] >= 2 and t["trades"][0]["ticker"] == "AAPL" and t["trades"][0]["disclosure_lag_days"] > 30 and t["locked"]
    s = client.get("/api/congress/summary").json()
    assert s["members"] >= 2 and s["most_traded"][0]["ticker"] == "AAPL"
    f = client.get("/api/smart-money/funds").json()
    assert f["funds"][0]["key"] == "berkshire" and f["funds"][0]["top_holding"]["ticker"] == "AAPL"
    d = client.get("/api/smart-money/funds/berkshire").json()
    assert d["holdings"][0]["ticker"] == "AAPL"
    assert client.get("/api/smart-money/symbol/AAPL").json()["smart_money"]["holders"] == 1
    assert client.get("/api/smart-money/funds/nope").status_code == 404


# ── Ask IRAI navigation ─────────────────────────────────────────────────────────────────────────
SCENARIOS = [
    ("compare ORCL to 3 others stocks", "/compare?symbols=ORCL,", True),
    ("Compare Apple vs Microsoft vs Nvidia", "/compare?symbols=AAPL,MSFT,NVDA", True),
    ("run a DCF on NVDA", "/valuebot?ticker=NVDA", True),
    ("What is Tesla worth?", "/valuebot?ticker=TSLA", False),
    ("take me to the heatmap", "/heatmap", True),
    ("Show me the regime for SPY", "/patterns?tab=regimes&symbol=SPY", True),
    ("build a bot that buys SPY on a golden cross with a 10% stop", "/bots/new?prompt=", True),
    ("backtest an RSI strategy on AMD", "/lab?symbol=AMD&strategy=rsi", True),
    ("monte carlo my AAPL MSFT portfolio", "/lab/montecarlo?symbols=AAPL,MSFT", True),
    ("what are hedge funds buying?", "/smart-money", False),
    ("did Pelosi buy NVDA?", "/congress?symbol=NVDA", False),
    ("when does MSFT report earnings", "/ticker/MSFT#earnings", False),
    ("options expected move for TSLA", "/options?symbol=TSLA", False),
    ("show me AI stocks", "/research/themes/ai-semiconductors", True),
    ("How do I compare stocks?", "/compare", False),
    ("ORCL", "/ticker/ORCL", True),
    ("upgrade to pro", "/pricing", True),
    ("turn on dark mode", "/account/customize", True),
    ("print a report on JPM", "/ticker/JPM/report", True),
    ("what is the price target for AAPL", "/ticker/AAPL", False),
    ("show me oversold stocks", "/signals", True),
    ("analyze Oracle", "/ticker/ORCL#analyst", True),
    ("find stocks with high dividend yield", "/screeners?preset=high_yield_div", False),
    ("show me today's top losers", "/screeners?preset=top_losers", True),
    ("inverse leveraged ETFs", "/screeners?preset=inverse_leveraged", False),
    ("which stocks are at 52 week lows", "/screeners?preset=low_52w", False),
    ("open the screener for low beta stocks", "/screeners?preset=low_beta", True),
]


@pytest.mark.parametrize("q,href,auto", SCENARIOS)
def test_navigation_scenarios(q, href, auto):
    from app.assistant_nav import plan

    p = plan(q)
    assert p["actions"], q
    assert p["actions"][0]["href"].startswith(href), (q, p["actions"])
    assert p["auto"] is auto, (q, p["auto"])
    assert all(a["href"].startswith("/") for a in p["actions"])


def test_navigation_uses_page_ticker_and_compare_peers():
    from app.assistant_nav import plan

    p = plan("compare this to 3 peers", page_symbol="ORCL")
    syms = p["actions"][0]["href"].split("symbols=")[1].split(",")
    assert syms[0] == "ORCL" and len(syms) == 4


def test_assistant_returns_actions(client):
    h = "nv" + uuid.uuid4().hex[:8]
    tok = client.post("/api/auth/register", json={"email": f"{h}@test.io", "password": "pw-123456789", "handle": h, "display_name": h}).json()["token"]
    r = client.post("/api/assistant", headers={"Authorization": f"Bearer {tok}"}, json={"messages": [{"role": "user", "content": "compare ORCL to 3 others stocks"}]}).json()
    assert r["navigate"].startswith("/compare?symbols=ORCL,") and r["actions"][0]["href"] == r["navigate"]
    chat = client.get(f"/api/assistant/chats/{r['chat_id']}", headers={"Authorization": f"Bearer {tok}"}).json()
    assert chat["messages"][-1]["actions"][0]["href"] == r["navigate"]
    bad = client.post("/api/assistant", headers={"Authorization": f"Bearer {tok}"}, json={"messages": [
        {"role": "assistant", "content": "x", "actions": [{"label": "evil", "href": "javascript:alert(1)"}]}, {"role": "user", "content": "hi"}]})
    assert bad.status_code == 422


def test_13f_thousands_detection():
    rows = [{"value": 192493.0, "shares": 1_200_000.0, "put_call": None}, {"value": 42345.0, "shares": 300_000.0, "put_call": None}]
    out = thirteenf.scale_values([dict(r) for r in rows], 234_838_000.0)
    assert out[0]["value"] == 192_493_000.0
    same = thirteenf.scale_values([{"value": 3000.0, "shares": 15.0, "put_call": None}], 3000.0)
    assert same[0]["value"] == 3000.0


# ── screener ────────────────────────────────────────────────────────────────────────────────────
def test_screener_catalog_presets_and_custom(client):
    from app import screener

    c = client.get("/api/screener").json()
    assert c["universe"] > 300 and len(c["spotlight"]) >= 8 and {g["id"] for g in c["groups"]} >= {"market_mover", "sector_rotation", "income", "risk", "liquidity_momentum"}
    r = client.get("/api/screener/presets/inverse_leveraged").json()
    assert r["rows"] and all(x["leverage"] for x in r["rows"]) and r["locked"] and len(r["rows"]) <= 10
    g = client.get("/api/screener/presets/top_gainers").json()["rows"]
    assert g == sorted(g, key=lambda x: -x["change_pct"])
    free = _tok(client)
    assert client.post("/api/screener/run", headers=free, json={"filters": [["rsi14", "<=", 30]], "sort": "rsi14"}).status_code == 402
    pro = _tok(client, "pro")
    j = client.post("/api/screener/run", headers=pro, json={"filters": [["ret_3m", ">=", 0.0], ["kind", "==", "etf"]], "sort": "ret_3m"}).json()
    assert all(x["ret_3m"] >= 0 and x["kind"] == "etf" for x in j["rows"])
    assert client.post("/api/screener/run", headers=pro, json={"filters": [["nope", ">=", 1]]}).status_code == 422
    s = client.post("/api/me/screens", headers=pro, json={"name": "My momentum", "universe": "market", "filters": {"filters": [["ret_3m", ">=", 0.05]], "sort": "ret_3m", "desc": True, "kind": None}})
    assert s.status_code == 200
    ran = client.get(f"/api/me/screens/{s.json()['id']}/run", headers=pro).json()
    assert ran["rows"] is not None
    assert client.post("/api/screener/export", headers=pro, json={"filters": [], "sort": "dollar_volume"}).text.startswith("symbol,name")
    rows = [{"symbol": "A", "x": 1.0, "kind": "stock"}, {"symbol": "B", "x": None, "kind": "stock"}]
    assert screener.run([("x", ">=", 0.5)], "x", rows=rows)["matches"] == 1


def _tok(c, plan=None):
    h = "sc" + uuid.uuid4().hex[:8]
    tok = c.post("/api/auth/register", json={"email": f"{h}@test.io", "password": "pw-123456789", "handle": h, "display_name": h}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    if plan:
        c.post("/api/billing/checkout", json={"plan": plan}, headers=hdr)
    c.cookies.clear()
    return hdr


def test_info_units_are_fractions():
    from app.market.source import normalise_info
    aapl = normalise_info({"dividendYield": 0.41, "trailingAnnualDividendYield": 0.0041})
    assert abs(aapl["dividend_yield"] - 0.0041) < 1e-9
    assert abs(normalise_info({"dividendYield": 2.8})["dividend_yield"] - 0.028) < 1e-9
    voo = normalise_info({"netExpenseRatio": 0.03})
    assert abs(voo["expense_ratio"] - 0.0003) < 1e-9
    assert abs(normalise_info({"annualReportExpenseRatio": 0.0049, "netExpenseRatio": 0.49})["expense_ratio"] - 0.0049) < 1e-9


def test_live_snapshot_drops_demo_fallbacks(monkeypatch):
    from app import screener
    from app.market import service
    real = service.bars

    def bars(sym, tf="1d"):
        b = real(sym, tf)
        return {**b, "source": "DEMO" if sym == "EA" else "LIVE"}

    monkeypatch.setattr(service, "bars", bars)
    snap = screener.build(["AAPL", "EA", "MSFT"], with_info=False, live_quotes=False)
    assert snap["source"] == "LIVE" and snap["dropped"] == ["EA"]
    assert [r["symbol"] for r in snap["rows"]] == ["AAPL", "MSFT"]
