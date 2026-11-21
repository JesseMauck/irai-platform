# IRAI — notes for Claude Code

Monorepo: `frontend/` (Next.js 15 App Router, TypeScript, Tailwind v4) and `backend/` (FastAPI, SQLAlchemy 2, ValueBot).

## Commands
- Backend: `cd backend && uvicorn app.main:app --reload --port 8000` · seed: `python -m app.seed --demo-users`
- Backend tests: `cd backend && pytest` (must stay green; runs offline on demo data)
- Frontend: `cd frontend && npm run dev` · checks: `npx tsc --noEmit && npm run lint && npm run build`
- Browser e2e: `python e2e/test_e2e.py http://localhost:3000 /tmp/shots` (both servers running)
- No network? `IRAI_MARKET_MODE=demo` (also turns ValueBot offline).

## Conventions
- Browser calls same-origin `/api/*`; `next.config.ts` rewrites to `BACKEND_URL`. Use `api()` / `useApi()` from `src/lib`.
- All market data goes through `app/market/service.py` (cache + LIVE/STALE/DEMO fallbacks). Never call Yahoo directly from routers.
- Every number shown to users carries its `source` badge. Never present DEMO or STALE data as live.
- Plan limits come from `app/seed_data/plans.json` via `security.limits(user)`; enforce on the server, not just the UI.
- Coverage (ADR pairs, ETFs, peers, ticker bar, articles) is JSON in `app/seed_data/`; seeding is idempotent.
- ValueBot routes are ValueBot's own `valuebot/api.py` router mounted at `/api/valuebot`; the platform overrides
  only `POST/GET /jobs` (auth + quota + DB record) in `app/routers/valuebot.py`. Keep the Excel parity tests passing.
- Trade posts are immutable after publish (entry price captured server-side). Don't add an edit route.
- Theme tokens are in `src/app/globals.css` (`bg`, `card`, `line`, `muted`, `primary`, `up`, `down`, `solar-*`).
- Copy is research/education only — no "buy/sell" language, no personalized advice.
- Synthetic-trader QA (`backend/app/qa/`, see its README): synthetic users live on `@qa.irai.invalid` and are excluded
  from business metrics; never let QA findings change risk controls. Fixes for QA issues follow `backend/app/qa/FIXER.md`
  and end the PR body with `QA-Fixes: <fingerprint>` lines.
