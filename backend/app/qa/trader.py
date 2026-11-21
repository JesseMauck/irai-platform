"""The synthetic trader: black-box flows against the target API with explicit QA assertions at every step.

Cohorts (one per picked ticker, chosen at random):
  market_probe     quote, chart, ticker page, quant profile: status, labels, staleness, data sanity, latency
  momentum_bot     strategy bot (SMA/EMA cross, Donchian, MACD) with stops: run twice, close, delete, reconcile
  reversion_bot    strategy bot (RSI, Bollinger) — same lifecycle
  webhook_trader   TradingView-style signals: buy, duplicate buy (caps), partial sell, exit, bad action,
                   symbol not allowed, paused bot, unknown token
  risk_limits      multi-symbol bot with a position cap; over-allocation, bad strategy, invalid symbols

Every account and bot is created under an ephemeral synthetic user and deleted at the end. Findings are
facts about what happened (expected vs actual + trace); deciding whether they are real defects is the
validator's job (triage.py), not the trader's.
"""
from __future__ import annotations

import logging
import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .client import Call, QaClient
from .config import QaSettings
from .findings import Finding
from .tickers import Pick

log = logging.getLogger("irai.qa.trader")
LABELS = {"LIVE", "PROXY", "EOD", "STALE", "DEMO"}
SLOW_PATHS = ("/profile", "/api/market/ticker/", "/api/bots")  # heavier endpoints get the slow latency budget
CAP_TOLERANCE = 1.05  # position may exceed its cap by slippage/commission rounding, not more
RECONCILE_TOL = 0.005  # account cash after a round trip must be within 0.5% of the capital allocated

STRATS = {"momentum_bot": ["sma_cross", "ema_cross", "donchian_breakout", "macd_cross"],
          "reversion_bot": ["rsi_reversion", "bollinger_reversion"]}
COHORTS = ["market_probe", "momentum_bot", "reversion_bot", "webhook_trader", "risk_limits"]


@dataclass
class Ctx:
    client: QaClient
    settings: QaSettings
    run_id: int
    identity: Callable[[str], str]  # cohort -> bearer token (provisioned lazily, one per cohort per run)
    live: bool  # target runs on live market data (DEMO labels are then a finding)
    rng: random.Random
    findings: list[Finding] = field(default_factory=list)
    checks: int = 0
    throttled: int = 0  # assertions skipped because the target rate-limited us

    def call(self, method: str, path: str, *, token: str | None = None, body: Any = None, params: dict | None = None) -> Call:
        return self.client.call(method, path, token=token, json_body=body, params=params)


class Flow:
    """Assertions for one (cohort, ticker) test. Each failed assertion becomes a Finding."""

    def __init__(self, ctx: Ctx, flow: str, pick: Pick, strategy: str | None = None):
        self.ctx, self.flow, self.pick, self.strategy = ctx, flow, pick, strategy
        self.market_open: bool | None = None
        self.failed = False

    def finding(self, issue_type: str, category: str, severity: str, step: str, call: Call | None, title: str,
                expected: str, actual: str, error: str = "") -> None:
        if call is not None and call.status == 429:  # backpressure is inconclusive, never a defect
            self.ctx.throttled += 1
            return
        self.failed = True
        self.ctx.findings.append(Finding(
            issue_type=issue_type, category=category, severity=severity, flow=self.flow,
            endpoint=f"{call.method} {call.path}" if call else self.flow, title=title, expected=expected, actual=actual,
            ticker=self.pick.symbol, strategy=self.strategy, step=step, error=error or _dedup_error(call),
            trace=call.trace() if call else None,
            context={"pick_kind": self.pick.kind, "edge_tag": self.pick.tag, "expect": self.pick.expect, "market_open": self.market_open,
                     "live_market_data": self.ctx.live, "env": self.ctx.settings.env}))

    def check(self, cond: bool, *args, **kw) -> bool:
        self.ctx.checks += 1
        if not cond:
            self.finding(*args, **kw)
        return cond

    def expect_ok(self, call: Call, step: str, allow: tuple[int, ...] = ()) -> bool:
        """Status discipline: never 5xx; 2xx for valid input; 4xx (not 5xx) for invalid input."""
        self.ctx.checks += 1
        self._latency(call, step)
        if call.status == 0 or call.status >= 500:
            self.finding("server_error", "bug", "high", step, call, f"{step}: server error on {self.pick.symbol}",
                         "a 2xx response, or a 4xx with a clear message for bad input",
                         f"HTTP {call.status or 'transport error'}: {_detail(call)}")
            return False
        carries = self._carries_symbol(call)
        if call.ok or call.status in allow:
            if call.ok and self.pick.expect == "reject" and carries:
                self.finding("accepted_invalid_input", "ux", "medium", step, call, f"{step}: invalid symbol {self.pick.symbol!r} accepted",
                             f"a 4xx rejecting the {self.pick.tag} symbol", f"HTTP {call.status}")
            return call.ok
        if self.pick.expect in ("reject", "any") and carries:
            return False  # a clean 4xx is correct here
        self.finding("rejected_valid_request", "bug", "medium", step, call, f"{step}: request for {self.pick.symbol} rejected",
                     "a 2xx response for a supported, well-formed symbol", f"HTTP {call.status}: {_detail(call)}")
        return False

    def _carries_symbol(self, call: Call) -> bool:
        """Only calls that send this ticker are judged by the ticker's edge-case expectation."""
        import json

        sym = self.pick.symbol
        return sym in call.path or sym.upper() in json.dumps(call.request or {}).upper()

    def _latency(self, call: Call, step: str) -> None:
        if call.status == 0:
            return
        budget = self.ctx.settings.latency_slow_ms if any(p in call.path for p in SLOW_PATHS) else self.ctx.settings.latency_ms
        if call.ms > budget:
            sev = "medium" if call.ms > budget * 3 else "low"
            self.finding("slow_response", "latency", sev, step, call, f"{step} took {call.ms:,.0f} ms",
                         f"under {budget:,} ms", f"{call.ms:,.0f} ms", error=f"slow {step}")


def _detail(call: Call | None) -> str:
    if not call:
        return ""
    if isinstance(call.body, dict) and "detail" in call.body:
        return str(call.body["detail"])[:300]
    return (call.error or call.text or "")[:300]


def _dedup_error(call: Call | None) -> str:
    """What makes two failures 'the same': the error message for failed calls; for assertion failures on a 2xx the
    issue type and step already say it (response bodies carry prices and names that would split one bug into many)."""
    if not call:
        return ""
    return f"{call.status} {_detail(call)}" if call.status >= 400 or call.status == 0 else str(call.status)


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


# ── cohort: market probe ─────────────────────────────────────────────────────────────────────────
def market_probe(ctx: Ctx, pick: Pick) -> Flow:
    f = Flow(ctx, "market_probe", pick)
    sym = pick.symbol
    q = ctx.call("GET", f"/api/market/quote/{sym}")
    if f.expect_ok(q, "quote") and isinstance(q.body, dict):
        b = q.body
        f.market_open = b.get("market_open")
        f.check(_finite(b.get("price")) and b["price"] > 0, "bad_quote_price", "data", "high", "quote", q,
                f"quote for {sym} has no usable price", "a finite price > 0", f"price={b.get('price')!r}")
        f.check(b.get("source") in LABELS, "missing_source_label", "data", "medium", "quote", q,
                f"quote for {sym} lacks a source label", f"source in {sorted(LABELS)}", f"source={b.get('source')!r}")
        if ctx.live:
            f.check(b.get("source") != "DEMO", "demo_data_in_live_mode", "data", "medium", "quote", q,
                    f"live quote for {sym} fell back to DEMO", "LIVE/EOD/STALE/PROXY data, or a 404 for unknown symbols",
                    f"DEMO price {b.get('price')} served for {pick.tag or 'a covered symbol'}", error=f"demo for {pick.tag or 'covered'}")
        _staleness(f, q, b)
    c = ctx.call("GET", f"/api/market/chart/{sym}", params={"range": "1y"})
    if f.expect_ok(c, "chart") and isinstance(c.body, dict):
        hist = c.body.get("history") or []
        dates = [h.get("date") for h in hist]
        closes = [h.get("close") for h in hist]
        f.check(len(hist) >= 20, "short_history", "data", "low", "chart", c, f"1y chart for {sym} has {len(hist)} bars",
                "at least 20 daily bars for a 1y range", f"{len(hist)} bars")
        f.check(all(a < b for a, b in zip(dates, dates[1:])), "history_not_monotonic", "data", "medium", "chart", c,
                f"chart dates for {sym} not strictly increasing", "strictly increasing, unique dates", "duplicate or out-of-order dates")
        bad = sum(1 for x in closes if not (_finite(x) and x > 0))
        f.check(bad == 0, "bad_history_values", "data", "medium", "chart", c, f"{bad} invalid closes in {sym} history",
                "every close finite and > 0", f"{bad} null/NaN/non-positive closes")
        if closes and _finite(closes[-1]) and isinstance(q.body, dict) and _finite(q.body.get("price")) and closes[-1] > 0:
            gap = abs(q.body["price"] / closes[-1] - 1)
            f.check(gap < 0.35, "quote_chart_mismatch", "data", "medium", "chart", c,
                    f"{sym} quote is {gap:.0%} away from its last chart close", "quote within 35% of the latest daily close",
                    f"quote {q.body['price']} vs last close {closes[-1]}", error="quote vs chart gap")
    t = ctx.call("GET", f"/api/market/ticker/{sym}")
    f.expect_ok(t, "ticker_page")
    p = ctx.call("GET", f"/api/insight/{sym}/profile")
    f.expect_ok(p, "quant_profile", allow=(404,))
    return f


def _staleness(f: Flow, call: Call, b: dict) -> None:
    import datetime as dt

    if b.get("source") != "LIVE" or not b.get("market_open") or not b.get("market_time"):
        return
    try:
        t = dt.datetime.fromisoformat(str(b["market_time"]).replace("Z", "+00:00"))
    except ValueError:
        return
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    age_min = (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 60 - float(b.get("delayed_minutes") or 0)
    f.check(age_min < 20, "stale_live_quote", "data", "medium", "quote", call, f"LIVE quote for {b.get('symbol')} is {age_min:.0f} min old",
            "a LIVE label only on quotes under ~20 minutes old (plus declared delay) while the market is open",
            f"market_time {b['market_time']}, {age_min:.0f} min old", error="stale live quote")


# ── shared paper-trading helpers ─────────────────────────────────────────────────────────────────
def _account(ctx: Ctx, f: Flow, tok: str) -> dict | None:
    cash = ctx.settings.starting_cash
    a = ctx.call("POST", "/api/paper/accounts", token=tok, body={"name": f"QA {f.flow}"[:80], "starting_cash": cash})
    if not f.expect_ok(a, "create_account", ) or not isinstance(a.body, dict):
        return None
    f.check(abs(a.body.get("cash", 0) - cash) < 0.01 and abs(a.body.get("equity", 0) - cash) < 0.01, "account_opening_mismatch",
            "trading_logic", "high", "create_account", a, "new paper account doesn't show its starting cash",
            f"cash == equity == {cash}", f"cash={a.body.get('cash')} equity={a.body.get('equity')}")
    return a.body


def _invariants(f: Flow, d: dict, call: Call, step: str, n_symbols: int, max_pct: float) -> None:
    """Accounting and risk invariants on a bot detail payload."""
    f.market_open = d.get("market_open", f.market_open)
    by_acct: dict[Any, float] = {}
    for p in d.get("positions") or []:
        by_acct[p.get("account_id")] = by_acct.get(p.get("account_id"), 0.0) + (p.get("value") or 0.0)
    for s in d.get("sleeves") or []:
        f.check((s.get("cash") or 0) >= -0.01, "negative_sleeve_cash", "trading_logic", "high", step, call,
                "a bot sleeve went below zero cash", "sleeve cash >= 0 (long-only, no margin)", f"cash={s.get('cash')}")
        eq, held = s.get("equity") or 0.0, by_acct.get(s.get("account_id"), 0.0)
        f.check(abs((s.get("cash") or 0) + held - eq) <= max(1.0, abs(eq) * 0.005), "equity_mismatch", "trading_logic", "medium", step, call,
                "sleeve equity != cash + position value", "equity == cash + sum(position values) (±0.5%)",
                f"equity={eq:.2f}, cash={s.get('cash'):.2f}, positions={held:.2f}")
        cap = max(s.get("capital") or 0.0, eq) * min(1.0 / max(1, n_symbols), max_pct)
        for p in (x for x in d.get("positions") or [] if x.get("account_id") == s.get("account_id")):
            f.check((p.get("value") or 0) <= cap * CAP_TOLERANCE + 1, "position_over_cap", "trading_logic", "high", step, call,
                    f"{p.get('symbol')} position exceeds its per-symbol cap", f"value <= {cap:,.2f} (min(1/n, max_position_pct) of sleeve)",
                    f"value {p.get('value'):,.2f}", error="position over cap")
    for t in d.get("trades") or []:
        ok = _finite(t.get("price")) and t["price"] > 0 and _finite(t.get("quantity")) and t["quantity"] > 0
        f.check(ok, "bad_fill", "trading_logic", "high", step, call, "a paper fill has a non-positive price or quantity",
                "price > 0 and quantity > 0 on every fill", f"{t.get('side')} {t.get('quantity')} @ {t.get('price')}")
        f.check(t.get("price_source") in LABELS | {None}, "fill_without_label", "data", "low", step, call,
                "a fill's price source isn't a known label", f"price_source in {sorted(LABELS)}", f"{t.get('price_source')!r}")
        if f.ctx.live:
            f.check(t.get("price_source") != "DEMO", "fill_on_demo_price", "trading_logic", "high", step, call,
                    "a paper trade filled at a DEMO (fictional) price in live mode", "fills only at LIVE/EOD/STALE/PROXY prices",
                    f"{t.get('side')} {t.get('symbol')} @ {t.get('price')} (DEMO)", error="fill on demo price")


def _teardown(ctx: Ctx, f: Flow, tok: str, bot_id: int | None, acct: dict, capital: float) -> None:
    if bot_id is not None:
        d = ctx.call("DELETE", f"/api/bots/{bot_id}", token=tok)
        f.expect_ok(d, "delete_bot")
    a = ctx.call("GET", f"/api/paper/accounts/{acct['id']}", token=tok)
    if f.expect_ok(a, "account_after") and isinstance(a.body, dict) and bot_id is not None:
        cash, start = a.body.get("cash") or 0.0, acct["starting_cash"]
        f.check(abs(cash - start) <= capital * RECONCILE_TOL + 1, "round_trip_reconciliation", "trading_logic", "high", "account_after", a,
                "account cash after deleting the bot doesn't reconcile", f"cash back to ~{start:,.2f} (±0.5% of {capital:,.0f} for costs)",
                f"cash {cash:,.2f} (diff {cash - start:+,.2f})", error="round trip reconciliation")
        f.check(not a.body.get("bots"), "orphan_sleeve", "trading_logic", "medium", "account_after", a, "deleted bot still listed on account",
                "no sleeves after the bot is deleted", f"{len(a.body.get('bots') or [])} sleeve(s)")
    ctx.call("DELETE", f"/api/paper/accounts/{acct['id']}", token=tok)


# ── cohorts: strategy bots ───────────────────────────────────────────────────────────────────────
def strategy_bot(ctx: Ctx, pick: Pick, flow: str) -> Flow:
    strategy = ctx.rng.choice(STRATS[flow])
    f = Flow(ctx, flow, pick, strategy)
    tok = ctx.identity(flow)
    acct = _account(ctx, f, tok)
    if not acct:
        return f
    capital = round(acct["starting_cash"] * 0.5, 2)
    body = {"name": f"QA {strategy} {pick.symbol}"[:80], "strategy": strategy, "symbols": [pick.symbol],
            "stop_loss_pct": ctx.rng.choice([None, 0.05, 0.1]), "take_profit_pct": ctx.rng.choice([None, 0.1, 0.25]),
            "max_position_pct": 1.0, "accounts": [{"account_id": acct["id"], "capital": capital}]}
    b = ctx.call("POST", "/api/bots", token=tok, body=body)
    bot_id = b.body.get("id") if f.expect_ok(b, "create_bot") and isinstance(b.body, dict) else None
    if bot_id is not None:
        f.check(abs((b.body.get("capital") or 0) - capital) < 0.01, "bot_capital_mismatch", "trading_logic", "high", "create_bot", b,
                "bot capital != allocated capital", f"capital == {capital}", f"capital={b.body.get('capital')}")
        f.check(bool((b.body.get("backtest") or {}).get("stats")), "missing_backtest", "data", "low", "create_bot", b,
                f"no backtest for {strategy} on {pick.symbol}", "a backtest with stats for a supported symbol", "backtest missing")
        a = ctx.call("GET", f"/api/paper/accounts/{acct['id']}", token=tok)
        if f.expect_ok(a, "account_after_funding") and isinstance(a.body, dict):
            f.check(abs((a.body.get("cash") or 0) - (acct["starting_cash"] - capital)) < 0.01, "funding_mismatch", "trading_logic", "high",
                    "account_after_funding", a, "account cash didn't drop by the bot's allocation",
                    f"cash == {acct['starting_cash'] - capital}", f"cash={a.body.get('cash')}")
        for step in ("run", "run_again"):  # second pass must not stack positions past the cap
            r = ctx.call("POST", f"/api/bots/{bot_id}/run", token=tok)
            if f.expect_ok(r, step) and isinstance(r.body, dict):
                _invariants(f, r.body.get("bot") or {}, r, step, 1, 1.0)
        c = ctx.call("POST", f"/api/bots/{bot_id}/close", token=tok)
        if f.expect_ok(c, "close_all") and isinstance(c.body, dict):
            f.check(not c.body.get("positions"), "close_all_left_positions", "trading_logic", "high", "close_all", c,
                    "close-all left open positions", "no positions after close-all", f"{len(c.body.get('positions') or [])} open")
    _teardown(ctx, f, tok, bot_id, acct, capital)
    return f


# ── cohort: webhook trader ───────────────────────────────────────────────────────────────────────
def webhook_trader(ctx: Ctx, pick: Pick) -> Flow:
    f = Flow(ctx, "webhook_trader", pick, "webhook")
    tok = ctx.identity("webhook_trader")
    acct = _account(ctx, f, tok)
    if not acct:
        return f
    capital, max_pct = round(acct["starting_cash"] * 0.4, 2), 0.5
    b = ctx.call("POST", "/api/bots", token=tok, body={"name": f"QA hook {pick.symbol}"[:80], "mode": "webhook", "symbols": [pick.symbol],
                                                      "max_position_pct": max_pct, "accounts": [{"account_id": acct["id"], "capital": capital}]})
    bot_id = b.body.get("id") if f.expect_ok(b, "create_webhook_bot") and isinstance(b.body, dict) else None
    if bot_id is not None:
        hook = b.body["webhook_path"]

        def send(step: str, payload: dict, allow: tuple[int, ...] = ()) -> Call:
            c = ctx.call("POST", hook, body=payload)
            f.expect_ok(c, step, allow=allow)
            return c

        def detail(step: str) -> dict:
            d = ctx.call("GET", f"/api/bots/{bot_id}", token=tok)
            if f.expect_ok(d, step) and isinstance(d.body, dict):
                _invariants(f, d.body, d, step, 1, max_pct)
                return d.body
            return {}

        send("hook_buy", {"ticker": pick.symbol, "action": "buy"})
        q1 = sum(p["quantity"] for p in detail("after_buy").get("positions") or [])
        dup = send("hook_duplicate_buy", {"ticker": pick.symbol, "action": "buy"})
        q2 = sum(p["quantity"] for p in detail("after_duplicate_buy").get("positions") or [])
        if q1 > 0:
            f.check(q2 <= q1 * CAP_TOLERANCE, "duplicate_signal_stacks", "trading_logic", "high", "hook_duplicate_buy", dup,
                    "a repeated buy alert grew the position past its cap", "a duplicate buy is capped (or ignored)",
                    f"quantity {q1:.4f} -> {q2:.4f}", error="duplicate buy stacks")
            half = round(q2 / 2, 6)
            s = send("hook_partial_sell", {"ticker": pick.symbol, "action": "sell", "quantity": half})
            q3 = sum(p["quantity"] for p in detail("after_partial_sell").get("positions") or [])
            f.check(abs(q3 - (q2 - half)) <= max(1e-6, q2 * 0.001), "partial_sell_quantity", "trading_logic", "high", "hook_partial_sell", s,
                    "a partial sell didn't reduce the position by the requested quantity", f"quantity == {q2 - half:.6f}", f"quantity {q3:.6f}")
            x = send("hook_exit", {"ticker": pick.symbol, "action": "exit"})
            f.check(not detail("after_exit").get("positions"), "exit_left_position", "trading_logic", "high", "hook_exit", x,
                    "an exit signal left a position open", "flat after exit", "position still open")
        bad = ctx.call("POST", hook, body={"ticker": pick.symbol, "action": "moon"})
        f.check(bad.status == 422, "bad_action_status", "ux", "low", "hook_bad_action", bad, "an unknown webhook action isn't a clean 422",
                "HTTP 422 with a message naming the allowed actions", f"HTTP {bad.status}: {_detail(bad)}")
        other = "QQQ" if pick.symbol.upper() == "SPY" else "SPY"
        o = ctx.call("POST", hook, body={"ticker": other, "action": "buy"})
        f.check(o.ok and (o.body or {}).get("status") == "ignored", "foreign_symbol_traded", "trading_logic", "high", "hook_foreign_symbol", o,
                f"a signal for {other} (not in the bot's symbols) wasn't ignored", "status 'ignored'", f"HTTP {o.status}: {o.text[:200]}")
        ctx.call("PATCH", f"/api/bots/{bot_id}", token=tok, body={"status": "paused"})
        pz = ctx.call("POST", hook, body={"ticker": pick.symbol, "action": "buy"})
        f.check(pz.ok and (pz.body or {}).get("status") == "ignored", "paused_bot_traded", "trading_logic", "high", "hook_paused", pz,
                "a paused bot acted on a signal", "status 'ignored' while paused", f"HTTP {pz.status}: {pz.text[:200]}")
        u = ctx.call("POST", "/api/bots/hook/" + "x" * 32, body={"ticker": pick.symbol, "action": "buy"})
        f.check(u.status == 404, "unknown_token_status", "bug", "medium", "hook_unknown_token", u, "an unknown webhook token isn't a 404",
                "HTTP 404", f"HTTP {u.status}")
    _teardown(ctx, f, tok, bot_id, acct, capital)
    return f


# ── cohort: risk limits and validation ───────────────────────────────────────────────────────────
def risk_limits(ctx: Ctx, pick: Pick) -> Flow:
    f = Flow(ctx, "risk_limits", pick, "buy_hold")
    tok = ctx.identity("risk_limits")
    acct = _account(ctx, f, tok)
    if not acct:
        return f
    capital, max_pct = round(acct["starting_cash"] * 0.6, 2), 0.3
    other = "QQQ" if pick.symbol.upper() == "SPY" else "SPY"
    funding = [{"account_id": acct["id"], "capital": capital}]
    over = ctx.call("POST", "/api/bots", token=tok, body={"name": "QA over", "strategy": "buy_hold", "symbols": [other],
                                                         "accounts": [{"account_id": acct["id"], "capital": acct["starting_cash"] * 2}]})
    f.check(over.status == 422, "over_allocation_accepted", "trading_logic", "high", "over_allocation", over,
            "allocating more than the account's cash wasn't refused", "HTTP 422", f"HTTP {over.status}")
    unk = ctx.call("POST", "/api/bots", token=tok, body={"name": "QA bad strat", "strategy": "no_such_strategy", "symbols": [other], "accounts": funding})
    f.check(unk.status == 422, "unknown_strategy_status", "bug", "medium", "unknown_strategy", unk, "an unknown strategy isn't a clean 422",
            "HTTP 422", f"HTTP {unk.status}: {_detail(unk)}")
    b = ctx.call("POST", "/api/bots", token=tok, body={"name": f"QA risk {pick.symbol}"[:80], "strategy": "buy_hold", "symbols": [pick.symbol, other],
                                                      "max_position_pct": max_pct, "stop_loss_pct": 0.05, "take_profit_pct": 0.1, "accounts": funding})
    bot_id = b.body.get("id") if f.expect_ok(b, "create_capped_bot") and isinstance(b.body, dict) else None
    if bot_id is not None:
        r = ctx.call("POST", f"/api/bots/{bot_id}/run", token=tok)
        if f.expect_ok(r, "run_capped") and isinstance(r.body, dict):
            _invariants(f, r.body.get("bot") or {}, r, "run_capped", 2, max_pct)
        p = ctx.call("PATCH", f"/api/bots/{bot_id}", token=tok, body={"max_position_pct": 1.5})
        f.check(p.status == 422, "invalid_patch_accepted", "ux", "medium", "patch_out_of_range", p, "max_position_pct > 1 was accepted",
                "HTTP 422", f"HTTP {p.status}")
    _teardown(ctx, f, tok, bot_id, acct, capital)
    return f


RUNNERS: dict[str, Callable[[Ctx, Pick], Flow]] = {
    "market_probe": market_probe,
    "momentum_bot": lambda c, p: strategy_bot(c, p, "momentum_bot"),
    "reversion_bot": lambda c, p: strategy_bot(c, p, "reversion_bot"),
    "webhook_trader": webhook_trader,
    "risk_limits": risk_limits,
}


def test_ticker(ctx: Ctx, pick: Pick, cohort: str | None = None) -> tuple[str, Flow]:
    cohort = cohort or ctx.rng.choice(COHORTS)
    t0 = time.perf_counter()
    flow = RUNNERS[cohort](ctx, pick)
    log.info("qa %s %s: %s in %.1fs", cohort, pick.symbol, "issues" if flow.failed else "pass", time.perf_counter() - t0)
    return cohort, flow
