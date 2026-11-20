"""Transactional email via an outbox table.

`enqueue()` only writes a row inside the caller's transaction, so a request never blocks on SMTP and an
email is never sent for a change that rolled back. `deliver_pending()` (run by the worker) sends due rows,
retrying with exponential backoff up to MAX_ATTEMPTS. Without SMTP_HOST, mail is printed to the log
(development) and marked sent.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import smtplib
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import EmailOutbox

log = logging.getLogger("irai.mail")
MAX_ATTEMPTS = 5


def enqueue(db: Session, to: str, subject: str, body: str, kind: str) -> EmailOutbox:
    row = EmailOutbox(to_addr=to, subject=subject[:200], body_text=body, kind=kind)
    db.add(row)
    return row


def _send_smtp(row: EmailOutbox) -> None:
    msg = EmailMessage()
    msg["Subject"], msg["To"] = row.subject, row.to_addr
    msg["From"] = os.environ.get("SMTP_FROM", "Irradiance <no-reply@irradiance.ai>")
    msg.set_content(row.body_text)
    host, port = os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=20) as s:
        s.starttls()
        if os.environ.get("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
        s.send_message(msg)


def deliver_pending(db: Session, sender=None, limit: int = 100) -> dict[str, int]:
    now = dt.datetime.now(dt.timezone.utc)
    sender = sender or (_send_smtp if os.environ.get("SMTP_HOST") else
                        (lambda r: log.info("MAIL to=%s subject=%r\n%s", r.to_addr, r.subject, r.body_text)))
    rows = db.scalars(select(EmailOutbox).where(EmailOutbox.status == "pending", EmailOutbox.next_attempt_at <= now)
                      .order_by(EmailOutbox.id).limit(limit).with_for_update(skip_locked=True)).all()
    sent = failed = 0
    for r in rows:
        r.attempts += 1
        try:
            sender(r)
            r.status, r.sent_at, r.last_error = "sent", now, None
            sent += 1
        except Exception as e:  # noqa: BLE001
            r.last_error = f"{type(e).__name__}: {e}"[:300]
            if r.attempts >= MAX_ATTEMPTS:
                r.status = "failed"
                failed += 1
            else:
                r.next_attempt_at = now + dt.timedelta(minutes=2 ** r.attempts)
            log.warning("mail %s attempt %s failed: %s", r.id, r.attempts, r.last_error)
    db.commit()
    return {"sent": sent, "failed": failed, "considered": len(rows)}


def link(path: str) -> str:
    return settings.public_url.rstrip("/") + path


FOOTER = "\n\n—\nIrradiance · Illuminating the market research.\nResearch and education only. Not investment advice."
