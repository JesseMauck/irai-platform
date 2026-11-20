"""Background jobs.

  python -m app.jobs alerts     evaluate alerts once
  python -m app.jobs mail       deliver queued emails once
  python -m app.jobs worker     loop forever: alerts + mail every IRAI_WORKER_INTERVAL seconds (default 60)

Run exactly one `worker` process per deployment (e.g. a separate Railway service), not inside the web
server: uvicorn can run several workers and each would fire every alert.
"""
from __future__ import annotations

import logging
import os
import sys
import time

from . import mail
from .config import settings
from .db import SessionLocal, init_db
from .routers.billing import process_trials
from .routers.me import check_screen_alerts, evaluate_alerts

log = logging.getLogger("irai.worker")


PREWARM_EVERY = int(os.environ.get("IRAI_PREWARM_SECONDS", "300"))
_last_prewarm = 0.0


def coverage_symbols(db) -> list[str]:
    """Every symbol a public page needs: ticker bar, ADR legs + FX, ETFs, peer groups."""
    from sqlalchemy import select

    from .models import AdrPair, EtfFund, Instrument, PeerMember

    syms: list[str] = list(db.scalars(select(Instrument.symbol).where(Instrument.in_ticker_bar)))
    from .market.engines import fx_symbol

    for a in db.scalars(select(AdrPair)):
        fx = fx_symbol(getattr(a, "local_currency", "") or "")
        syms += [a.adr_symbol, a.local_symbol] + ([fx] if fx else [])
    syms += list(db.scalars(select(EtfFund.symbol)))
    syms += list(db.scalars(select(PeerMember.symbol)))
    seen, out = set(), []
    for s in syms:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def prewarm(db, pause: float = 0.4) -> dict:
    """Refresh stored quotes for covered symbols at a gentle pace, so pages always have a recent
    last-known price (shown as STALE) even when the live feed is rate-limiting the web server."""
    from .market import service

    ok = live = 0
    for sym in coverage_symbols(db):
        if service.cooling_down():
            break
        try:
            q = service.quote(sym)
            ok += 1
            live += q.get("source") == "LIVE"
        except Exception:  # noqa: BLE001
            pass
        time.sleep(pause)
    return {"fetched": ok, "live": live, "cooling_down": service.cooling_down()}


def tick() -> dict:
    global _last_prewarm
    out = {}
    if settings.live and time.time() - _last_prewarm >= PREWARM_EVERY:
        _last_prewarm = time.time()
        with SessionLocal() as db:
            out["prewarm"] = prewarm(db)
    with SessionLocal() as db:
        out["alerts"] = len(evaluate_alerts(db))
    with SessionLocal() as db:
        out["screens"] = check_screen_alerts(db)
    with SessionLocal() as db:
        out["trials"] = process_trials(db)
    with SessionLocal() as db:
        out["mail"] = mail.deliver_pending(db)
    return out


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if settings.auto_create_tables:
        init_db()
    cmd = argv[:1]
    if cmd == ["alerts"]:
        with SessionLocal() as db:
            for f in evaluate_alerts(db):
                print(f["message"])
    elif cmd == ["mail"]:
        with SessionLocal() as db:
            print(mail.deliver_pending(db))
    elif cmd == ["worker"]:
        interval = int(os.environ.get("IRAI_WORKER_INTERVAL", "60"))
        log.info("worker started, interval %ss", interval)
        while True:
            started = time.time()
            try:
                log.info("tick %s", tick())
            except Exception:  # noqa: BLE001  (one bad tick must not kill the worker)
                log.exception("tick failed")
            time.sleep(max(1, interval - (time.time() - started)))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
