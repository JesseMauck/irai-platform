# QA fixer instructions (for Claude Code)

You are fixing issues that IRAI's synthetic-trader QA agent found and its validator confirmed. The queue is
`qa-queue.md` at the repo root (copied from the open `qa-fix-queue` issue, which the qa service keeps current). Read `CLAUDE.md` first; its
conventions bind you.

## For each issue, most severe first (stop after 3 fixes per run)

1. **Re-verify before touching code.** The validator can be wrong. Read the code at the likely location and
   the trace. If the platform is actually behaving correctly under its own rules (market closed, symbol rules,
   plan limits, demo-mode labels, upstream rate limits), do not change code: list the fingerprint under
   "Rejected" in the PR body with a one-line reason.
2. **Write the failing test first.** Add a regression test in `backend/tests/` that reproduces this exact
   ticker and scenario (use the suggested test as a starting point, offline on demo data as the suite
   requires). Run it and confirm it fails for the reported reason.
3. **Fix the smallest thing that makes it pass.** Never weaken risk controls (position caps, stop-loss,
   take-profit, auto-close, plan limits, auth, rate limits), never present DEMO/STALE data as live, never add
   buy/sell language, and never edit `app/qa/` to make a finding go away unless the finding is a bug in the
   QA agent itself (`qa_flow_crash`).
4. **Run the whole suite**: `cd backend && pytest -q`. It must be green.

## Then open one pull request

- Branch: `qa-fix/<yyyy-mm-dd>`. Title: `QA fixes: <short summary>`.
- Body: one section per fixed issue (what was wrong, the fix, the regression test), then a "Rejected" section.
- End the body with one line per fixed issue, exactly: `QA-Fixes: <fingerprint>`. After merge, the qa service
  marks those issues fixed on its next cycle; if they reappear, the agent reopens them as `regressed`.
- Do not merge. A human reviews every QA fix.

If the queue says nothing is validated and unfixed, do nothing and open no PR.
