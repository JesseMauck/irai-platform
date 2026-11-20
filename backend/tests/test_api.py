"""End-to-end API tests on demo data: accounts, plan gating, research quota, community, alerts,
billing, and a full ValueBot run recorded in the database."""
import hashlib
import hmac
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def signup(c, plan=None):
    h = "u" + uuid.uuid4().hex[:10]
    r = c.post("/api/auth/register", json={"email": f"{h}@test.io", "password": "correct-horse-9",
                                           "handle": h, "display_name": h})
    assert r.status_code == 200, r.text
    hdr = {"Authorization": f"Bearer {r.json()['token']}"}
    if plan:
        assert c.post("/api/billing/checkout", json={"plan": plan}, headers=hdr).json()["plan"] == plan
    c.cookies.clear()
    return hdr


def test_health_and_tickerbar(client):
    assert client.get("/api/health").json()["ok"]
    bar = client.get("/api/market/tickerbar").json()
    assert len(bar) >= 5 and all("price" in x for x in bar)


def test_any_ticker_loads(client):
    t = client.get("/api/market/ticker/AAPL").json()
    assert t["quote"]["price"] > 0 and len(t["history"]) > 200 and t["info"]
    assert client.get("/api/market/ticker/NVDA").json()["grade"]["peer_group"] == "Semiconductors"
    assert client.get("/api/market/ticker/bad$$sym").status_code == 422
    assert client.get("/api/market/chart/MSFT?range=3mo").status_code == 200
    assert client.get("/api/market/search?q=apple").status_code == 200


def test_auth_flow(client):
    h = signup(client)
    me = client.get("/api/auth/me", headers=h).json()
    assert me["plan"] == "free" and me["limits"]["articles_per_month"] == 3
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/register", json={"email": me["email"], "password": "x" * 9, "handle": "other1", "display_name": "x"})
    assert r.status_code == 409
    assert client.post("/api/auth/login", json={"email": me["email"], "password": "wrong-pass"}).status_code == 401
    client.cookies.clear()


def test_monitor_gating(client):
    free = client.get("/api/monitors/adr").json()
    assert len(free["rows"]) == 5 and free["locked"] == free["total"] - 5
    paid = client.get("/api/monitors/adr", headers=signup(client, "essential")).json()
    assert len(paid["rows"]) == paid["total"] and paid["locked"] == 0
    for r in paid["rows"]:
        assert r["source"] in ("LIVE", "PROXY", "STALE", "DEMO") and "z" in r
    assert client.get("/api/monitors/etf").json()["rows"][0]["tier"]
    fund = client.get("/api/monitors/fundamental").json()["rows"][0]
    assert "residual" not in fund and fund["grade"]


def test_screeners_gating(client):
    assert client.get("/api/monitors/screeners/adr-discounts").status_code == 200
    assert client.get("/api/monitors/screeners/etf-gaps").status_code == 402
    pro = signup(client, "pro")
    assert client.get("/api/monitors/screeners/etf-gaps", headers=pro).status_code == 200
    assert client.get("/api/monitors/screeners/quality-leaders/csv", headers=pro).headers["content-type"].startswith("text/csv")


def test_article_quota(client):
    h = signup(client)
    slugs = [a["slug"] for a in client.get("/api/research/articles").json()]
    assert len(slugs) >= 5
    for s in slugs[:3]:
        assert client.get(f"/api/research/articles/{s}", headers=h).json()["locked"] is False
    assert client.get(f"/api/research/articles/{slugs[0]}", headers=h).json()["locked"] is False  # re-read is free
    fourth = client.get(f"/api/research/articles/{slugs[3]}", headers=h).json()
    assert fourth["locked"] is True and fourth["free_remaining"] == 0
    assert client.get(f"/api/research/articles/{slugs[3]}", headers=signup(client, "essential")).json()["locked"] is False
    assert client.get("/api/research/articles?category=ETF").json()[0]["category"] == "ETF"


def test_community_and_trades(client):
    free = signup(client)
    assert client.post("/api/community/threads", json={"community": "adr-arbitrage", "title": "Hello world",
                                                       "body": "x"}, headers=free).status_code == 402
    h = signup(client, "essential")
    t = client.post("/api/community/threads", json={"community": "adr-arbitrage", "title": "TM gap at the Tokyo open",
                                                    "body": "Thoughts?", "tickers": ["tm"]}, headers=h).json()
    assert t["tickers"] == ["TM"]
    assert client.post(f"/api/community/threads/{t['id']}/posts", json={"body": "Agree"}, headers=h).status_code == 200
    assert client.post(f"/api/community/threads/{t['id']}/vote", json={"value": 1}, headers=h).json()["score"] == 1
    assert client.post(f"/api/community/threads/{t['id']}/vote", json={"value": 1}, headers=h).json()["score"] == 1  # idempotent
    assert client.get(f"/api/community/threads/{t['id']}").json()["replies"] == 1
    assert client.post("/api/community/threads", json={"community": "pro-room", "title": "Pro only room",
                                                       "body": "x"}, headers=h).status_code == 402

    # entry price is captured from the market feed, not supplied by the user
    quote = client.get("/api/market/quote/TM").json()["price"]
    tr = client.post("/api/community/trades", json={"long": "TM", "short": "7203.T", "thesis": "Basis deviation, no earnings soon",
                                                    "entry_long": 1.0}, headers=h).json()
    assert tr["entry_long"] == quote and tr["entry_short"] > 0
    assert tr["verification"] == "self-reported"  # demo prices can't be timestamp-verified
    other = signup(client, "essential")
    assert client.post(f"/api/community/trades/{tr['id']}/close", headers=other).status_code == 403
    closed = client.post(f"/api/community/trades/{tr['id']}/close", headers=h).json()
    assert closed["status"] == "closed" and closed["return_pct"] is not None
    assert client.post(f"/api/community/trades/{tr['id']}/close", headers=h).status_code == 409
    assert client.put(f"/api/community/trades/{tr['id']}", json={"thesis": "edited"}, headers=h).status_code in (404, 405)  # no edit route exists
    lb = client.get("/api/community/leaderboard").json()
    assert all(r["verification"] != "self-reported" for r in lb["rows"])


def test_leaderboard_counts_only_verified(client):
    from app.db import SessionLocal
    from app.models import TradePost, User
    h = signup(client, "essential")
    me = client.get("/api/auth/me", headers=h).json()
    with SessionLocal() as db:
        for r in (0.05, -0.01, 0.03):
            db.add(TradePost(author_id=me["id"], long_symbol="X", thesis="t" * 10, entry_long=1, entry_source="LIVE",
                             verification="timestamp-verified", status="closed", return_pct=r))
        db.commit()
    rows = client.get("/api/community/leaderboard").json()["rows"]
    mine = next(r for r in rows if r["handle"] == me["handle"])
    assert mine["closed_trades"] == 3 and abs(mine["win_rate"] - 2 / 3) < 1e-9


def test_watchlists_and_alerts(client):
    h = signup(client)
    wl = client.get("/api/me/watchlists", headers=h).json()
    assert len(wl) == 1
    wid = wl[0]["id"]
    for s in ["AAPL", "MSFT", "aapl"]:
        client.post(f"/api/me/watchlists/{wid}/items", json={"symbol": s}, headers=h)
    wl = client.get("/api/me/watchlists", headers=h).json()[0]
    assert wl["symbols"] == ["AAPL", "MSFT"] and "AAPL" in wl["quotes"]
    assert client.post("/api/me/watchlists", json={"name": "Second"}, headers=h).status_code == 402
    assert client.post("/api/me/alerts", json={"symbol": "AAPL", "kind": "price_above", "threshold": 1}, headers=h).status_code == 402

    e = signup(client, "essential")
    a = client.post("/api/me/alerts", json={"symbol": "AAPL", "kind": "price_above", "threshold": 1}, headers=e).json()
    assert client.post("/api/me/alerts", json={"symbol": "AAPL", "kind": "price_above", "threshold": 1, "channel": "webhook",
                                               "webhook_url": "https://example.com/h"}, headers=e).status_code == 402
    from app.db import SessionLocal
    from app.routers.me import evaluate_alerts
    with SessionLocal() as db:
        fired = evaluate_alerts(db)
        assert any(f["alert_id"] == a["id"] for f in fired)
        assert not any(f["alert_id"] == a["id"] for f in evaluate_alerts(db))  # cooldown
    assert client.get("/api/me/alerts/events", headers=e).json()[0]["symbol"] == "AAPL"


def test_billing_dev_mode_and_cancel(client):
    h = signup(client)
    assert client.post("/api/billing/checkout", json={"plan": "platinum"}, headers=h).status_code == 422
    r = client.post("/api/billing/checkout", json={"plan": "pro", "interval": "annual"}, headers=h).json()
    assert r["dev_mode"] and r["plan"] == "pro"
    sub = client.get("/api/billing/subscription", headers=h).json()
    assert sub["subscription"]["status"] == "trialing" and sub["subscription"]["interval"] == "annual"
    assert client.post("/api/billing/cancel", headers=h).json()["plan"] == "free"


def test_stripe_signature():
    from app.routers.billing import verify_stripe_signature
    payload, secret, ts = b'{"a":1}', "whsec_test", int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    assert verify_stripe_signature(payload, f"t={ts},v1={sig}", secret)
    assert not verify_stripe_signature(payload, f"t={ts},v1={'0' * 64}", secret)
    assert not verify_stripe_signature(payload, f"t={ts - 3600},v1={sig}", secret)


def test_plans_glossary_faq(client):
    plans = client.get("/api/plans").json()
    assert [p["key"] for p in plans] == ["free", "essential", "pro"] and plans[1]["monthly"] == 49
    assert len(client.get("/api/glossary").json()) >= 10 and client.get("/api/faq").json()


def test_valuebot_run_recorded_and_quota(client):
    h = signup(client)
    assert client.post("/api/valuebot/jobs", json={"ticker": "DEMO"}).status_code == 401
    assert client.get("/api/valuebot/company/DEMO").json()["suggested_method"] == "fcff"
    job = client.post("/api/valuebot/jobs", json={"ticker": "DEMO", "stance": "bullish"}, headers=h).json()
    assert job["usage"]["remaining"] == 0
    for _ in range(240):
        st = client.get(f"/api/valuebot/jobs/{job['id']}").json()
        if st["status"] in ("done", "error"):
            break
        time.sleep(0.5)
    assert st["status"] == "done", st.get("error")
    res = client.get(f"/api/valuebot/jobs/{job['id']}/result").json()
    assert res["result"]["value_per_share"] > 0
    assert client.get(f"/api/valuebot/jobs/{job['id']}/files/model.xlsx").status_code == 200
    runs = client.get("/api/valuebot/jobs", headers=h).json()
    assert runs[0]["status"] == "done" and runs[0]["value_per_share"] == pytest.approx(res["result"]["value_per_share"])
    # what-if revalue and share link
    rv = client.post(f"/api/valuebot/jobs/{job['id']}/revalue", json={"assumptions": {"target_operating_margin": 0.35}}).json()
    assert rv["value_per_share"] > res["result"]["value_per_share"]
    assert client.get(f"/api/valuebot/share/{runs[0]['share_token']}").json()["read_only"] is True
    # quota: free plan = 1 run / month
    assert client.post("/api/valuebot/jobs", json={"ticker": "DEMO"}, headers=h).status_code == 402
    assert client.post("/api/valuebot/jobs", json={"ticker": "../../x"}, headers=h).status_code == 422
    assert client.get("/api/valuebot/jobs/../../etc").status_code == 404


def test_password_reset_flow_and_outbox(client):
    from sqlalchemy import select

    from app import mail
    from app.db import SessionLocal
    from app.models import EmailOutbox
    h = signup(client)
    me = client.get("/api/auth/me", headers=h).json()
    with SessionLocal() as db:
        kinds = [r.kind for r in db.scalars(select(EmailOutbox).where(EmailOutbox.to_addr == me["email"]))]
    assert "welcome" in kinds
    # unknown email gets the same answer (no account enumeration)
    a = client.post("/api/auth/forgot", json={"email": "nobody-here@test.io"}).json()
    b = client.post("/api/auth/forgot", json={"email": me["email"]}).json()
    assert a == b
    sent = []
    with SessionLocal() as db:
        mail.deliver_pending(db, sender=sent.append)
    reset_mail = next(m for m in sent if m.kind == "password_reset" and m.to_addr == me["email"])
    token = reset_mail.body_text.split("token=")[1].split()[0]
    time.sleep(1.1)  # old session's iat must be strictly before the reset second
    r = client.post("/api/auth/reset", json={"token": token, "password": "brand-new-pass-1"})
    assert r.status_code == 200
    new_hdr = {"Authorization": f"Bearer {r.json()['token']}"}
    client.cookies.clear()
    assert client.get("/api/auth/me", headers=h).status_code == 401       # old session revoked
    assert client.get("/api/auth/me", headers=new_hdr).status_code == 200
    assert client.post("/api/auth/reset", json={"token": token, "password": "another-pass-2"}).status_code == 400  # single use
    assert client.post("/api/auth/login", json={"email": me["email"], "password": "brand-new-pass-1"}).status_code == 200
    client.cookies.clear()


def test_mail_retry_backoff_then_fail():
    from app import mail
    from app.db import SessionLocal
    from app.models import EmailOutbox
    with SessionLocal() as db:
        row = mail.enqueue(db, "x@test.io", "s", "b", "test")
        db.commit()
        rid = row.id

    def boom(r):
        if r.id == rid:
            raise OSError("smtp down")

    with SessionLocal() as db:
        mail.deliver_pending(db, sender=boom)
        r = db.get(EmailOutbox, rid)
        assert r.status == "pending" and r.attempts == 1 and "smtp down" in r.last_error
        for _ in range(4):
            r.next_attempt_at = r.created_at  # pretend the backoff elapsed
            db.commit()
            mail.deliver_pending(db, sender=boom)
            db.refresh(r)
        assert r.status == "failed" and r.attempts == mail.MAX_ATTEMPTS


def test_email_alert_enqueued(client):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import EmailOutbox
    from app.routers.me import evaluate_alerts
    e = signup(client, "essential")
    me = client.get("/api/auth/me", headers=e).json()
    client.post("/api/me/alerts", json={"symbol": "NVDA", "kind": "price_above", "threshold": 0.01}, headers=e)
    with SessionLocal() as db:
        evaluate_alerts(db)
        assert db.scalar(select(EmailOutbox).where(EmailOutbox.to_addr == me["email"], EmailOutbox.kind == "alert"))


def test_api_keys_read_only_and_pro_only(client):
    free = signup(client)
    assert client.post("/api/me/api-keys", json={"name": "x"}, headers=free).status_code == 402
    pro = signup(client, "pro")
    k = client.post("/api/me/api-keys", json={"name": "notebook"}, headers=pro).json()
    assert k["key"].startswith("irai_") and k["prefix"] == k["key"][:12]
    hdr = {"X-API-Key": k["key"]}
    assert client.get("/api/monitors/adr", headers=hdr).json()["locked"] == 0      # Pro data via key
    assert client.get("/api/me/api-keys", headers=pro).json()[0]["name"] == "notebook"
    assert "key" not in client.get("/api/me/api-keys", headers=pro).json()[0]       # plaintext never shown again
    assert client.post("/api/me/alerts", json={"symbol": "A", "kind": "price_above", "threshold": 1}, headers=hdr).status_code == 403
    assert client.get("/api/monitors/adr", headers={"X-API-Key": "irai_wrong"}).status_code == 401
    client.delete(f"/api/me/api-keys/{k['id']}", headers=pro)
    assert client.get("/api/monitors/adr", headers=hdr).status_code == 401


def test_grade_detail_gated_for_free(client):
    anon = client.get("/api/market/ticker/NVDA").json()["grade"]
    assert anon["locked"] and "rv_percentile" not in anon and anon["grade"]
    paid = client.get("/api/market/ticker/NVDA", headers=signup(client, "essential")).json()["grade"]
    assert paid.get("locked") is None and paid["rv_percentile"] is not None
    assert client.get("/api/monitors/fundamental").json()["rows"][0]["rv_percentile"] is None


def test_pair_ideas_pro_only(client):
    assert client.get("/api/monitors/pair-ideas", headers=signup(client, "essential")).status_code == 402
    ideas = client.get("/api/monitors/pair-ideas", headers=signup(client, "pro")).json()
    assert ideas and ideas[0]["spread_sigma"] > 0 and ideas[0]["long"]["symbol"] != ideas[0]["short"]["symbol"]


def test_point_in_time_snapshots_once_per_day():
    from app.db import SessionLocal
    from app.routers.monitors import record_snapshots
    rows = [{"symbol": "ZZZ1", "peer_group": "T", "grade": "A", "rv_percentile": 90.0, "quality_percentile": 50.0,
             "multiple": 10.0, "multiple_name": "P/E", "residual": -0.2, "source": "LIVE"}]
    with SessionLocal() as db:
        assert record_snapshots(db, rows) == 1
        assert record_snapshots(db, [{**rows[0], "rv_percentile": 10.0}]) == 0  # not restated the same day


def test_saved_screens(client):
    free = signup(client)
    body = {"name": "Cheap quality", "universe": "fundamental", "filters": {"rv_min": 50}}
    assert client.post("/api/me/screens", json=body, headers=free).status_code == 402
    e = signup(client, "essential")
    prev = client.post("/api/me/screens/preview", json=body, headers=e).json()["rows"]
    assert prev and all(r["value"] >= 50 for r in prev)
    sc = client.post("/api/me/screens", json={**body, "alert_on_new": True}, headers=e).json()
    assert sc["alert_on_new"] is True
    assert client.get(f"/api/me/screens/{sc['id']}/run", headers=e).json()["rows"] == prev
    assert client.post("/api/me/screens", json={**body, "filters": {"bogus": 1}}, headers=e).status_code == 422
    for i in range(4):
        client.post("/api/me/screens", json={**body, "name": f"s{i}"}, headers=e)
    assert client.post("/api/me/screens", json=body, headers=e).status_code == 402  # 5 saved max on Essential
    adr = client.post("/api/me/screens/preview", json={"name": "x", "universe": "adr", "filters": {"z_abs_min": 0}}, headers=e).json()
    assert len(adr["rows"]) > 0
    from app.db import SessionLocal
    from app.models import SavedScreen
    from app.routers.me import check_screen_alerts
    with SessionLocal() as db:
        s = db.get(SavedScreen, sc["id"])
        s.last_symbols = []
        db.commit()
        assert check_screen_alerts(db) >= 1
