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


def tick() -> dict:
    out = {}
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
