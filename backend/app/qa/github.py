"""GitHub bridge, driven from the qa service (which already has database access), so GitHub never needs it.

  publish_queue  keeps one open issue labelled `qa-fix-queue` whose body is the validated fix queue; the
                 fixer workflow reads that issue. Refuses to publish to a public repository: an open list of
                 unfixed defects is a disclosure risk.
  sync_fixed     scans recently merged PRs for `QA-Fixes: <fingerprint>` lines and marks those issues fixed.

Settings: IRAI_QA_GITHUB_TOKEN (fine-grained, this repo only: Issues read/write, Pull requests read) and
IRAI_QA_GITHUB_REPO (owner/name). Both unset = bridge off.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import QaIssue
from . import triage

log = logging.getLogger("irai.qa.github")
API = "https://api.github.com"
LABEL = "qa-fix-queue"
TITLE = "QA fix queue (synthetic trader)"
FIXES = re.compile(r"^QA-Fixes:\s*([0-9a-f]{8,40})\s*$", re.M)


class GitHubError(RuntimeError):
    pass


def configured() -> tuple[str, str] | None:
    tok, repo = os.environ.get("IRAI_QA_GITHUB_TOKEN", "").strip(), os.environ.get("IRAI_QA_GITHUB_REPO", "").strip()
    return (tok, repo) if tok and repo else None


def _client(token: str, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(base_url=API, timeout=20, transport=transport,
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "irai-qa"})


def _ok(r: httpx.Response) -> Any:
    if r.status_code >= 300:
        raise GitHubError(f"GitHub {r.request.method} {r.request.url.path} -> {r.status_code}: {r.text[:200]}")
    return r.json() if r.content else None


def publish_queue(db: Session, gh: httpx.Client, repo: str) -> dict[str, Any]:
    meta = _ok(gh.get(f"/repos/{repo}"))
    if not meta.get("private"):
        return {"published": False, "reason": "repository is public; make it private before publishing the fix queue"}
    rows = triage.fix_queue(db)
    body = triage.queue_markdown(rows)[:60000]
    existing = _ok(gh.get(f"/repos/{repo}/issues", params={"labels": LABEL, "state": "open", "per_page": 5}))
    issue = next((i for i in existing if "pull_request" not in i), None)
    if not rows:
        if issue:  # nothing left to fix: close the queue issue
            _ok(gh.patch(f"/repos/{repo}/issues/{issue['number']}", json={"body": body, "state": "closed"}))
            return {"published": True, "issue": issue["number"], "items": 0, "closed": True}
        return {"published": False, "reason": "queue empty"}
    if issue:
        if (issue.get("body") or "").strip() != body.strip():
            _ok(gh.patch(f"/repos/{repo}/issues/{issue['number']}", json={"body": body}))
        return {"published": True, "issue": issue["number"], "items": len(rows)}
    made = _ok(gh.post(f"/repos/{repo}/issues", json={"title": TITLE, "body": body, "labels": [LABEL]}))
    return {"published": True, "issue": made["number"], "items": len(rows), "created": True}


def sync_fixed(db: Session, gh: httpx.Client, repo: str) -> dict[str, Any]:
    pulls = _ok(gh.get(f"/repos/{repo}/pulls", params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": 30}))
    marked = []
    for pr in pulls:
        if not pr.get("merged_at"):
            continue
        for fp in FIXES.findall(pr.get("body") or ""):
            row = db.scalar(select(QaIssue).where(QaIssue.fingerprint.startswith(fp)))
            if row and row.status not in ("fixed", "regressed", "wontfix") and row.fix_ref != pr["html_url"]:
                row.status, row.fix_ref = "fixed", pr["html_url"][:300]
                marked.append(row.fingerprint)
    db.commit()
    return {"marked_fixed": marked}


def sync(db: Session, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    cfg = configured()
    if not cfg:
        return {"enabled": False}
    token, repo = cfg
    try:
        with _client(token, transport) as gh:
            return {"enabled": True, **sync_fixed(db, gh, repo), **publish_queue(db, gh, repo)}
    except (GitHubError, httpx.HTTPError) as e:  # GitHub trouble must never fail a QA cycle
        log.warning("qa github sync failed: %s", e)
        return {"enabled": True, "error": str(e)[:300]}
