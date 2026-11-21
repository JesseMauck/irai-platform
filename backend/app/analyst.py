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

import numpy as np

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
    ("quant", "Quantitative profile: trend, volatility, risk, levels, regimes"),
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

    # 6b quantitative profile (deterministic; charts and tables in the report come from here)
    _set(report_id, "quant", "running")
    from .quant import profile as qprofile

    qp = _safe(qprofile.build, symbol, info)
    if isinstance(qp, dict) and "error" not in qp:
        pack["quant_profile"] = {"source_id": src(f"Irradiance quantitative profile from daily OHLCV ({qp.get('source')})"), **_slim(qp)}
        _set(report_id, "quant", "done", f"{(qp.get('regime') or {}).get('current', 'n/a')} regime · 20-day vol {_p((qp.get('risk') or {}).get('vol_20d'), 0)}")
    else:
        qp = None
        _set(report_id, "quant", "done", "unavailable")

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
              "analysis": analysis, "sources": sources, "quant": qp,
              "peers": pack.get("peers"), "earnings": pack.get("earnings"), "dividends": pack.get("dividends"),
              "fundamentals_full": {k: v for k, v in pack["fundamentals"].items() if k != "source_id"},
              "profile": {k: pack["market"].get(k) for k in ("sector", "industry", "market_cap", "summary", "exchange", "52w_high", "52w_low")},
              "headlines": [{k: h.get(k) for k in ("title", "published", "outlet", "source_id")} for h in pack["news"]["headlines"][:10]],
              "filings": pack.get("filings")}
    _set(report_id, "publish", "done", None, status="done", result=result, engine=engine,
         finished_at=dt.datetime.now(dt.timezone.utc))


def _slim(qp: dict[str, Any]) -> dict[str, Any]:
    """The profile without chart series, for the model to interpret."""
    drop = {"chart", "relative_strength", "seasonality"}
    out = {k: v for k, v in qp.items() if k not in drop}
    out["risk"] = {k: v for k, v in (qp.get("risk") or {}).items() if k not in ("drawdown_series", "vol_series", "distribution")}
    out["momentum"] = {k: v for k, v in (qp.get("momentum") or {}).items() if k != "series"}
    if qp.get("regime"):
        out["regime"] = {k: v for k, v in qp["regime"].items() if k != "strip"}
    if qp.get("relative_strength"):
        out["relative_strength_3m"] = qp["relative_strength"].get("change_3m")
    sea = (qp.get("seasonality") or {}).get("by_month") or []
    nxt = (dt.date.today().month % 12) + 1
    out["seasonality_this_and_next_month"] = [m for m in sea if m["month"] in (dt.date.today().month, nxt)]
    return out


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
        "key_takeaways": {"type": "array", "items": {"type": "object", "properties": {"point": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}}}, "required": ["point", "sources"]},
                          "description": "3-5 crisp, quantified takeaways a professional trader would want first."},
        "price_action": {"type": "string", "description": "Trend structure (MA stack, crosses, ADX), key support/resistance levels and distances, volume confirmation (relative volume, up/down volume, OBV)."},
        "volatility_risk": {"type": "string", "description": "Realised vol term structure and percentile, ATR, regime, beta/correlation, drawdown, VaR/CVaR, tail shape; what that means for position sizing in general terms."},
        "relative_performance": {"type": "string", "description": "Performance vs SPY and the sector ETF across periods; relative strength trend."},
        "options_positioning": {"type": "string", "description": "Implied vs realised vol, expected move, put/call, short interest and ownership. Say plainly if options data is unavailable."},
        "earnings_quality": {"type": "string", "description": "Beat/miss history, estimate trend, margins and growth quality, balance sheet."},
        "scenarios": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string", "enum": ["Upside", "Base", "Downside"]},
                      "conditions": {"type": "string", "description": "What would have to happen, referencing the data and the statistical ranges in the pack (not your own price target)."},
                      "sources": {"type": "array", "items": {"type": "string"}}}, "required": ["name", "conditions", "sources"]}},
    },
    "required": ["key_takeaways", "price_action", "volatility_risk", "relative_performance", "options_positioning", "earnings_quality", "scenarios", "headline", "summary", "whats_new", "bull_case", "bear_case", "valuation", "technical", "sentiment", "catalysts", "risks", "questions", "data_gaps"],
}

SYSTEM = (
    "You are a senior buy-side equity research analyst and former prop-desk trader writing a same-day research note for "
    "sophisticated self-directed investors. Write in the precise vernacular professionals use (MA stack, ADX, relative strength, "
    "realised vs implied vol, ATR, drawdown, VaR, skew, positioning, estimate revisions, multiple compression/expansion) and "
    "quantify every claim with the figures in the pack. Use ONLY the JSON data pack provided: never invent numbers, dates, events or quotes, and never use outside "
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
            from valuebot.llm.toolcall import call_tool

            note = call_tool(client, model=vb.model, max_tokens=6500, system=SYSTEM, messages=[{"role": "user", "content": user}],
                             tool={"name": "submit_note", "description": "Submit the analysis note.", "input_schema": SCHEMA})
            valid = {s["id"] for s in sources}
            for sec in ("whats_new", "bull_case", "bear_case", "catalysts", "key_takeaways", "scenarios"):  # drop citations to ids that don't exist
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
                    f"{(pack['news']['buzz'] or {}).get('level', 'n/a')}." + _rules_summary_tail(pack)),
        "whats_new": [{"point": h["title"], "sources": [h["source_id"]]} for h in news] or [{"point": "No recent headlines found.", "sources": []}],
        "bull_case": bull or [{"point": "No standout strengths in the available metrics.", "sources": []}],
        "bear_case": bear or [{"point": "No standout weaknesses in the available metrics.", "sources": []}],
        "valuation": f"Forward P/E {_x(f.get('forward_pe'))}, EV/EBITDA {_x(f.get('ev_ebitda'))}; Street mean target implies {_p(c.get('implied_move'))}.",
        "technical": f"Trend {t.get('trend', 'n/a')}, RSI {round(t['rsi14']) if t.get('rsi14') else 'n/a'}; {_p(t.get('from_high_52w'))} from the 52-week high.",
        "sentiment": f"Street sentiment {c.get('sentiment') or 'n/a'}; news tone {(pack['news']['buzz'] or {}).get('tone_label') or 'n/a'}.",
        "catalysts": [{"event": "Next earnings report", "date": nxt.get("date"), "sources": sid("earnings")}] if nxt else [],
        "risks": ["Model and data limitations: verify figures in the linked sources."],
        "questions": ["What is driving recent news flow, and is it already in the price?", "How do margins and growth compare with peers over a full cycle?"],
        "data_gaps": ([] if m.get("data_label") == "LIVE" else [f"Price data is {m.get('data_label')}."]) +
                     ["Narrative written by the rules engine (AI writer unavailable); figures are computed, interpretation is templated."],
        **_rules_quant(pack, sid),
    }


def _rules_summary_tail(pack: dict[str, Any]) -> str:
    from .quant.profile import ordinal

    q = pack.get("quant_profile") or {}
    t, rk, rg = q.get("trend") or {}, q.get("risk") or {}, q.get("regime") or {}
    if not t:
        return ""
    return (f" Structurally the tape shows a {t.get('ma_stack', 'mixed')}, with price {_p(t.get('vs_sma200'))} versus the 200-day; "
            f"20-day realised volatility is {_p(rk.get('vol_20d'), 0).lstrip('+')} ({ordinal(rk.get('vol_percentile_1y'))} percentile of the past year) "
            f"and the volatility regime model reads {rg.get('current', 'n/a')}.")


def _rules_quant(pack: dict[str, Any], sid) -> dict[str, Any]:
    q = pack.get("quant_profile")
    if not q:
        return {"key_takeaways": [], "price_action": "Quantitative profile unavailable.", "volatility_risk": "n/a", "relative_performance": "n/a",
                "options_positioning": "n/a", "earnings_quality": "n/a", "scenarios": []}
    s_q = sid("quant_profile")
    t, mo, rk, lv, vol = q["trend"], q["momentum"], q["risk"], q["levels"], q.get("volume") or {}
    rg, op, pos = q.get("regime") or {}, q.get("options") or {}, q.get("positioning") or {}
    perf = {r["period"]: r for r in q["performance"]["rows"]}
    rngs = {r["horizon"]: r for r in q["ranges"]["rows"]}
    near_res = next((x for x in reversed(lv["rows"]) if x["distance"] > 0.001), None)
    near_sup = next((x for x in lv["rows"] if x["distance"] < -0.001), None)
    cross = t.get("last_cross")
    adx = t.get("adx14")
    takeaways = [
        {"point": f"Trend: {t['ma_stack']}; price {_p(t.get('vs_sma50'))} vs the 50-day and {_p(t.get('vs_sma200'))} vs the 200-day"
                  + (f"; last {cross['type']} {cross['sessions_ago']} sessions ago" if cross else "") + (f"; ADX {adx:.0f} ({t['trend_strength']})." if adx else "."), "sources": s_q},
        {"point": f"Momentum: RSI(14) {mo['rsi14']:.0f} ({mo['rsi_state']}), MACD {mo['macd_state']}, 12-1 month momentum {_p(mo.get('mom_12_1'))}." if mo.get("rsi14") else "Momentum data unavailable.", "sources": s_q},
        {"point": f"Risk: 20-day realised vol {_p(rk.get('vol_20d'), 0).lstrip('+')}, ATR {rk['atr_pct'] * 100:.1f}% of price, 1-day 95% VaR {rk['var95_1d'] * 100:.1f}%, "
                  f"max drawdown over the past year {_p(rk.get('max_drawdown_1y'))}.", "sources": s_q},
        {"point": f"Relative performance: {_p(perf.get('3M', {}).get('stock'))} over 3 months vs {_p(perf.get('3M', {}).get('spy'))} for SPY"
                  + (f" and {_p(perf['3M']['sector'])} for {q['performance']['sector_etf']}" if perf.get('3M', {}).get('sector') is not None else "") + ".", "sources": s_q},
    ]
    if rg:
        takeaways.append({"point": f"Volatility regime: {rg['current']} for {rg['days_in_regime']} sessions; historical probability of staying in this regime the next day {rg['stay_probability'] * 100:.0f}%.", "sources": s_q})
    pa = (f"{t['ma_stack'].capitalize()}. Price sits at {lv['pct_of_52w_range'] * 100:.0f}% of its 52-week range ({_p(lv['from_52w_high'])} from the high). "
          + (f"Nearest overhead reference {near_res['level'].lower()} at {near_res['price']:.2f} ({_p(near_res['distance'])}); " if near_res else "")
          + (f"nearest support {near_sup['level'].lower()} at {near_sup['price']:.2f} ({_p(near_sup['distance'])}). " if near_sup else "")
          + (f"Participation: relative volume {vol['relative_volume']:.2f}x, 20-day up/down volume {vol['up_down_volume_20d']:.2f}, OBV {vol['obv_trend_1m']} over the month." if vol.get("relative_volume") and vol.get("up_down_volume_20d") else ""))
    vr = (f"Realised vol term structure: 10-day {_p(rk.get('vol_10d'), 0).lstrip('+')}, 20-day {_p(rk.get('vol_20d'), 0).lstrip('+')}, 60-day {_p(rk.get('vol_60d'), 0).lstrip('+')}, 1-year {_p(rk.get('vol_1y'), 0).lstrip('+')}"
          f" ({'rising' if (rk.get('vol_10d') or 0) > (rk.get('vol_60d') or 0) else 'easing'} short-term). "
          + (f"Beta {rk['beta_1y']:.2f} and correlation {rk['correlation_1y']:.2f} to SPY; upside/downside capture {rk.get('upside_capture') or 0:.2f}/{rk.get('downside_capture') or 0:.2f}. " if rk.get("beta_1y") is not None else "")
          + f"Tail profile: skew {rk.get('skew_1y') or 0:.2f}, excess kurtosis {rk.get('kurtosis_1y') or 0:.1f}; CVaR(95) {rk['cvar95_1d'] * 100:.1f}% a day. "
          f"A 1-ATR move is about {rk['atr_pct'] * 100:.1f}%, a common yardstick for stop distance and position size.")
    rp = "; ".join(f"{r['period']} {_p(r['stock'])} vs SPY {_p(r['spy'])}" for r in q["performance"]["rows"] if r["stock"] is not None and r["spy"] is not None)
    if op:
        oo = (f"Front expiry ({op.get('expiry')}, {op.get('days')} days): ATM implied vol {op['atm_iv'] * 100:.0f}%"
              + (f", {op['iv_vs_realised']:.2f}x 20-day realised" if op.get("iv_vs_realised") else "")
              + (f"; straddle-implied move ±{op['expected_move_pct'] * 100:.1f}%" if op.get("expected_move_pct") else "")
              + (f"; put/call volume {op['put_call_volume']:.2f}, open interest {op['put_call_oi']:.2f}" if op.get("put_call_volume") and op.get("put_call_oi") else "") + ".")
    else:
        oo = "Listed options data was not available for this run."
    if pos.get("short_percent_float") is not None or pos.get("held_by_institutions") is not None:
        oo += f" Short interest {_p(pos.get('short_percent_float')).lstrip('+')} of float; institutions hold {_p(pos.get('held_by_institutions'), 0).lstrip('+')}."
    e = pack.get("earnings") or {}
    beats = [x for x in e.get("last_4") or [] if x.get("surprise_pct") is not None]
    f = pack["fundamentals"]
    eq = ((f"{sum(1 for x in beats if x['surprise_pct'] > 0)} of the last {len(beats)} quarters beat consensus EPS (average surprise {np.mean([x['surprise_pct'] for x in beats]):+.1f}%). " if beats else "")
          + f"Operating margin {_p(f.get('operating_margin')).lstrip('+')}, revenue growth {_p(f.get('revenue_growth'))}, ROE {_p(f.get('roe')).lstrip('+')}"
          + (f", debt/equity {f['debt_to_equity']:.0f}%." if f.get("debt_to_equity") else "."))
    m1 = rngs.get("1 month")
    sc = []
    if m1:
        sc = [{"name": "Upside", "conditions": f"Trend structure improves and momentum confirms (RSI holding above 50, MACD above signal); a +1σ one-month move from realised vol would be about {m1['plus_1sd']:.2f} (+{m1['one_sd_pct'] * 100:.1f}%)."
               + (f" A close above {near_res['price']:.2f} would clear the nearest reference level." if near_res else ""), "sources": s_q},
              {"name": "Base", "conditions": f"Volatility stays near current levels and price holds its range; roughly 68% of one-month outcomes would fall between {m1['minus_1sd']:.2f} and {m1['plus_1sd']:.2f} if volatility is unchanged.", "sources": s_q},
              {"name": "Downside", "conditions": f"Support fails and the volatility regime shifts higher; a −1σ move is about {m1['minus_1sd']:.2f}, −2σ about {m1['minus_2sd']:.2f}."
               + (f" Watch {near_sup['level'].lower()} at {near_sup['price']:.2f}." if near_sup else ""), "sources": s_q}]
    return {"key_takeaways": takeaways, "price_action": pa, "volatility_risk": vr, "relative_performance": rp + ".", "options_positioning": oo,
            "earnings_quality": eq, "scenarios": sc}
