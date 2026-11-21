# Synthetic-trader QA agent

An always-on background agent that keeps trading random tickers on AlgoTrader (paper money only), files
structured, deduplicated findings, has Claude validate them, and feeds a fix queue that Claude Code works
through in reviewed pull requests.

```
 loop (always on) ──every 15 min──▶ cycle (fresh process, hard timeout)
                                     ├─ run: lease → sample tickers → synthetic trader → qa_issues (dedup) → cleanup
                                     └─ triage: rules → Claude verdict (bounded) → valid | false_positive | needs_more_data
 weekly GitHub Action ─▶ queue (valid, unfixed) ─▶ Claude Code: verify → failing test → fix → PR (human merges)
 PR merged with "QA-Fixes: <fp>" ─▶ issue marked fixed ─▶ if it reappears: "regressed"
```

## What a run does
1. Sweeps orphaned synthetic users, takes the run lease (one run at a time; stale leases are reclaimed).
2. Samples `IRAI_QA_BATCH` tickers: ~60% from coverage (least-recently tested first, via `qa_ticker_ledger`),
   ~25% edge cases (share classes, indices, FX, crypto, OTC ADRs, delisted, nonexistent, malformed),
   ~15% tickers attached to open issues (regression rechecks).
3. Provisions an ephemeral Pro user per cohort on `qa.irai.invalid` (never billed, mail undeliverable,
   excluded from Admin stats) and checks the target accepts it.
4. Runs one cohort per ticker: `market_probe`, `momentum_bot`, `reversion_bot`, `webhook_trader`,
   `risk_limits` (see `trader.py`). Assertions cover status discipline (never 5xx; 4xx for bad input),
   latency budgets, source labels and staleness, chart sanity, funding/equity/round-trip reconciliation,
   per-symbol caps, duplicate-signal stacking, partial sells, exits, paused bots and foreign symbols.
5. Writes findings (ticker, strategy, step, expected, actual, redacted request/response trace, context) into
   `qa_issues`, keyed by `hash(issue_type, flow, normalized endpoint, normalized error)`.
6. Heartbeats after every ticker, deletes its synthetic users, closes the run row.

Budgets: `IRAI_QA_MAX_REQUESTS` (400) and `IRAI_QA_MAX_SECONDS` (480) per run; `IRAI_QA_RUN_TIMEOUT` (900)
kills a hung process; `IRAI_QA_TRIAGE_MAX` (10) Claude verdicts per cycle at `IRAI_QA_TRIAGE_MAX_TOKENS` (1500).
429s are backpressure, never findings: short `Retry-After` is honored, a long one ends the run as `throttled`.
5xx/transport errors retry with exponential backoff; `IRAI_QA_ABORT_AFTER` (6) in a row aborts the run.
The loop backs off exponentially after failed cycles and emails admins once per failure streak.

## Commands
```bash
python -m app.qa run [--seed N] [--cohort NAME]   # one batch
python -m app.qa triage                            # validate new issues
python -m app.qa cycle                             # run + triage
python -m app.qa loop                              # always-on
python -m app.qa status                            # runs, heartbeat, open issues
python -m app.qa queue --out qa-queue.md           # fixer input
python -m app.qa mark <fingerprint> fixed --ref <PR url>
```
Admin API: `GET /api/admin/qa/status`, `GET /api/admin/qa/issues?status=valid`, `GET|PATCH /api/admin/qa/issues/{id}`.

## Where it runs (choose one)
| Option | Settings | Trade-off |
|---|---|---|
| **A. In-process, shared DB** (simplest) | Railway service `qa`, start `python -m app.qa loop`; `IRAI_QA_TARGET=inprocess`, same `DATABASE_URL`/`IRAI_JWT_SECRET` as `api`, `IRAI_QA_ENV=production`, `IRAI_QA_ALLOW_PRODUCTION=1` | Tests the deployed code with live data and puts no load on the API process. Synthetic users exist in the production DB for a few minutes per run (tagged, cleaned up, excluded from stats). Doesn't exercise the HTTP edge (Railway networking, CORS). |
| **B. Staging over HTTP** (cleanest) | Railway `staging` environment + Supabase branch; `IRAI_QA_TARGET=https://<staging api>`, `IRAI_QA_ENV=staging`, staging `DATABASE_URL`/`IRAI_JWT_SECRET` | Full black-box test with zero production footprint; costs a second environment. `QA_DATABASE_URL` for the GitHub workflows is then the staging DB. |

Without `IRAI_QA_ALLOW_PRODUCTION=1`, the agent refuses any production host or a Postgres DB not marked staging.
