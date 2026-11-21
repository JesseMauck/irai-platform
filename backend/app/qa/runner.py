"""Orchestration: one bounded run (lease, heartbeat, budgets, cleanup) and the always-on loop around it."""
from __future__ import annotations

import datetime as dt
import logging
import os
import random
import subprocess
import sys
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import QaRun, User
from . import findings as fnd
from . import identity, tickers
from .client import BudgetExhausted, QaClient, TargetUnhealthy, Throttled
from .config import QaSettings, load
from .trader import Ctx, test_ticker

log = logging.getLogger("irai.qa")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(t: dt.datetime) -> dt.datetime:
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def acquire_lease(db: Session, s: QaSettings) -> QaRun | None:
    """At most one run at a time across all processes. A 'running' row whose heartbeat went stale is marked crashed."""
    cutoff = _now() - dt.timedelta(seconds=s.lease_stale_after)
    for r in db.scalars(select(QaRun).where(QaRun.status == "running")):
        if _aware(r.heartbeat_at) < cutoff:
            r.status, r.finished_at = "crashed", _now()
            r.summary = {**(r.summary or {}), "note": "heartbeat went stale; marked crashed by the next run"}
        else:
            db.commit()
            return None
    run = QaRun(status="running", target=s.target[:200], env=s.env, started_at=_now(), heartbeat_at=_now(), tickers=[],
                requests=0, checks=0, issues_new=0, issues_seen=0)
    db.add(run)
    db.commit()
    return run


def _heartbeat(db: Session, run: QaRun, client: QaClient, ctx: Ctx | None) -> None:
    run.heartbeat_at = _now()
    run.requests = client.requests
    if ctx:
        run.checks = ctx.checks
    db.commit()


def run_once(settings: QaSettings | None = None, seed: int | None = None, cohort: str | None = None) -> dict[str, Any]:
    """Execute one bounded batch and exit. Safe to call from tests (target=inprocess)."""
    s = settings or load()
    s.guard()
    rng = random.Random(seed)
    with SessionLocal() as db:
        swept = identity.sweep_orphans(db)
        run = acquire_lease(db, s)
        if run is None:
            return {"status": "busy"}
        run_id = run.id
        picks = tickers.sample(db, s.batch_size, rng)
        run.tickers = [{"symbol": p.symbol, "kind": p.kind, "tag": p.tag} for p in picks]
        db.commit()

    client = QaClient.build(s)
    tokens: dict[str, str] = {}

    def ident(cohort_name: str) -> str:
        if cohort_name not in tokens:
            with SessionLocal() as db:
                _, tokens[cohort_name] = identity.provision(db, run_id, cohort_name)
        return tokens[cohort_name]

    status, note, deadline = "ok", "", time.monotonic() + s.max_seconds
    ctx: Ctx | None = None
    results: list[dict[str, Any]] = []
    new = seen = 0
    try:
        health = client.call("GET", "/api/health")
        if health.status != 200:
            raise TargetUnhealthy(f"/api/health returned {health.status}")
        mode = ((health.body or {}).get("market") or {}).get("mode", "live")
        ctx = Ctx(client=client, settings=s, run_id=run_id, identity=ident, live=mode == "live", rng=rng)
        me = client.call("GET", "/api/auth/me", token=ident("probe"))
        if me.status != 200:  # the target must share our database and JWT secret, or every flow would 401
            raise TargetUnhealthy(f"synthetic identity rejected by target (/api/auth/me {me.status}); check DATABASE_URL and IRAI_JWT_SECRET")
        for pick in picks:
            if time.monotonic() > deadline:
                status, note = "budget", f"wall-clock budget of {s.max_seconds}s used"
                break
            before = len(ctx.findings)
            try:
                used, flow = test_ticker(ctx, pick, cohort)
                result = "issues" if flow.failed else "pass"
            except (BudgetExhausted, TargetUnhealthy, Throttled):
                raise
            except Exception as e:  # noqa: BLE001  (a trader bug must not kill the run; it is itself a finding)
                log.exception("qa flow crashed on %s", pick.symbol)
                used, result = cohort or "unknown", "error"
                ctx.findings.append(fnd.Finding("qa_flow_crash", "bug", "low", used, "qa", f"QA flow crashed on {pick.symbol}",
                                                "the synthetic flow completes", f"{type(e).__name__}: {e}", ticker=pick.symbol,
                                                error=f"{type(e).__name__}: {e}"))
            with SessionLocal() as db:
                for f in ctx.findings[before:]:
                    _, is_new = fnd.record(db, f, run_id)
                    new += is_new
                    seen += not is_new
                tickers.mark(db, pick.symbol, used, result)
                r = db.get(QaRun, run_id)
                r.issues_new, r.issues_seen = new, seen
                _heartbeat(db, r, client, ctx)
            results.append({"symbol": pick.symbol, "cohort": used, "result": result, "findings": len(ctx.findings) - before})
    except BudgetExhausted as e:
        status, note = "budget", str(e)
    except Throttled as e:
        status, note = "throttled", str(e)
        log.info("qa run %s throttled by target: %s", run_id, e)
    except TargetUnhealthy as e:
        status, note = "aborted", str(e)
        log.warning("qa run %s aborted: %s", run_id, e)
    finally:
        client.close()
        with SessionLocal() as db:
            cleaned = identity.cleanup_run(db, run_id)
            r = db.get(QaRun, run_id)
            r.status, r.finished_at = status, _now()
            r.requests, r.checks = client.requests, ctx.checks if ctx else 0
            r.issues_new, r.issues_seen = new, seen
            r.summary = {"results": results, "note": note, "identities_cleaned": cleaned, "orphans_swept": swept,
                         "throttled_checks": ctx.throttled if ctx else 0,
                         "live_market_data": ctx.live if ctx else None}
            db.commit()
    return {"run_id": run_id, "status": status, "note": note, "tickers": len(results), "requests": client.requests,
            "checks": ctx.checks if ctx else 0, "issues_new": new, "issues_seen": seen, "results": results}


# ── always-on loop ───────────────────────────────────────────────────────────────────────────────
def _alert(subject: str, body: str) -> None:
    """Email every (non-synthetic) admin through the existing outbox; the worker delivers it."""
    from .. import mail

    with SessionLocal() as db:
        admins = [u for u in db.scalars(select(User).where(User.is_admin, User.disabled.is_(False))) if not identity.is_synthetic_email(u.email)]
        for u in admins:
            mail.enqueue(db, u.email, f"[IRAI QA] {subject}", body, "qa_alert")
        db.commit()
    log.error("qa alert: %s — %s", subject, body)


def loop(settings: QaSettings | None = None, max_cycles: int | None = None, sleep=time.sleep) -> None:
    """Forever: spawn `python -m app.qa cycle` in a fresh process with a hard timeout, then sleep.
    Exponential backoff after failures; one alert per failure streak."""
    s = settings or load()
    s.guard()
    fails, alerted, n = 0, False, 0
    log.info("qa loop started: target=%s env=%s interval=%ss", s.target, s.env, s.interval)
    while max_cycles is None or n < max_cycles:
        n += 1
        started = time.time()
        try:
            proc = subprocess.run([sys.executable, "-m", "app.qa", "cycle"], timeout=s.run_timeout, env=os.environ.copy(),
                                  cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            ok = proc.returncode == 0
            reason = f"exit code {proc.returncode}"
        except subprocess.TimeoutExpired:
            ok, reason = False, f"timed out after {s.run_timeout}s"
        if ok:
            if alerted:
                _alert("QA runs recovered", f"Synthetic-trader runs are succeeding again after {fails} failure(s).")
            fails, alerted = 0, False
        else:
            fails += 1
            log.error("qa cycle failed (%s), %d in a row", reason, fails)
            if fails >= s.alert_after_failures and not alerted:
                _alert(f"{fails} consecutive QA cycle failures", f"Last failure: {reason}. Target {s.target} (env {s.env}). "
                       "Check the qa service logs and Admin → QA status.")
                alerted = True
        wait = s.interval * (2 ** min(fails, 4)) if fails else s.interval
        sleep(max(5, wait - (time.time() - started)))
