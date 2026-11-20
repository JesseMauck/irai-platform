# IRAI — Irradiance research platform + ValueBot

Subscription research site for irradiance.ai: live ADR / ETF / Fundamental-RV monitors, a ticker page for
**any symbol you type**, research articles, community with price-captured trade posts, leaderboards,
Free / Essential / Pro membership — with **ValueBot** (narrative-and-numbers DCF engine) and the
**Strategy Lab** (StockSharp-model backtesting and optimisation) built in.

Production layout: **Vercel** (frontend/) · **Railway** (backend API + worker) · **Supabase** (PostgreSQL).

```
frontend/   Next.js 15 (App Router) · TypeScript · Tailwind v4        → http://localhost:3000
backend/    FastAPI · SQLAlchemy 2 · SQLite (dev) / PostgreSQL (prod) → http://localhost:8000/docs
  app/          platform: auth, plans, market data, monitors, research, community, alerts, billing
  app/market/   source.py (Yahoo live / Demo) · service.py (cache + fallbacks) · engines.py (ADR, ETF, RV)
  app/seed_data/*.json   plans, ticker bar, ADR pairs, ETFs, peer groups, articles, glossary, FAQ
  valuebot/     the ValueBot engine (mounted at /api/valuebot)
  schema.sql    PostgreSQL schema (21 tables) — the app also creates tables on startup
e2e/        Playwright browser test
```

## Quick start

```bash
# 1. backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # set IRAI_JWT_SECRET, SEC_USER_AGENT; ANTHROPIC_API_KEY optional
python -m app.seed --demo-users      # tables + reference data + 3 local accounts
uvicorn app.main:app --reload --port 8000

# 2. frontend (new terminal)
cd frontend
npm install
npm run dev                          # http://localhost:3000
```

Demo logins (local only): `admin@irai-demo.com` (Pro), `essential@irai-demo.com`, `free@irai-demo.com` — password `irai-demo-2026`.

Everything in Docker (Postgres + API + web): `cp backend/.env.example backend/.env && docker compose up --build`.

## Live data — type any ticker

Press **⌘K / Ctrl+K** anywhere (or the search box), type a symbol or company name, hit Enter.
`/ticker/<SYMBOL>` loads the live quote, 1M–5Y chart, key statistics, company profile and — if the name is in a
covered peer group — its Relative Value grade with peers. Works for stocks (`AAPL`, `7203.T`, `BP.L`, `0005.HK`),
ETFs (`SPY`), indices (`^GSPC`), FX (`EURUSD=X`) and crypto (`BTC-USD`). "Value with ValueBot" runs a full DCF.

| Source label | Meaning |
|---|---|
| `LIVE` | fetched from Yahoo Finance just now (US usually real-time; many non-US exchanges 15–20 min delayed) |
| `PROXY` | ADR whose local market is closed: fair value = last local close at live FX |
| `STALE` | feed failed; last price stored in the `quotes` table |
| `DEMO` | synthetic fallback (no network, or `IRAI_MARKET_MODE=demo`) |

Quotes are cached ~30 s in memory and persisted per symbol; fundamentals ~6 h. The ticker bar refreshes every
30 s, monitors every 60 s. To move to a licensed vendor (Polygon, Refinitiv, IEX…), implement the three methods
of `MarketSource` in `app/market/source.py` and call `service.set_source(...)` — nothing else changes.

**Coverage is data, not code:** add ADR pairs, ETFs, peer groups or ticker-bar items to `app/seed_data/*.json`
and re-run `python -m app.seed` (idempotent). Verify ADR ratios against the depositary bank — they change after splits.

## The engines

* **ADR Monitor** — premium = ADR ÷ (local × ratio × FX) − 1 (pence/cents handled); basis = trailing median
  premium; z vs the pair's own history; AR(1) half-life; confidence; rejection reasons (costs, |z|<2, borrow,
  market closed, stale).
* **ETF Monitor** — price vs issuer NAV (prior close), expense ratio, AUM, flags ≥ 0.5%.
* **Fundamental RV** — per peer group: quality = z(ROE) + z(op. margin) − z(leverage); regress log(EV/EBITDA or
  P/E) on quality; residual percentile → A+…F. Every computed grade is written to `grade_snapshots`
  (point-in-time, never restated).
* **ValueBot** — 18-stage pipeline (SEC XBRL + Yahoo → R&D/lease adjustments → bottom-up beta, ERP, synthetic
  rating → story→drivers → FCFF / excess-return / DDM → story tests → sensitivity, break-evens, Monte Carlo,
  reverse DCF → Excel with live formulas + bull/bear/market-implied → report HTML/PDF). Without
  `ANTHROPIC_API_KEY` the narrative uses templates; with it, Claude drafts theses, researches and writes.

## Strategy Lab (StockSharp integration)

`backend/app/algo/` ports the model of [JesseMauck/stocksharp-algo-trade-platform](https://github.com/JesseMauck/stocksharp-algo-trade-platform)
(StockSharp, Apache-2.0; see `app/algo/NOTICE-StockSharp.txt`): S# indicators (SMA, EMA, SMMA, RSI, Bollinger, MACD,
Highest/Lowest), candle-driven strategies with Position/Volume semantics (the SMA crossover reproduces the S#
`SmaStrategy` sample, including reversals), a history emulator (next-bar fills, commission, slippage), the
StatisticManager metrics, and a grid optimiser (S# BatchEmulation) with an out-of-sample check. `/lab` runs it on
live daily history for any ticker. The original repo is a 2019 .NET Framework 4.x/WPF codebase that won't build on
Linux; the modern cross-platform StockSharp (.NET 8, NuGet) can later run as a sidecar behind the same
`/api/lab` contract if tick-level emulation or broker connectors are needed. No order routing: research only.

## Operations

* **Migrations:** `cd backend && alembic upgrade head` (the Docker image runs it on start). New change:
  edit `app/models.py`, then `alembic revision --autogenerate -m "..."`, review, commit.
* **Worker:** one process: `python -m app.jobs worker` (alerts, saved-screen alerts, email outbox).
* **Email:** set `SMTP_*` (Resend, Postmark, SendGrid…). Without it, mail is logged.
* **Admin:** `/admin` for users with `is_admin` — metrics, plans, articles, coverage, moderation log.
* **API:** Pro members create read-only keys on /account; send `X-API-Key` on GET requests.
* **CI:** `.github/workflows/ci.yml` runs backend tests on SQLite and Postgres, a migration drift check,
  and frontend typecheck/lint/build.

## Plans (enforced server-side)

| | Free | Essential $49 | Pro $100 |
|---|---|---|---|
| Articles | 3 / month | unlimited | unlimited |
| Monitors | top 5 rows | full | full |
| ValueBot runs | 1 / month | 10 / month | unlimited |
| Screeners | 2 presets | all | all + CSV |
| Watchlists | 1 × 10 | 10 × 100 | unlimited |
| Alerts | — | 20 email | 100 email/webhook |
| Post / trade / vote | — | ✓ | ✓ + Pro room |

Limits live in `app/seed_data/plans.json`.

**Billing (Square).** Every member gets one in-app 7-day trial of Essential or Pro (no card; reminder email two
days before it ends; the worker downgrades expired trials). Paid plans use Square subscriptions:
1. Square Developer Dashboard → create an application → copy the access token (sandbox first).
2. `SQUARE_ACCESS_TOKEN=... python -m app.payments.setup_square --locations` → set `SQUARE_LOCATION_ID`.
3. `python -m app.payments.setup_square` → creates the plan + 4 variations; set the printed `SQUARE_PLAN_*`.
4. Add a webhook subscription for `subscription.created` and `subscription.updated` pointing at
   `https://api.irradiance.ai/api/billing/webhook/square`; set `SQUARE_WEBHOOK_SIGNATURE_KEY` and `SQUARE_WEBHOOK_URL`.
Checkout opens a Square-hosted page; access is granted only when Square's signed webhook confirms the subscription.
Members cancel from /account (access continues to the end of the paid period). Without `SQUARE_ACCESS_TOKEN`,
checkout activates plans directly so the product can be tested locally.

## Database (27 tables, Alembic-managed)

`users · subscriptions · api_keys · password_resets · email_outbox · saved_screens · backtest_runs · moderation_log · instruments · adr_pairs · etf_funds · peer_groups · peer_members · grade_snapshots ·
quotes · articles · article_views · watchlists · watchlist_items · alerts · alert_events · communities · threads
· posts · votes · trade_posts · valuation_runs`. See `backend/app/models.py` / `backend/schema.sql`.
Trade posts store the entry price captured from the feed at publish time; there is no edit route.

## Scheduled jobs

`python -m app.jobs alerts` — evaluates all active alerts against live data (run every minute via cron, a
Render/Fly cron, or a GitHub Action). Webhook alerts POST JSON to the user's URL.

## Tests

```bash
cd backend && pytest                       # 77 tests: platform API, market engines, Strategy Lab, ValueBot (incl. Excel parity)
IRAI_TEST_DATABASE_URL=postgresql://user@localhost/irai_test pytest   # same suite on Postgres
cd frontend && npx tsc --noEmit && npm run lint && npm run build
python e2e/test_e2e.py http://localhost:3000 e2e-screenshots   # browser flow (needs both servers; pip install playwright)
```

Tests run on demo data with no network. `tests/test_market.py` exercises the Yahoo source against mocked
HTTP responses, the STALE/DEMO fallbacks, and the ADR maths (GBp conversion, ratio 0.5, z, PROXY).

## Before going live

* Set a strong `IRAI_JWT_SECRET`, real `SEC_USER_AGENT`, Postgres `DATABASE_URL`, Stripe keys.
* Yahoo Finance's public endpoints are unofficial and for personal use — for a paid product, license a market
  data feed and plug it in as a `MarketSource`. Exchange display rules apply to real-time data.
* Have counsel review `/legal/*` (drafts) and the "not investment advice" positioning for your jurisdiction.
* Add Alembic migrations once the schema stabilises (`alembic init`, autogenerate from `app.models`).
