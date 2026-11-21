"""Validation gate between the synthetic trader and any code change.

1. Rules (free, deterministic): legitimate rejections and one-off blips are settled without an LLM call.
2. Claude: each remaining issue is cross-checked against the platform's business rules and the evidence,
   with a tool call returning a structured verdict (valuebot.llm.toolcall handles models that reject a forced tool_choice). Bounded per run (IRAI_QA_TRIAGE_MAX).

Verdicts: valid (a real defect or UX/latency bottleneck worth fixing), false_positive (the platform behaved
correctly), needs_more_data (can't tell yet; re-triaged once it recurs). Only `valid` issues reach the fix queue.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import QaIssue
from .config import QaSettings, load

log = logging.getLogger("irai.qa.triage")

BUSINESS_RULES = """IRAI platform rules the synthetic trader runs against (from the codebase):
- AlgoTrader is paper trading only: simulated money, nothing reaches a broker. Long-only; no margin; sells are capped at
  shares held, buys at the sleeve's cash.
- Fills use the latest market price plus 2 bps slippage and 1 bp commission per side. Outside US regular hours
  (Mon-Fri 09:30-16:00 ET; exchange holidays are not modelled) fills use the last price and the signal notes "market closed".
- Each bot owns a sleeve of capital in each paper account it is funded from. Per-symbol budget =
  sleeve equity x min(1/number_of_symbols, max_position_pct). Rebalance band 5%. Stop-loss / take-profit / daily
  auto-close are enforced on every pass.
- Webhook actions: buy/long/enter, sell/exit/close/flat. Signals for symbols outside the bot's list, or to a paused bot,
  are ignored (HTTP 200, status "ignored"). Missing ticker/action -> 422. Unknown token -> 404. Owner below Pro -> 402.
- Market data goes through a cached service with labels: LIVE (feed), PROXY (ADR with local market closed), EOD,
  STALE (last stored value), DEMO (synthetic, only if every source fails; never to be presented as live). With
  IRAI_MARKET_MODE=demo the whole platform intentionally serves DEMO data. Yahoo Finance is an unofficial source and
  rate-limits; brief STALE fallbacks and cooldowns are expected behavior, not defects.
- Symbols must match ^[A-Za-z0-9^=.-]{1,20}$; bad symbols must be a 4xx, never a 5xx. Every 5xx is a defect.
- Copy is research/education only (no buy/sell advice). Plan limits are enforced server-side.
Relevant code: app/paper.py (engine, fills, risk), app/routers/bots.py (AlgoTrader API, webhooks),
app/market/service.py (quotes, labels, fallbacks), app/routers/market.py, app/routers/insight.py, app/quant/profile.py."""

SYSTEM = (
    "You are the validation gate for an automated QA agent on a paper-trading research platform. A synthetic trader "
    "reported the issue below. Decide whether it is a real defect (or a genuine UX/latency bottleneck worth engineering "
    "time) or a false positive where the platform behaved correctly under its own rules. Be skeptical: legitimate "
    "rejections (market closed, tick-size or symbol rules, plan limits, unknown symbols returning 4xx, demo-mode labels, "
    "transient upstream rate limits) are false positives. If the evidence can't settle it, say needs_more_data and name "
    "what would settle it. Never propose changes that weaken risk controls or present DEMO/STALE data as live.\n\n" + BUSINESS_RULES)

VERDICT_TOOL = {
    "name": "record_verdict",
    "description": "Record the triage verdict for this QA issue.",
    "input_schema": {"type": "object", "properties": {
        "verdict": {"type": "string", "enum": ["valid", "false_positive", "needs_more_data"]},
        "category": {"type": "string", "enum": ["bug", "trading_logic", "data", "latency", "ux"]},
        "severity": {"type": "string", "enum": ["high", "medium", "low"]},
        "rationale": {"type": "string", "description": "Two to four sentences citing the evidence and the rule it violates or satisfies."},
        "likely_location": {"type": "string", "description": "Most likely file(s)/function(s) to change, or empty."},
        "fix_hint": {"type": "string", "description": "What a correct fix would do, without weakening safeguards. Empty unless valid."},
        "regression_test": {"type": "string", "description": "A pytest sketch reproducing this exact ticker/scenario. Empty unless valid."},
    }, "required": ["verdict", "category", "severity", "rationale"]},
}

# (issue_type, predicate on the issue) -> false positive reason
LEGIT_PATTERNS = [
    (re.compile(r"market (is )?closed", re.I), "rejected because the market is closed, which is the documented behavior"),
    (re.compile(r"needs the \w+ plan", re.I), "plan gate (402) working as designed"),
    (re.compile(r"cooling down|rate.?limit", re.I), "upstream rate limit / cooldown; the service is expected to fall back"),
    (re.compile(r"no live price .*only demo data", re.I), "paper trading correctly refused a DEMO-only price while the live feed was down; "
     "the outage itself is tracked by demo_data_in_live_mode"),
]


def _set(issue: QaIssue, status: str, verdict: dict[str, Any], by: str) -> None:
    issue.status = status
    issue.triage = {**verdict, "by": by, "at": dt.datetime.now(dt.timezone.utc).isoformat(), "occurrences_at_triage": issue.occurrences}
    if verdict.get("category") in {"bug", "trading_logic", "data", "latency", "ux"}:
        issue.category = verdict["category"]
    if verdict.get("severity") in {"high", "medium", "low"}:
        issue.severity = verdict["severity"]


def rules(issue: QaIssue, s: QaSettings) -> dict[str, Any] | None:
    """Return a verdict without an LLM when the answer is mechanical, else None."""
    ctx = issue.context or {}
    text = f"{issue.actual} {(issue.trace or {}).get('response') or ''}"
    for rx, why in LEGIT_PATTERNS:
        if rx.search(text) and issue.issue_type in ("rejected_valid_request", "slow_response"):
            return {"verdict": "false_positive", "rationale": why}
    if issue.issue_type in ("demo_data_in_live_mode", "fill_on_demo_price") and not ctx.get("live_market_data"):
        return {"verdict": "false_positive", "rationale": "target runs in demo market mode, where DEMO labels are intended"}
    if issue.issue_type == "qa_flow_crash":
        return {"verdict": "valid", "category": "bug", "severity": "low", "rationale": "the QA agent itself crashed; fix the trader (app/qa/trader.py)",
                "likely_location": "app/qa/trader.py"}
    one_off = issue.category == "latency" or issue.severity == "low"
    if one_off and issue.occurrences < s.triage_min_occurrences:
        return {"verdict": "needs_more_data", "rationale": f"seen {issue.occurrences}x; waiting for {s.triage_min_occurrences} occurrences before triage"}
    return None


def _claude(issue: QaIssue, s: QaSettings) -> dict[str, Any] | None:
    from valuebot.config import settings as vb

    if not vb.llm_enabled:
        return None
    import anthropic

    evidence = {k: getattr(issue, k) for k in ("issue_type", "category", "severity", "flow", "endpoint", "strategy", "step", "title",
                                              "expected", "actual", "tickers", "occurrences", "context")}
    evidence["first_seen"], evidence["last_seen"] = str(issue.first_seen), str(issue.last_seen)
    evidence["trace"] = issue.trace
    from valuebot.llm.toolcall import call_tool

    return call_tool(anthropic.Anthropic(api_key=vb.anthropic_api_key), model=s.triage_model or vb.model, max_tokens=s.triage_max_tokens,
                     system=SYSTEM, tool=VERDICT_TOOL,
                     messages=[{"role": "user", "content": "Issue reported by the synthetic trader:\n" + json.dumps(evidence, default=str, indent=1)[:12000]}])


def triage(db: Session, settings: QaSettings | None = None, llm=None) -> dict[str, int]:
    """Triage new/regressed issues and needs_more_data issues that have recurred since. `llm` is injectable for tests."""
    s = settings or load()
    llm = llm or _claude
    rank = {"high": 0, "medium": 1, "low": 2}
    pending = sorted(db.scalars(select(QaIssue).where(or_(QaIssue.status.in_(["new", "regressed"]), QaIssue.status == "needs_more_data"))).all(),
                     key=lambda i: (rank.get(i.severity, 3), -i.occurrences))  # most severe first, so the LLM budget goes there
    out = {"rules": 0, "claude": 0, "skipped": 0, "valid": 0}
    budget = s.triage_max
    for issue in pending:
        if issue.status == "needs_more_data" and issue.occurrences <= int((issue.triage or {}).get("occurrences_at_triage") or 0):
            continue  # nothing new since the last look
        v = rules(issue, s)
        by = "rules"
        if v is None:
            if budget <= 0:
                out["skipped"] += 1
                continue
            budget -= 1
            try:
                v = llm(issue, s)
            except Exception as e:  # noqa: BLE001  (an API outage leaves the issue for the next run)
                log.warning("triage of issue %s failed: %s", issue.id, e)
                v = None
            if v is None:
                out["skipped"] += 1
                continue
            by = "claude"
        status = {"valid": "valid", "false_positive": "false_positive"}.get(v.get("verdict"), "needs_more_data")
        _set(issue, status, v, by)
        out[by] += 1
        out["valid"] += status == "valid"
    db.commit()
    return out


# ── fix queue ────────────────────────────────────────────────────────────────────────────────────
def fix_queue(db: Session, limit: int = 20) -> list[QaIssue]:
    sev = {"high": 0, "medium": 1, "low": 2}
    rows = db.scalars(select(QaIssue).where(QaIssue.status.in_(["valid", "regressed"]))).all()
    rows = [r for r in rows if r.status == "valid" or (r.triage or {}).get("verdict") == "valid"]
    return sorted(rows, key=lambda r: (sev.get(r.severity, 3), -r.occurrences))[:limit]


def queue_markdown(rows: list[QaIssue]) -> str:
    if not rows:
        return "# IRAI QA fix queue\n\nNothing validated and unfixed. 🎉\n"
    out = ["# IRAI QA fix queue", "", f"{len(rows)} validated issue(s), most severe first. Follow app/qa/FIXER.md.", ""]
    for r in rows:
        t = r.triage or {}
        out += [f"## [{r.severity}] {r.title}", "",
                f"- **fingerprint**: `{r.fingerprint}` · **status**: {r.status} · **category**: {r.category} · **seen** {r.occurrences}x "
                f"(first {r.first_seen:%Y-%m-%d}, last {r.last_seen:%Y-%m-%d %H:%M} UTC)",
                f"- **flow**: {r.flow} / step `{r.step}` · strategy {r.strategy or '-'} · endpoint `{r.endpoint}`",
                f"- **tickers**: {', '.join((r.tickers or [])[-8:]) or '-'}",
                f"- **expected**: {r.expected}", f"- **actual**: {r.actual}",
                f"- **triage** ({t.get('by', '?')}): {t.get('rationale', '')}"]
        if t.get("likely_location"):
            out.append(f"- **likely location**: {t['likely_location']}")
        if t.get("fix_hint"):
            out.append(f"- **fix hint**: {t['fix_hint']}")
        if r.trace:
            out += ["", "<details><summary>trace</summary>", "", "```json", json.dumps(r.trace, indent=1, default=str)[:3000], "```", "</details>"]
        if t.get("regression_test"):
            out += ["", "Suggested regression test:", "", "```python", t["regression_test"], "```"]
        out.append("")
    return "\n".join(out)
