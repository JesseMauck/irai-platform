"""Synthetic-trader QA: a background agent that keeps exercising the platform with random tickers.

Two loops, kept apart on purpose:

  orchestration  `python -m app.qa loop` — always on. Every IRAI_QA_INTERVAL seconds it starts a fresh
                 subprocess (`python -m app.qa cycle`) with a hard wall-clock timeout, records heartbeats,
                 backs off after failures and emails admins after repeated crashes.
  single runs    `python -m app.qa cycle` = `run` (one bounded batch of synthetic trading against the target
                 API, findings written to qa_issues) + `triage` (rules, then Claude validates new issues).

Durable state lives in Postgres (qa_runs, qa_issues, qa_ticker_ledger), never in an LLM context window.
Fixes happen elsewhere: `python -m app.qa queue` writes the validated fix queue that the fixer workflow
(.github/workflows/qa-fixer.yml + app/qa/FIXER.md) reads, and the fixer marks issues fixed with a PR link.

AlgoTrader is paper-only, so nothing here can reach a broker; the guardrails in config.py also keep the
trader off production unless explicitly allowed. See app/qa/README.md.
"""
