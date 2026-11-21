"""Analyst Bot: gathers today's news, filings, fundamentals, technicals and Street views for a ticker, then
has Claude write a sourced, real-time analysis. Progress is persisted stage by stage so the UI can show a
progress bar. Without an API key a deterministic, rule-based write-up is produced instead.

Design rules (same as ValueBot): the model never invents numbers — it only interprets the data pack, and
every claim must cite a source id from that pack. No buy/sell/hold language or personalised advice.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import secrets
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import fundamentals, research
from .db import SessionLocal
from .market import service
from .models import AnalystReport

log = logging.getLogger("irai.analyst")

STAGES: list[tuple[str, str]] = [
    ("market", "Market snapshot"),
    ("news", "Today's news and RSS feeds"),
    ("filings", "SEC filings"),
    ("fundamentals", "Fundamentals and quant ratings"),
    ("earnings", "Earnings and dividends"),
    ("technicals", "Technicals"),
    ("street", "Analyst consensus and peers"),
    ("ai", "AI analysis"),
    ("publish", "Publish report"),
]
_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="analyst")


def new_report(user_id: int | None, symbol: str) -> AnalystReport:
    return AnalystReport(id=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3),
                         user_id=user_id, symbol=symbol, status="queued",
                         stages=[{"key": k, "label": lab, "status": "pending", "detail": None} for k, lab in STAGES])


def start(report_id: str) -> None:
    _pool.submit(_run_safe, report_id)


def _set(report_id: str, key: str, stage_status: str, detail: str | None = None, **fields) -> None:
    with SessionLocal() as db:
        r = db.get(AnalystReport, report_id)
        if not r:
            return
        r.stages = [{**s, "status": stage_status, "detail": detail} if s["key"] == key else s for s in r.stages]
        for k, v in fields.items():
            setattr(r, k, v)
        db.commit()


def _run_safe(report_id: str) -> None:
    try:
        run(report_id)
    except Exception as e:  # noqa: BLE001
        log.exception("analyst run failed")
        with SessionLocal() as db:
            r = db.get(AnalystReport, report_id)
            if r:
                r.status, r.error = "error", f"{type(e).__name__}: {e}"[:500]
                r.stages = [{**s, "status": "error"} if s["status"] == "running" else s for s in r.stages]
                r.finished_at = dt.datetime.now(dt.timezone.utc)
                db.commit()
        log.debug(traceback.format_exc())


def _safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def run(report_id: str) -> None:
    with SessionLocal() as db:
        r = db.get(AnalystReport, report_id)
        symbol = r.symbol
    _set(report_id, "market", "running", status="running")
    pack: dict[str, Any] = {"symbol": symbol, "as_of": dt.datetime.now(dt.timezone.utc).isoformat()}
    sources: list[dict[str, Any]] = []

    def src(label: str, url: str | None = None, kind: str = "data") -> str:
        sid = f"S{len(sources) + 1}"
        sources.append({"id": sid, "label": label, "url": url, "kind": kind})
        return sid

    # 1 market
    c = service.chart(symbol, "1y")
    q = c["quote"]
    try:
        info = service.info(symbol)
    except Exception:  # noqa: BLE001
        info = {}
    rets = research._returns(c["history"])
    pack["market"] = {"source_id": src(f"Market quote and 1-year price history ({q.get('source')})", f"https://finance.yahoo.com/quote/{symbol}"),
                      "name": info.get("name") or q.get("name"), "price": q.get("price"), "change_pct": q.get("change_pct"),
                      "currency": q.get("currency"), "exchange": q.get("exchange"), "market_time": q.get("market_time"),
                      "data_label": q.get("source"), "returns": rets, "52w_high": q.get("fifty_two_week_high"),
                      "52w_low": q.get("fifty_two_week_low"), "sector": info.get("sector"), "industry": info.get("industry"),
                      "market_cap": info.get("market_cap"), "summary": (info.get("summary") or "")[:800]}
    _set(report_id, "market", "done", f"{q.get('price')} {q.get('currency') or ''} · {q.get('source')}")

    # 2 news + buzz
    _set(report_id, "news", "running")
    b = _safe(research.buzz, symbol, with_headlines=True)
    heads = (b.get("headlines") or [])[:15] if isinstance(b, dict) else []
    pack["news"] = {"headlines": [{"source_id": src(h.get("title") or "headline", h.get("url"), "news"), "title": h.get("title"),
                                   "published": h.get("published"), "outlet": h.get("source")} for h in heads],
                    "buzz": {k: b.get(k) for k in ("score", "level", "tone", "tone_label", "inputs")} if isinstance(b, dict) and "score" in b else None,
                    "buzz_source_id": src("Irradiance buzz score (GDELT news volume, SEC filings, volume and price activity)")}
    _set(report_id, "news", "done", f"{len(heads)} headlines · buzz {b.get('level') if isinstance(b, dict) else 'n/a'}")

    # 3 filings
    _set(report_id, "filings", "running")
    f = _safe(research.filings, symbol)
    recent = [x for x in (f.get("filings") or []) if not x.get("routine")][:10]
    pack["filings"] = [{"source_id": src(f"SEC {x['form']} filed {x['date']}: {x['label']}", x["url"], "filing"), "form": x["form"],
                        "date": x["date"], "label": x["label"]} for x in recent]
    _set(report_id, "filings", "done", f"{len(recent)} recent key filings" if recent else (f.get("note") or "none"))

    # 4 fundamentals + ratings
    _set(report_id, "fundamentals", "running")
    rt = _safe(research.ratings, symbol)
    keys = ["trailing_pe", "forward_pe", "ev_ebitda", "price_to_sales", "price_to_book", "peg_ratio", "gross_margin", "operating_margin",
            "profit_margin", "roe", "revenue_growth", "earnings_growth", "debt_to_equity", "free_cash_flow", "revenue", "beta",
            "dividend_yield", "short_percent_float", "held_by_institutions"]
    pack["fundamentals"] = {"source_id": src("Key statistics (Yahoo Finance)"), **{k: info.get(k) for k in keys}}
    if isinstance(rt, dict) and "factors" in rt:
        pack["quant_ratings"] = {"source_id": src("Irradiance quant ratings (computed)"), "overall": rt["overall_grade"], "label": rt["overall_label"],
                                 "factors": {k: v["grade"] for k, v in rt["factors"].items()}}
    _set(report_id, "fundamentals", "done", f"quant rating {rt.get('overall_grade') if isinstance(rt, dict) else 'n/a'}")

    # 5 earnings + dividends
    _set(report_id, "earnings", "running")
    e = _safe(fundamentals.earnings, symbol)
    d = _safe(fundamentals.dividends, symbol)
    qs = (e.get("quarterly") or []) if isinstance(e, dict) else []
    pack["earnings"] = {"source_id": src("Earnings dates, EPS estimates and results (Yahoo Finance)"),
                        "next": next((x for x in reversed(qs) if x.get("upcoming")), None),
                        "last_4": [x for x in qs if not x.get("upcoming")][:4],
                        "annual": (e.get("annual") or [])[:5] if isinstance(e, dict) else []}
    if isinstance(d, dict) and d.get("history"):
        pack["dividends"] = {"source_id": src("Dividend history (Yahoo Finance)"), **{k: d.get(k) for k in
                             ("ttm_per_share", "yield_ttm", "payout_ratio", "five_year_growth", "consecutive_increases", "ex_dividend_date")}}
    _set(report_id, "earnings", "done", f"{len(pack['earnings']['last_4'])} recent quarters")

    # 6 technicals
    _set(report_id, "technicals", "running")
    t = _safe(fundamentals.technicals, symbol)
    pack["technicals"] = {"source_id": src("Technical indicators computed from daily closes"),
                          **({k: t.get(k) for k in ("trend", "rsi14", "macd", "distance_from_sma", "from_high_52w", "volatility_20d_ann", "signals", "performance")}
                             if isinstance(t, dict) else {})}
    _set(report_id, "technicals", "done", t.get("trend") if isinstance(t, dict) else None)

    # 7 street + peers
    _set(report_id, "street", "running")
    cons = _safe(research.consensus, symbol)
    pr = _safe(fundamentals.peers, symbol)
    pack["consensus"] = {"source_id": src("Sell-side consensus (Yahoo Finance)"), **({k: cons.get(k) for k in
                         ("analyst_count", "sentiment", "recommendation_mean", "target_mean", "target_low", "target_high", "implied_move")} if isinstance(cons, dict) else {})}
    if isinstance(pr, dict) and pr.get("rows"):
        pack["peers"] = {"source_id": src(f"Peer comparison ({pr.get('group')})"), "median": pr.get("peer_median"),
                         "rows": [{k: r.get(k) for k in ("symbol", "forward_pe", "ev_ebitda", "operating_margin", "revenue_growth", "roe")} for r in pr["rows"][:8]]}
    _set(report_id, "street", "done", f"{int(cons['analyst_count']) if isinstance(cons, dict) and cons.get('analyst_count') else 'n/a'} analysts")

    # 8 AI
    _set(report_id, "ai", "running")
    analysis, engine = write(pack, sources)
    _set(report_id, "ai", "done", engine)

    # 9 publish
    _set(report_id, "publish", "running")
    result = {"symbol": symbol, "name": pack["market"]["name"], "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "snapshot": {"price": q.get("price"), "change_pct": q.get("change_pct"), "currency": q.get("currency"), "data_label": q.get("source"),
                           "returns": rets, "quant": pack.get("quant_ratings"), "consensus": pack["consensus"], "buzz": pack["news"]["buzz"],
                           "technicals": {"trend": pack["technicals"].get("trend"), "rsi14": pack["technicals"].get("rsi14")},
                           "next_earnings": pack["earnings"]["next"], "dividend_yield": (pack.get("dividends") or {}).get("yield_ttm"),
                           "fundamentals": {k: pack["fundamentals"].get(k) for k in ("forward_pe", "ev_ebitda", "operating_margin", "revenue_growth", "roe")}},
              "analysis": analysis, "sources": sources}
    _set(report_id, "publish", "done", None, status="done", result=result, engine=engine,
         finished_at=dt.datetime.now(dt.timezone.utc))


# ── writing ──────────────────────────────────────────────────────────────────────────────────────
SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "One-line takeaway about what matters for this stock today (descriptive, no advice)."},
        "summary": {"type": "string", "description": "3-5 sentence executive summary."},
        "whats_new": {"type": "array", "items": {"type": "object", "properties": {"point": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}}}, "required": ["point", "sources"]}, "description": "What changed recently: news, filings, earnings, price action."},
        "bull_case": {"type": "array", "items": {"type": "object", "properties": {"point": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}}}, "required": ["point", "sources"]}},
        "bear_case": {"type": "array", "items": {"type": "object", "properties": {"point": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}}}, "required": ["point", "sources"]}},
        "valuation": {"type": "string", "description": "Valuation context vs history, peers and consensus, citing numbers from the pack."},
        "technical": {"type": "string", "description": "Trend, momentum and positioning context."},
        "sentiment": {"type": "string", "description": "News tone, buzz, Street sentiment."},
        "catalysts": {"type": "array", "items": {"type": "object", "properties": {"event": {"type": "string"}, "date": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}}}, "required": ["event", "sources"]}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {"type": "string"}, "description": "Questions an analyst should research next."},
        "data_gaps": {"type": "array", "items": {"type": "string"}, "description": "Missing, stale or DEMO data the reader should know about."},
    },
    "required": ["headline", "summary", "whats_new", "bull_case", "bear_case", "valuation", "technical", "sentiment", "catalysts", "risks", "questions", "data_gaps"],
}

SYSTEM = (
    "You are a senior buy-side equity research analyst writing a same-day research note for sophisticated self-directed "
    "investors. Use ONLY the JSON data pack provided: never invent numbers, dates, events or quotes, and never use outside "
    "knowledge about recent events. Every bullet must cite one or more source ids (e.g. S3) from the pack. Be specific and "
    "quantitative (cite the figures), balanced (real bull and bear cases), and concise. If headlines are ambiguous, say so. "
    "Flag data gaps (missing fields, DEMO/STALE labels). This is research and education, not advice: never say buy, sell, hold, "
    "overweight, accumulate, or give price targets of your own; describe what the data shows and what to watch.")


def write(pack: dict[str, Any], sources: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    from valuebot.config import settings as vb

    if vb.llm_enabled:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=vb.anthropic_api_key)
            user = ("Data pack (JSON):\n" + json.dumps(pack, default=str)[:90_000] +
                    "\n\nSource list:\n" + json.dumps([{k: s[k] for k in ("id", "label")} for s in sources])[:20_000] +
                    "\n\nWrite today's analysis note for this ticker.")
            resp = client.messages.create(model=vb.model, max_tokens=3500, system=SYSTEM,
                                          messages=[{"role": "user", "content": user}],
                                          tools=[{"name": "submit_note", "description": "Submit the analysis note.", "input_schema": SCHEMA}],
                                          tool_choice={"type": "tool", "name": "submit_note"})
            for block in resp.content:
                if block.type == "tool_use":
                    note = dict(block.input)
                    valid = {s["id"] for s in sources}
                    for sec in ("whats_new", "bull_case", "bear_case", "catalysts"):  # drop citations to ids that don't exist
                        for item in note.get(sec) or []:
                            item["sources"] = [x for x in item.get("sources") or [] if x in valid]
                    return note, f"Claude ({vb.model})"
        except Exception as e:  # noqa: BLE001
            log.warning("analyst LLM failed, using rules: %s", e)
    return rules_note(pack), "rules"


def _p(x: float | None, d: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:+.{d}f}%"


def _x(v: float | None) -> str:
    return "n/a" if v is None or v <= 0 else f"{v:.1f}x"


def rules_note(pack: dict[str, Any]) -> dict[str, Any]:
    m, f, t, c = pack["market"], pack["fundamentals"], pack["technicals"], pack["consensus"]
    qr = pack.get("quant_ratings") or {}
    r = m["returns"]
    sid = lambda sec: [pack[sec]["source_id"]] if pack.get(sec) and pack[sec].get("source_id") else []  # noqa: E731
    news = pack["news"]["headlines"][:4]
    bull, bear = [], []
    if (f.get("revenue_growth") or 0) > 0.1:
        bull.append({"point": f"Revenue growing {_p(f['revenue_growth'])} year over year.", "sources": sid("fundamentals")})
    if (f.get("operating_margin") or 0) > 0.25:
        bull.append({"point": f"High operating margin of {_p(f['operating_margin'])}.", "sources": sid("fundamentals")})
    if c.get("implied_move") and c["implied_move"] > 0.1:
        bull.append({"point": f"Consensus target implies {_p(c['implied_move'])} vs the current price ({int(c.get('analyst_count') or 0)} analysts).", "sources": sid("consensus")})
    if (f.get("forward_pe") or 0) > 35:
        bear.append({"point": f"Rich valuation at {f['forward_pe']:.1f}x forward earnings.", "sources": sid("fundamentals")})
    if (r.get("3m") or 0) < -0.1:
        bear.append({"point": f"Weak momentum: {_p(r['3m'])} over three months.", "sources": sid("market")})
    if t.get("trend") == "Downtrend":
        bear.append({"point": "Price below its 50- and 200-day averages (downtrend).", "sources": sid("technicals")})
    if (f.get("debt_to_equity") or 0) > 150:
        bear.append({"point": f"Leverage: debt/equity {f['debt_to_equity']:.0f}%.", "sources": sid("fundamentals")})
    nxt = pack["earnings"].get("next")
    return {
        "headline": f"{m['name']} {_p(m.get('change_pct'), 2)} today; {t.get('trend', 'mixed').lower()} trend, quant grade {qr.get('overall', 'n/a')}.",
        "summary": (f"{m['name']} trades at {m.get('price')} {m.get('currency') or ''} ({m.get('data_label')}). Over 12 months the stock is "
                    f"{_p(r.get('12m'))}; quant rating {qr.get('overall', 'n/a')} ({qr.get('label') or 'n/a'}). Buzz is "
                    f"{(pack['news']['buzz'] or {}).get('level', 'n/a')}. This summary was generated by rules because the AI writer is not configured."),
        "whats_new": [{"point": h["title"], "sources": [h["source_id"]]} for h in news] or [{"point": "No recent headlines found.", "sources": []}],
        "bull_case": bull or [{"point": "No standout strengths in the available metrics.", "sources": []}],
        "bear_case": bear or [{"point": "No standout weaknesses in the available metrics.", "sources": []}],
        "valuation": f"Forward P/E {_x(f.get('forward_pe'))}, EV/EBITDA {_x(f.get('ev_ebitda'))}; Street mean target implies {_p(c.get('implied_move'))}.",
        "technical": f"Trend {t.get('trend', 'n/a')}, RSI {round(t['rsi14']) if t.get('rsi14') else 'n/a'}; {_p(t.get('from_high_52w'))} from the 52-week high.",
        "sentiment": f"Street sentiment {c.get('sentiment') or 'n/a'}; news tone {(pack['news']['buzz'] or {}).get('tone_label') or 'n/a'}.",
        "catalysts": [{"event": "Next earnings report", "date": nxt.get("date"), "sources": sid("earnings")}] if nxt else [],
        "risks": ["Model and data limitations: verify figures in the linked sources."],
        "questions": ["What is driving recent news flow, and is it already in the price?", "How do margins and growth compare with peers over a full cycle?"],
        "data_gaps": [] if m.get("data_label") == "LIVE" else [f"Price data is {m.get('data_label')}."],
    }
