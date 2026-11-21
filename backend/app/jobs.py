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
ADR_SCAN_EVERY = int(os.environ.get("IRAI_ADR_SCAN_SECONDS", "180"))
BUZZ_BATCH = int(os.environ.get("IRAI_BUZZ_BATCH", "12"))
_last_prewarm = 0.0
_last_adr_scan = 0.0
_buzz_cursor = 0


def scan_adrs(db) -> dict:
    """Continuous ADR scanner: price every active pair, store one signal row each, prune > 7 days."""
    import datetime as dt

    from sqlalchemy import delete

    from .market import engines
    from .models import AdrSignal
    from .routers.monitors import _pairs

    rows = engines.build_adr_monitor(_pairs(db))
    now = dt.datetime.now(dt.timezone.utc)
    for r in rows:
        payload = {k: v for k, v in r.items() if k != "premium_history"}
        db.add(AdrSignal(adr_symbol=r["adr_symbol"], scanned_at=now, premium=r.get("premium"), deviation=r.get("deviation"),
                         z=r.get("z"), source=r.get("source", "ERROR"), confidence=r.get("confidence"),
                         tradable=bool(r.get("tradable")), payload=payload))
    db.execute(delete(AdrSignal).where(AdrSignal.scanned_at < now - dt.timedelta(days=7)))
    db.commit()
    flagged = [r for r in rows if abs(r.get("z") or 0) >= 2 and r.get("source") not in ("DEMO", "ERROR")]
    return {"pairs": len(rows), "flagged": len(flagged)}


def scan_buzz(db, batch: int = BUZZ_BATCH, pause: float = 2.5) -> dict:
    """Refresh buzz for the next `batch` covered symbols (round-robin), at a pace GDELT tolerates."""
    global _buzz_cursor
    import datetime as dt

    from . import research
    from .models import BuzzSnapshot

    syms = coverage_symbols(db)
    syms = [s for s in syms if not s.startswith("^") and not s.endswith("=X")]
    if not syms:
        return {"scored": 0}
    done = 0
    for _ in range(min(batch, len(syms))):
        sym = syms[_buzz_cursor % len(syms)]
        _buzz_cursor += 1
        try:
            b = research.buzz(sym, with_headlines=False)
        except Exception:  # noqa: BLE001
            continue
        row = db.get(BuzzSnapshot, sym) or BuzzSnapshot(symbol=sym)
        row.name, row.kind, row.score, row.level = b.get("name"), b.get("kind"), b["score"], b["level"]
        row.components = {**b["components"], **b["inputs"], "tone": b.get("tone")}
        row.as_of = dt.datetime.now(dt.timezone.utc)
        db.merge(row)
        done += 1
        time.sleep(pause)
    db.commit()
    return {"scored": done}


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


def refresh_pestel(db) -> dict:
    """Recompute the stalest curated theme's PESTEL radar (one per tick keeps GDELT happy)."""
    import datetime as dt

    from sqlalchemy import select

    from .models import ResearchTheme
    from .routers.workspace import compute_pestel, pestel_fresh

    themes = db.scalars(select(ResearchTheme).where(ResearchTheme.owner_id.is_(None))).all()
    stale = sorted((t for t in themes if not pestel_fresh(t)), key=lambda t: t.pestel_at.timestamp() if t.pestel_at else 0.0)
    if not stale:
        return {"refreshed": None}
    t = stale[0]
    t.pestel, t.pestel_at = compute_pestel(t), dt.datetime.now(dt.timezone.utc)
    db.commit()
    return {"refreshed": t.slug}


def tick() -> dict:
    global _last_prewarm, _last_adr_scan
    out = {}
    if time.time() - _last_adr_scan >= ADR_SCAN_EVERY:
        _last_adr_scan = time.time()
        with SessionLocal() as db:
            out["adr_scan"] = scan_adrs(db)
    if settings.live:
        with SessionLocal() as db:
            out["buzz"] = scan_buzz(db)
        with SessionLocal() as db:
            out["pestel"] = refresh_pestel(db)
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
