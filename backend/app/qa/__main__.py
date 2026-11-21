"""Synthetic-trader QA CLI.

  python -m app.qa run                 one bounded batch against IRAI_QA_TARGET, then exit
  python -m app.qa triage              validate new issues (rules, then Claude)
  python -m app.qa cycle               run + triage + GitHub sync (what the loop spawns each interval)
  python -m app.qa loop                always-on scheduler: cycle every IRAI_QA_INTERVAL s in a fresh process
  python -m app.qa status              last runs, heartbeat age, open issues by status
  python -m app.qa queue [--out F]     validated, unfixed issues as Markdown (the fixer's input)
  python -m app.qa mark FP STATUS [--ref URL] [--note TEXT]
                                       set an issue's status (fixed | wontfix | false_positive | valid), e.g. after a PR

Options for run/cycle: --seed N (reproducible sampling), --cohort NAME (force one cohort).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys

from sqlalchemy import func, select

from ..config import settings as app_settings
from ..db import SessionLocal, init_db
from ..models import QaIssue, QaRun
from . import runner, triage
from .config import load

STATUSES = {"fixed", "wontfix", "false_positive", "valid", "new"}


def status_report() -> dict:
    with SessionLocal() as db:
        runs = db.scalars(select(QaRun).order_by(QaRun.id.desc()).limit(10)).all()
        by_status = dict(db.execute(select(QaIssue.status, func.count()).group_by(QaIssue.status)).all())
        open_rows = db.execute(select(QaIssue.category, QaIssue.severity, func.count()).where(QaIssue.status.in_(["new", "valid", "regressed", "needs_more_data"]))
                               .group_by(QaIssue.category, QaIssue.severity)).all()
    now = dt.datetime.now(dt.timezone.utc)
    last = runs[0] if runs else None
    hb = last.heartbeat_at if last else None
    if hb is not None and hb.tzinfo is None:
        hb = hb.replace(tzinfo=dt.timezone.utc)
    return {
        "last_run": {"id": last.id, "status": last.status, "started_at": last.started_at.isoformat(), "heartbeat_age_s": round((now - hb).total_seconds()),
                     "requests": last.requests, "checks": last.checks, "issues_new": last.issues_new, "issues_seen": last.issues_seen} if last else None,
        "recent": [{"id": r.id, "status": r.status, "tickers": len(r.tickers or []), "new": r.issues_new, "seen": r.issues_seen} for r in runs],
        "issues_by_status": by_status,
        "open": [{"category": c, "severity": s, "count": n} for c, s, n in open_rows],
    }


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if app_settings.auto_create_tables:
        init_db()
    p = argparse.ArgumentParser(prog="python -m app.qa", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["run", "triage", "cycle", "loop", "status", "queue", "mark"])
    p.add_argument("args", nargs="*")
    p.add_argument("--seed", type=int)
    p.add_argument("--cohort")
    p.add_argument("--out")
    p.add_argument("--ref")
    p.add_argument("--note")
    a = p.parse_args(argv)
    s = load()
    if a.cmd in ("run", "cycle"):
        res = runner.run_once(s, seed=a.seed, cohort=a.cohort)
        print(json.dumps({k: v for k, v in res.items() if k != "results"}, default=str))
        if a.cmd == "cycle" and res.get("status") != "busy":
            from . import github

            with SessionLocal() as db:
                print(json.dumps({"triage": triage.triage(db, s)}))
                print(json.dumps({"github": github.sync(db)}))
        return 0 if res.get("status") in ("ok", "budget", "busy", "throttled") else 2
    if a.cmd == "triage":
        with SessionLocal() as db:
            print(json.dumps(triage.triage(db, s)))
        return 0
    if a.cmd == "loop":
        runner.loop(s)
        return 0
    if a.cmd == "status":
        print(json.dumps(status_report(), indent=1, default=str))
        return 0
    if a.cmd == "queue":
        with SessionLocal() as db:
            md = triage.queue_markdown(triage.fix_queue(db))
        if a.out:
            with open(a.out, "w") as fh:
                fh.write(md)
        else:
            print(md)
        return 0
    if a.cmd == "mark":
        if len(a.args) != 2 or a.args[1] not in STATUSES:
            p.error(f"usage: mark FINGERPRINT STATUS  (STATUS in {sorted(STATUSES)})")
        fp, st = a.args
        with SessionLocal() as db:
            row = db.scalar(select(QaIssue).where(QaIssue.fingerprint.startswith(fp)))
            if not row:
                print(f"no issue with fingerprint {fp}", file=sys.stderr)
                return 1
            row.status = st
            if a.ref:
                row.fix_ref = a.ref[:300]
            if a.note:
                row.triage = {**(row.triage or {}), "note": a.note, "marked_at": dt.datetime.now(dt.timezone.utc).isoformat()}
            db.commit()
            print(f"{row.fingerprint} -> {st}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
