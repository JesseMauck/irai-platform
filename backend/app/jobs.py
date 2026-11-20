"""Scheduled jobs.  python -m app.jobs alerts   (run every minute from cron / a worker)"""
from __future__ import annotations

import sys

from .db import SessionLocal, init_db
from .routers.me import evaluate_alerts


def main(argv: list[str]) -> None:
    init_db()
    if argv[:1] == ["alerts"]:
        with SessionLocal() as db:
            for f in evaluate_alerts(db):
                print(f["message"])
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
