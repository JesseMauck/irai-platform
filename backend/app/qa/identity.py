"""Ephemeral synthetic trader identities.

Each run provisions fresh Pro users on the reserved `qa.irai.invalid` domain (mail can never be delivered),
tagged `preferences.synthetic_qa = true` with the run id, and deletes them (and with them every paper account,
bot and trade, via ON DELETE CASCADE) when the run ends. Orphans from crashed runs are swept at the next start.
Nothing is billed: no Subscription row is created and no payment provider is called.
"""
from __future__ import annotations

import datetime as dt
import secrets

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import User
from ..security import create_token, hash_password
from .config import SYNTHETIC_DOMAIN

ORPHAN_AFTER = dt.timedelta(hours=1)


def is_synthetic_email(email: str | None) -> bool:
    return bool(email) and email.lower().endswith("@" + SYNTHETIC_DOMAIN)


def provision(db: Session, run_id: int, cohort: str, plan: str = "pro") -> tuple[User, str]:
    tag = secrets.token_hex(4)
    u = User(email=f"qa-{run_id}-{cohort[:12]}-{tag}@{SYNTHETIC_DOMAIN}", handle=f"qa_{run_id}_{tag}"[:40],
             display_name=f"Synthetic QA {cohort}"[:80], password_hash=hash_password(secrets.token_urlsafe(32)), plan=plan,
             preferences={"synthetic_qa": True, "qa_run_id": run_id, "qa_cohort": cohort})
    db.add(u)
    db.commit()
    return u, create_token(u)


def cleanup_run(db: Session, run_id: int) -> int:
    ids = [u.id for u in db.scalars(select(User).where(User.email.like(f"qa-{run_id}-%@{SYNTHETIC_DOMAIN}")))]
    return _delete(db, ids)


def sweep_orphans(db: Session) -> int:
    cutoff = dt.datetime.now(dt.timezone.utc) - ORPHAN_AFTER
    ids = [u.id for u in db.scalars(select(User).where(User.email.like(f"%@{SYNTHETIC_DOMAIN}"), User.created_at < cutoff))]
    return _delete(db, ids)


def _delete(db: Session, ids: list[int]) -> int:
    if not ids:
        return 0
    # ORM delete so User relationships cascade; tables without an ORM relationship cascade in the database.
    for u in db.scalars(select(User).where(User.id.in_(ids))):
        db.delete(u)
    db.commit()
    db.execute(delete(User).where(User.id.in_(ids)))  # belt and braces for rows the ORM didn't load
    db.commit()
    return len(ids)
