"""Create tables and load reference data from seed_data/*.json.  Run:  python -m app.seed [--demo-users]

Idempotent: rows that already exist (by natural key) are left alone, so it is safe to re-run after
editing the JSON to add pairs, funds, peers or articles.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .models import AdrPair, Article, Community, EtfFund, Instrument, PeerGroup, PeerMember, Thread, User
from .security import hash_password

DATA = Path(__file__).parent / "seed_data"


def _load(name: str):
    return json.loads((DATA / name).read_text())


def seed_reference(db: Session) -> dict[str, int]:
    n = {"instruments": 0, "adr_pairs": 0, "etf_funds": 0, "peer_members": 0, "articles": 0, "communities": 0}
    for row in _load("instruments.json"):
        if not db.get(Instrument, row["symbol"]):
            db.add(Instrument(**row)); n["instruments"] += 1
    for row in _load("adr_pairs.json"):
        if not db.scalar(select(AdrPair).where(AdrPair.adr_symbol == row["adr_symbol"])):
            db.add(AdrPair(**row)); n["adr_pairs"] += 1
    for row in _load("etf_funds.json"):
        if not db.get(EtfFund, row["symbol"]):
            db.add(EtfFund(**row)); n["etf_funds"] += 1
    db.flush()
    for g in _load("peer_groups.json"):
        grp = db.scalar(select(PeerGroup).where(PeerGroup.name == g["name"]))
        if not grp:
            grp = PeerGroup(name=g["name"], sector=g["sector"]); db.add(grp); db.flush()
        have = {m.symbol for m in grp.members}
        for sym, name in g["members"]:
            if sym not in have:
                db.add(PeerMember(group_id=grp.id, symbol=sym, name=name)); n["peer_members"] += 1
    for a in _load("articles.json"):
        if not db.scalar(select(Article).where(Article.slug == a["slug"])):
            a = {**a, "published_at": dt.datetime.fromisoformat(a["published_at"]).replace(tzinfo=dt.timezone.utc)}
            db.add(Article(**a)); n["articles"] += 1
    for c in _load("communities.json"):
        if not db.scalar(select(Community).where(Community.slug == c["slug"])):
            db.add(Community(**c)); n["communities"] += 1
    db.commit()
    return n


DEMO_USERS = [("admin@irai-demo.com", "admin", "IRAI Admin", "pro", True),
              ("essential@irai-demo.com", "essential-demo", "Essential Demo", "essential", False),
              ("free@irai-demo.com", "free-demo", "Free Demo", "free", False)]


def seed_demo_users(db: Session, password: str = "irai-demo-2026") -> None:
    """Local-development accounts. Never run against production."""
    for email, handle, name, plan, admin in DEMO_USERS:
        if not db.scalar(select(User).where(User.email == email)):
            db.add(User(email=email, handle=handle, display_name=name, plan=plan, is_admin=admin,
                        password_hash=hash_password(password)))
    db.commit()
    admin = db.scalar(select(User).where(User.handle == "admin"))
    if not db.scalar(select(Thread).limit(1)):
        comm = {c.slug: c for c in db.scalars(select(Community))}
        for slug, title, body, tick in [
            ("adr-arbitrage", "TSM premium to 2330.TW: structural or stretched?", "The basis has been drifting up for months. Is the foreign-ownership cap still the main driver?", ["TSM"]),
            ("etf-mechanics", "HYG discounts during selloffs: who is right, price or NAV?", "Evaluated bond prices lag. Has anyone measured how fast NAV catches up?", ["HYG"]),
            ("valuebot-models", "ValueBot on AAPL: what growth does the price imply?", "Reverse DCF says the market wants ~9% revenue growth for five years. Too much?", ["AAPL"]),
            ("platform-feedback", "Feature request: alert on ADR z-score crossing ±2", "Would love webhook alerts when a pair's z-score crosses a threshold.", []),
        ]:
            db.add(Thread(community_id=comm[slug].id, author_id=admin.id, title=title, body_md=body, tickers=tick))
        db.commit()


def main(argv: list[str]) -> None:
    init_db()
    with SessionLocal() as db:
        print("Seeded:", seed_reference(db))
        if "--demo-users" in argv:
            seed_demo_users(db)
            print("Demo users: admin@irai-demo.com / essential@irai-demo.com / free@irai-demo.com, password irai-demo-2026")


if __name__ == "__main__":
    main(sys.argv[1:])
