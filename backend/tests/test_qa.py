"""Synthetic-trader QA agent: dedup, guardrails, a clean run, injected-bug detection, backoff, lease, triage, alerts."""
import dataclasses
import datetime as dt
import subprocess
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app import paper
from app.db import SessionLocal
from app.main import app
from app.models import EmailOutbox, QaIssue, QaRun, QaTickerLedger, User
from app.qa import findings as fnd
from app.qa import runner, triage
from app.qa.client import QaClient, Throttled
from app.qa.config import load
from app.qa.identity import is_synthetic_email


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_qa():
    from app.db import init_db

    init_db()

    def wipe():
        with SessionLocal() as db:
            for m in (QaIssue, QaRun, QaTickerLedger):
                db.execute(delete(m))
            db.commit()
    wipe()
    yield
    wipe()


def S(**kw):
    return dataclasses.replace(load(), **{"target": "inprocess", "env": "local", "backoff_base": 0, **kw})


def _finding(**kw):
    base = dict(issue_type="server_error", category="bug", severity="high", flow="market_probe", endpoint="GET /api/market/quote/AAPL",
                title="t", expected="e", actual="a", ticker="AAPL", error="500 boom for AAPL at 12.5 id 4411")
    return fnd.Finding(**{**base, **kw})


# ── dedup ────────────────────────────────────────────────────────────────────────────────────────
def test_fingerprint_ignores_ids_numbers_and_ticker():
    a = _finding()
    b = _finding(endpoint="GET /api/market/quote/MSFT", ticker="MSFT", error="500 boom for MSFT at 99.1 id 7")
    assert a.fingerprint == b.fingerprint
    assert fnd.normalize_endpoint("POST /api/bots/42/run") == "POST /api/bots/{id}/run"
    assert fnd.normalize_endpoint("POST /api/bots/hook/abcdefghijklmnopqrstuvwxyz") == "POST /api/bots/hook/{token}"
    assert _finding(issue_type="bad_fill").fingerprint != a.fingerprint
    assert _finding(flow="webhook_trader").fingerprint != a.fingerprint


def test_record_dedups_then_flags_regression():
    with SessionLocal() as db:
        row, new = fnd.record(db, _finding(), 1)
        assert new
        row2, new2 = fnd.record(db, _finding(ticker="MSFT", endpoint="GET /api/market/quote/MSFT", error="500 boom for MSFT at 1 id 2"), 2)
        assert not new2 and row2.id == row.id and row2.occurrences == 2 and row2.tickers == ["AAPL", "MSFT"]
        row.status = "fixed"
        row3, _ = fnd.record(db, _finding(), 3)
        assert row3.status == "regressed" and row3.last_run_id == 3
        db.commit()


# ── guardrails ───────────────────────────────────────────────────────────────────────────────────
def test_guard_refuses_production_targets():
    for kw in ({"target": "https://api.irradiance.ai", "env": "local"}, {"target": "http://localhost:8000", "env": "production"}):
        with pytest.raises(RuntimeError, match="looks like production"):
            dataclasses.replace(load(), **kw).guard()
    dataclasses.replace(load(), target="https://api.irradiance.ai", env="production", allow_production=True).guard()
    dataclasses.replace(load(), target="https://staging-api.example.com", env="staging").guard()


# ── a clean run ──────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("cohort", ["market_probe", "momentum_bot", "reversion_bot", "webhook_trader", "risk_limits"])
def test_clean_run_files_nothing_and_cleans_up(client, cohort):
    res = runner.run_once(S(batch_size=4), seed=3, cohort=cohort)
    assert res["status"] == "ok", res
    assert res["tickers"] == 4 and res["checks"] > 10
    assert res["issues_new"] == 0, [(i.issue_type, i.step, i.actual) for i in SessionLocal().scalars(select(QaIssue))]
    with SessionLocal() as db:
        run = db.get(QaRun, res["run_id"])
        assert run.status == "ok" and run.finished_at and run.summary["identities_cleaned"] >= 1
        assert db.scalar(select(func.count()).select_from(User).where(User.email.like("%@qa.irai.invalid"))) == 0
        assert db.scalar(select(func.count()).select_from(QaTickerLedger)) == 4


def test_edge_case_symbols_get_4xx_not_5xx(client):
    from app.qa import tickers

    rejects = [p for p in tickers.EDGE_POOL if p.expect == "reject"]
    assert rejects
    with SessionLocal() as db:
        run = runner.acquire_lease(db, S())
    from app.qa.trader import Ctx, market_probe, webhook_trader

    qc = QaClient.build(S())
    tokens = {}

    def ident(c):
        from app.qa import identity

        with SessionLocal() as db:
            tokens.setdefault(c, identity.provision(db, run.id, c)[1])
        return tokens[c]

    import random

    ctx = Ctx(qc, S(), run.id, ident, live=False, rng=random.Random(1))
    for p in rejects:
        market_probe(ctx, p)
        webhook_trader(ctx, p)
    assert [(f.issue_type, f.step, f.ticker, f.actual) for f in ctx.findings] == []
    with SessionLocal() as db:
        from app.qa import identity

        identity.cleanup_run(db, run.id)


# ── the trader catches real bugs ─────────────────────────────────────────────────────────────────
def test_detects_position_cap_bug(client, monkeypatch):
    monkeypatch.setattr(paper, "per_symbol_budget", lambda bot, eq: eq * 3)  # ignores max_position_pct
    res = runner.run_once(S(batch_size=2), seed=5, cohort="risk_limits")
    with SessionLocal() as db:
        types = {i.issue_type for i in db.scalars(select(QaIssue))}
    assert res["issues_new"] >= 1 and "position_over_cap" in types


def test_detects_server_error(client, monkeypatch):
    from app.market import service

    real = service.quote
    monkeypatch.setattr(service, "quote", lambda s, *a, **k: (_ for _ in ()).throw(RuntimeError("feed exploded")) if s != "SPY" else real(s, *a, **k))
    runner.run_once(S(batch_size=2), seed=9, cohort="market_probe")
    with SessionLocal() as db:
        rows = db.scalars(select(QaIssue).where(QaIssue.issue_type == "server_error")).all()
    assert rows and rows[0].severity == "high" and rows[0].trace["status"] == 500
    assert "authorization" not in str(rows[0].trace).lower()


def test_detects_paused_bot_trading(client, monkeypatch):
    real = paper.handle_webhook

    def leaky(db, bot, payload):
        status, bot.status = bot.status, "running"  # bug: pause is ignored
        try:
            return real(db, bot, payload)
        finally:
            bot.status = status
    monkeypatch.setattr(paper, "handle_webhook", leaky)
    runner.run_once(S(batch_size=1), seed=2, cohort="webhook_trader")
    with SessionLocal() as db:
        assert db.scalar(select(QaIssue).where(QaIssue.issue_type == "paused_bot_traded")) is not None


# ── client: backoff and throttling ───────────────────────────────────────────────────────────────
def _mock_client(handler, **kw):
    slept = []
    qc = QaClient(settings=S(backoff_base=1.0, **kw), http=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://t"), sleep=slept.append)
    return qc, slept


def test_retries_with_exponential_backoff():
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        return httpx.Response(503) if n["i"] < 3 else httpx.Response(200, json={"ok": True})
    qc, slept = _mock_client(h)
    c = qc.call("GET", "/x")
    assert c.ok and c.attempts == 3 and slept == [1.0, 2.0] and qc.requests == 3


def test_long_retry_after_ends_run_politely():
    qc, _ = _mock_client(lambda req: httpx.Response(429, headers={"Retry-After": "600"}, json={"detail": "slow down"}))
    with pytest.raises(Throttled):
        qc.call("POST", "/api/bots")


def test_budget_is_enforced():
    from app.qa.client import BudgetExhausted

    qc, _ = _mock_client(lambda req: httpx.Response(200, json={}), max_requests=2)
    qc.call("GET", "/a")
    qc.call("GET", "/b")
    with pytest.raises(BudgetExhausted):
        qc.call("GET", "/c")


# ── lease ────────────────────────────────────────────────────────────────────────────────────────
def test_lease_blocks_concurrent_runs_and_reclaims_stale_ones():
    s = S()
    with SessionLocal() as db:
        first = runner.acquire_lease(db, s)
        assert first and runner.acquire_lease(db, s) is None
        first.heartbeat_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=s.lease_stale_after + 5)
        db.commit()
        second = runner.acquire_lease(db, s)
        assert second and db.get(QaRun, first.id).status == "crashed"
        second.status = "ok"
        db.commit()


# ── triage ───────────────────────────────────────────────────────────────────────────────────────
def test_triage_rules_then_llm_then_queue():
    with SessionLocal() as db:
        real, _ = fnd.record(db, _finding(issue_type="position_over_cap", category="trading_logic"), 1)
        demo, _ = fnd.record(db, _finding(issue_type="demo_data_in_live_mode", category="data", severity="medium",
                                          context={"live_market_data": False}), 1)
        closed, _ = fnd.record(db, _finding(issue_type="rejected_valid_request", severity="medium", actual="HTTP 422: market is closed"), 1)
        blip, _ = fnd.record(db, _finding(issue_type="slow_response", category="latency", severity="low"), 1)
        nolive, _ = fnd.record(db, _finding(issue_type="rejected_valid_request", severity="medium", flow="webhook_trader",
                                            actual="HTTP 422: No live price for BMY (feed unavailable, only DEMO data); not trading on it"), 1)
        db.commit()
        calls = []

        def fake_llm(issue, s):
            calls.append(issue.issue_type)
            return {"verdict": "valid", "category": "trading_logic", "severity": "high", "rationale": "cap ignored",
                    "likely_location": "app/paper.py per_symbol_budget", "regression_test": "def test_cap(): ..."}
        out = triage.triage(db, S(), llm=fake_llm)
        assert calls == ["position_over_cap"] and out["claude"] == 1 and out["rules"] == 4
        assert db.get(QaIssue, nolive.id).status == "false_positive"
        assert db.get(QaIssue, real.id).status == "valid"
        assert db.get(QaIssue, demo.id).status == "false_positive"
        assert db.get(QaIssue, closed.id).status == "false_positive"
        assert db.get(QaIssue, blip.id).status == "needs_more_data"
        # nothing new: the blip isn't re-triaged; once it recurs, it is
        assert triage.triage(db, S(), llm=fake_llm)["rules"] == 0
        fnd.record(db, _finding(issue_type="slow_response", category="latency", severity="low"), 2)
        db.commit()
        triage.triage(db, S(), llm=fake_llm)
        assert calls[-1] == "slow_response"
        md = triage.queue_markdown(triage.fix_queue(db))
        assert real.fingerprint in md and "per_symbol_budget" in md and demo.fingerprint not in md


def test_triage_respects_llm_budget_and_outages():
    with SessionLocal() as db:
        for k in range(4):
            fnd.record(db, _finding(issue_type=f"server_error_{k}"), 1)
        db.commit()
        out = triage.triage(db, S(triage_max=2), llm=lambda i, s: (_ for _ in ()).throw(RuntimeError("API down")))
        assert out == {"rules": 0, "claude": 0, "skipped": 4, "valid": 0}
        assert all(i.status == "new" for i in db.scalars(select(QaIssue)))


# ── admin API and metrics hygiene ────────────────────────────────────────────────────────────────
def _admin(c):
    h = "ad" + uuid.uuid4().hex[:8]
    tok = c.post("/api/auth/register", json={"email": f"{h}@test.io", "password": "pw-123456789", "handle": h, "display_name": h}).json()["token"]
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.handle == h))
        u.is_admin = True
        db.commit()
    c.cookies.clear()
    return {"Authorization": f"Bearer {tok}"}


def test_admin_qa_endpoints(client):
    hdr = _admin(client)
    with SessionLocal() as db:
        row, _ = fnd.record(db, _finding(), 1)
        db.commit()
    assert client.get("/api/admin/qa/issues").status_code == 401
    lst = client.get("/api/admin/qa/issues?status=new", headers=hdr).json()
    assert [i["fingerprint"] for i in lst] == [row.fingerprint]
    full = client.get(f"/api/admin/qa/issues/{row.id}", headers=hdr).json()
    assert full["trace"] is None and full["expected"] == "e"
    p = client.patch(f"/api/admin/qa/issues/{row.id}", headers=hdr, json={"status": "fixed", "fix_ref": "https://github.com/x/y/pull/1"}).json()
    assert p["status"] == "fixed" and p["fix_ref"].endswith("/1")
    assert client.patch(f"/api/admin/qa/issues/{row.id}", headers=hdr, json={"status": "bogus"}).status_code == 422
    assert "issues_by_status" in client.get("/api/admin/qa/status", headers=hdr).json()


def test_synthetic_users_excluded_from_business_stats(client):
    hdr = _admin(client)
    before = client.get("/api/admin/stats", headers=hdr).json()["users"]["total"]
    from app.qa import identity

    with SessionLocal() as db:
        u, _ = identity.provision(db, 999, "probe")
        assert is_synthetic_email(u.email) and u.preferences["synthetic_qa"]
    assert client.get("/api/admin/stats", headers=hdr).json()["users"]["total"] == before
    with SessionLocal() as db:
        assert identity.cleanup_run(db, 999) == 1


# ── loop: backoff and alerting ───────────────────────────────────────────────────────────────────
def test_loop_backs_off_and_alerts_once_per_streak(client, monkeypatch):
    _admin(client)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 2))
    waits = []
    with SessionLocal() as db:
        db.execute(delete(EmailOutbox).where(EmailOutbox.kind == "qa_alert"))
        db.commit()
    runner.loop(S(interval=10, alert_after_failures=2), max_cycles=4, sleep=waits.append)
    assert waits[0] >= 19 and waits[1] > waits[0] and waits[3] > waits[2]  # 10*2^1, 10*2^2, ...
    with SessionLocal() as db:
        alerts = db.scalars(select(EmailOutbox).where(EmailOutbox.kind == "qa_alert")).all()
    admins = {a.to_addr for a in alerts}
    assert alerts and len(alerts) == len(admins)  # one alert per admin for the streak, not one per failure


# ── GitHub bridge (qa service → GitHub; GitHub never gets database access) ─────────────────────
def _gh(private=True, issues=None, pulls=None):
    calls = []

    def h(req):
        calls.append((req.method, req.url.path, req.content.decode() if req.content else ""))
        p = req.url.path
        if p == "/repos/o/r":
            return httpx.Response(200, json={"private": private})
        if p == "/repos/o/r/pulls":
            return httpx.Response(200, json=pulls or [])
        if p == "/repos/o/r/issues" and req.method == "GET":
            return httpx.Response(200, json=issues or [])
        if p == "/repos/o/r/issues" and req.method == "POST":
            return httpx.Response(201, json={"number": 7})
        if p.startswith("/repos/o/r/issues/") and req.method == "PATCH":
            return httpx.Response(200, json={})
        return httpx.Response(404, json={})
    return httpx.MockTransport(h), calls


def test_github_bridge_publishes_queue_and_marks_merged_fixes(monkeypatch):
    from app.qa import github

    monkeypatch.setenv("IRAI_QA_GITHUB_TOKEN", "t")
    monkeypatch.setenv("IRAI_QA_GITHUB_REPO", "o/r")
    with SessionLocal() as db:
        a, _ = fnd.record(db, _finding(issue_type="position_over_cap"), 1)
        b, _ = fnd.record(db, _finding(issue_type="bad_fill"), 1)
        a.status = b.status = "valid"
        db.commit()
        pr = {"merged_at": "2026-11-21T00:00:00Z", "html_url": "https://github.com/o/r/pull/3", "body": f"Fix\n\nQA-Fixes: {b.fingerprint}\n"}
        unmerged = {"merged_at": None, "html_url": "https://github.com/o/r/pull/4", "body": f"QA-Fixes: {a.fingerprint}"}
        t, calls = _gh(pulls=[pr, unmerged])
        out = github.sync(db, transport=t)
        assert out["marked_fixed"] == [b.fingerprint] and out["created"] and out["items"] == 1
        db.refresh(a), db.refresh(b)
        assert b.status == "fixed" and b.fix_ref.endswith("/3") and a.status == "valid"
        body = next(c[2] for c in calls if c[0] == "POST")
        assert a.fingerprint in body and b.fingerprint not in body and "qa-fix-queue" in body


def test_github_bridge_refuses_public_repo_and_survives_outages(monkeypatch):
    from app.qa import github

    assert github.sync(SessionLocal()) == {"enabled": False}
    monkeypatch.setenv("IRAI_QA_GITHUB_TOKEN", "t")
    monkeypatch.setenv("IRAI_QA_GITHUB_REPO", "o/r")
    with SessionLocal() as db:
        row, _ = fnd.record(db, _finding(), 1)
        row.status = "valid"
        db.commit()
        t, calls = _gh(private=False)
        out = github.sync(db, transport=t)
        assert out["published"] is False and "public" in out["reason"]
        assert not any(m in ("POST", "PATCH") for m, _, _ in calls)
        down = httpx.MockTransport(lambda req: httpx.Response(502, text="bad gateway"))
        assert "error" in github.sync(db, transport=down)
