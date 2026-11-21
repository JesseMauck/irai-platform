"""Portfolio analytics: positions valued at market, P&L, weights, concentration, sector mix, risk (volatility,
drawdown, beta, VaR, correlation) from one year of daily history at today's weights, income, valuation and
quant grades, and descriptive health flags. Everything is computed from the market service, so each number
carries the data label of the quotes behind it."""
from __future__ import annotations

import csv
import io
import math
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import research
from .market import service

MAX_HOLDINGS = 60
SYM_RE = re.compile(r"^[A-Z0-9.\-=^]{1,20}$")


# ── CSV import ───────────────────────────────────────────────────────────────────────────────────
_SYM_COLS = ("symbol", "ticker", "security", "instrument")
_QTY_COLS = ("quantity", "qty", "shares", "units", "position")
_COST_COLS = ("cost_basis", "cost basis per share", "average cost", "avg cost", "cost/share", "price paid", "cost per share", "average price", "avg price")
_TOTAL_COST_COLS = ("cost basis", "total cost", "cost basis total", "book value")


def _num(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("$", "").replace("€", "").replace("£", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def parse_csv(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse a broker positions export or a simple symbol,quantity,cost CSV. Returns (rows, warnings)."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    # broker exports often have a title line before the header: start at the first line naming a symbol column
    start = next((i for i, ln in enumerate(lines[:15]) if any(c in ln.lower() for c in _SYM_COLS)), 0)
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    if not reader.fieldnames:
        return [], ["The file is empty."]
    fields = {f: (f or "").strip().lower() for f in reader.fieldnames}

    def col(names: tuple[str, ...]) -> str | None:
        for n in names:
            for orig, low in fields.items():
                if low == n:
                    return orig
        for n in names:
            for orig, low in fields.items():
                if n in low:
                    return orig
        return None

    cs, cq, cc, ct = col(_SYM_COLS), col(_QTY_COLS), col(_COST_COLS), col(_TOTAL_COST_COLS)
    if not cs or not cq:
        return [], ["Couldn't find symbol and quantity columns. Use headers like Symbol, Quantity, Cost basis per share."]
    rows: dict[str, dict[str, Any]] = {}
    warn: list[str] = []
    for r in reader:
        sym = (r.get(cs) or "").strip().upper().replace(" ", "")
        qty = _num(r.get(cq))
        if not sym or sym in ("CASH", "TOTAL", "ACCOUNT TOTAL", "PENDING ACTIVITY") or sym.startswith("--"):
            continue
        if not SYM_RE.match(sym) or qty is None or qty == 0:
            warn.append(f"Skipped row '{sym or '?'}'")
            continue
        cost = _num(r.get(cc)) if cc else None
        if cost is None and ct:
            tot = _num(r.get(ct))
            cost = tot / qty if tot is not None and qty else None
        if sym in rows:  # same symbol in several accounts: merge with a quantity-weighted cost
            o = rows[sym]
            q2 = o["quantity"] + qty
            o["cost_basis"] = ((o["cost_basis"] or 0) * o["quantity"] + (cost or 0) * qty) / q2 if (o["cost_basis"] and cost) else (o["cost_basis"] or cost)
            o["quantity"] = q2
        else:
            rows[sym] = {"symbol": sym, "quantity": qty, "cost_basis": cost}
    return list(rows.values())[:MAX_HOLDINGS], warn[:20]


# ── analytics ────────────────────────────────────────────────────────────────────────────────────
def _fx_to_usd(currency: str | None) -> tuple[float, str | None]:
    """Multiplier from a quote currency to USD, and the FX data label (None for USD)."""
    cur = (currency or "USD").strip()
    if cur in ("USD", ""):
        return 1.0, None
    scale = 1.0
    if cur in ("GBp", "GBX"):  # London quotes in pence
        cur, scale = "GBP", 0.01
    elif cur == "ILA":
        cur, scale = "ILS", 0.01
    elif cur == "ZAc":
        cur, scale = "ZAR", 0.01
    try:
        q = service.quote(f"{cur}USD=X")
        if q.get("price"):
            return q["price"] * scale, q.get("source")
    except Exception:  # noqa: BLE001
        pass
    return float("nan"), "STALE"


def _daily(history: list[dict]) -> dict[str, float]:
    out, prev = {}, None
    for h in history:
        c = h.get("close")
        if c and prev:
            out[h["date"]] = c / prev - 1
        prev = c or prev
    return out


def _corr(a: list[float], b: list[float]) -> float | None:
    if len(a) < 30:
        return None
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    va, vb = sum((x - ma) ** 2 for x in a), sum((y - mb) ** 2 for y in b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb) if va and vb else None


def analyze(holdings: list[dict[str, Any]], cash: float = 0.0, benchmark: str = "SPY", with_grades: bool = True) -> dict[str, Any]:
    syms = [h["symbol"] for h in holdings][:MAX_HOLDINGS]

    def load(sym: str):
        try:
            c = service.chart(sym, "1y")
        except Exception as e:  # noqa: BLE001
            return sym, None, {}, None, str(e)[:120]
        try:
            info = service.info(sym)
        except Exception:  # noqa: BLE001
            info = {}
        grade = None
        if with_grades and info.get("quote_type", "EQUITY") in ("EQUITY", None):
            try:
                rt = research.ratings(sym)
                grade = {"overall": rt.get("overall_grade"), "label": rt.get("overall_label"),
                         "factors": {k: v.get("grade") for k, v in (rt.get("factors") or {}).items()}}
            except Exception:  # noqa: BLE001
                grade = None
        return sym, c, info, grade, None

    with ThreadPoolExecutor(max_workers=4) as ex:
        loaded = {x[0]: x for x in ex.map(load, [*syms, benchmark])}
    by = {h["symbol"]: h for h in holdings}
    positions, missing, daily, labels = [], [], {}, set()
    for sym in syms:
        _, c, info, grade, err = loaded[sym]
        if c is None or not c["quote"].get("price"):
            missing.append({"symbol": sym, "reason": err or "no price"})
            continue
        q = c["quote"]
        fx, fx_label = _fx_to_usd(q.get("currency"))
        if math.isnan(fx):
            missing.append({"symbol": sym, "reason": f"no FX rate for {q.get('currency')}"})
            continue
        labels.add(q.get("source"))
        if fx_label:
            labels.add(fx_label)
        h = by[sym]
        price_usd = q["price"] * fx
        value = h["quantity"] * price_usd
        cost = h.get("cost_basis")
        cost_usd = cost * fx if cost is not None else None
        rr = research._returns(c["history"])
        daily[sym] = _daily(c["history"])
        positions.append({
            "symbol": sym, "name": info.get("name") or q.get("name"), "quantity": h["quantity"], "price": q["price"],
            "currency": q.get("currency") or "USD", "fx_to_usd": fx, "value": value, "cost_basis": cost,
            "cost_value": (cost_usd * h["quantity"]) if cost_usd is not None else None,
            "unrealized": (value - cost_usd * h["quantity"]) if cost_usd is not None else None,
            "unrealized_pct": (price_usd / cost_usd - 1) if cost_usd else None,
            "day_change": value * (q.get("change_pct") or 0) / (1 + (q.get("change_pct") or 0)),
            "change_pct": q.get("change_pct"), "ret_1m": rr["1m"], "ret_12m": rr["12m"], "volatility": rr["volatility"],
            "max_drawdown": rr["max_drawdown"], "sector": info.get("sector") or ("Fund / ETF" if info.get("quote_type") in ("ETF", "MUTUALFUND") else "Other"),
            "industry": info.get("industry"), "kind": info.get("quote_type") or "EQUITY", "beta": info.get("beta"),
            "forward_pe": info.get("forward_pe"), "dividend_yield": info.get("dividend_yield"), "market_cap": info.get("market_cap"),
            "grade": grade, "source": q.get("source"),
        })
    invested = sum(p["value"] for p in positions)
    total = invested + (cash or 0)
    for p in positions:
        p["weight"] = p["value"] / total if total else 0
    positions.sort(key=lambda p: -p["value"])
    w = {p["symbol"]: p["value"] / invested for p in positions} if invested else {}

    # risk from 1y of daily returns at today's weights (a constant-mix approximation)
    dates = sorted(set().union(*[set(d) for d in daily.values()])) if daily else []
    port = []
    for d in dates:
        avail = [(s, daily[s][d]) for s in w if d in daily[s]]
        wsum = sum(w[s] for s, _ in avail)
        if wsum >= 0.6:
            port.append((d, sum(w[s] * r for s, r in avail) / wsum))
    rets = [r for _, r in port]
    level, peak, mdd, series = 100.0, 100.0, 0.0, []
    for d, r in port:
        level *= 1 + r
        peak = max(peak, level)
        mdd = min(mdd, level / peak - 1)
        series.append({"date": d, "portfolio": round(level, 3)})
    risk: dict[str, Any] = {"volatility": statistics.pstdev(rets) * math.sqrt(252) if len(rets) > 20 else None,
                            "max_drawdown": mdd if port else None,
                            "ret_1y": (level / 100 - 1) if len(port) > 200 else None,
                            "var95_1d": (-sorted(rets)[int(0.05 * len(rets))] if len(rets) > 60 else None)}
    b = loaded.get(benchmark)
    if b and b[1]:
        bd = _daily(b[1]["history"])
        pairs = [(r, bd[d]) for d, r in port if d in bd]
        bh = {h["date"]: h["close"] for h in b[1]["history"] if h.get("close")}
        base = next((bh[s["date"]] for s in series if s["date"] in bh), None)
        for s in series:
            if base and s["date"] in bh:
                s["bench"] = round(bh[s["date"]] / base * 100, 3)
        if len(pairs) > 30:
            xs, ys = [x for _, x in pairs], [y for y, _ in pairs]
            vb = statistics.pvariance(xs)
            mx, my = statistics.fmean(xs), statistics.fmean(ys)
            risk["beta"] = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs) / vb if vb else None
            risk["corr_vs_bench"] = _corr(ys, xs)
        bc = [h["close"] for h in b[1]["history"] if h.get("close")]
        risk["bench_ret_1y"] = bc[-1] / bc[0] - 1 if len(bc) > 200 else None
        risk["bench_volatility"] = research._returns(b[1]["history"])["volatility"]
    # average pairwise correlation over the last 6 months
    recent, keys, cors = dates[-126:], list(daily), []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            common = [d for d in recent if d in daily[keys[i]] and d in daily[keys[j]]]
            c = _corr([daily[keys[i]][d] for d in common], [daily[keys[j]][d] for d in common])
            if c is not None:
                cors.append((keys[i], keys[j], c))
    risk["avg_correlation"] = statistics.fmean(c for *_, c in cors) if cors else None
    risk["most_correlated"] = [{"a": a, "b": bb, "corr": c} for a, bb, c in sorted(cors, key=lambda x: -x[2])[:5]]

    hhi = sum(x * x for x in w.values())
    sectors: dict[str, float] = {}
    for p in positions:
        sectors[p["sector"]] = sectors.get(p["sector"], 0) + p["weight"]
    income = sum(p["value"] * (p["dividend_yield"] or 0) for p in positions)
    ey = [(w[p["symbol"]], 1 / p["forward_pe"]) for p in positions if p["forward_pe"] and p["forward_pe"] > 0]
    wpe = (sum(a for a, _ in ey) / sum(a * e for a, e in ey)) if ey else None  # harmonic: weighted earnings yield
    betas = [(w[p["symbol"]], p["beta"]) for p in positions if p["beta"] is not None]
    summary = {
        "total_value": total, "invested": invested, "cash": cash or 0,
        "day_change": sum(p["day_change"] for p in positions),
        "unrealized": sum(p["unrealized"] for p in positions if p["unrealized"] is not None) if any(p["unrealized"] is not None for p in positions) else None,
        "cost_value": sum(p["cost_value"] for p in positions if p["cost_value"] is not None) or None,
        "positions": len(positions), "top_weight": positions[0]["weight"] if positions else None,
        "top5_weight": sum(p["weight"] for p in positions[:5]), "hhi": hhi, "effective_holdings": (1 / hhi) if hhi else None,
        "est_annual_income": income, "yield": income / total if total else None,
        "weighted_forward_pe": wpe, "weighted_beta": (sum(a * bb for a, bb in betas) / sum(a for a, _ in betas)) if betas else None,
    }
    sector_list = [{"sector": k, "weight": v} for k, v in sorted(sectors.items(), key=lambda kv: -kv[1])]
    return {"summary": summary, "positions": positions, "sectors": sector_list, "risk": risk, "series": series,
            "flags": flags(summary, positions, sector_list, risk), "missing": missing, "benchmark": benchmark,
            "data_labels": sorted(x for x in labels if x),
            "method": "Risk uses one year of daily returns at today's weights (a constant-mix approximation); VaR is the "
                      "historical 1-day 95% loss. Values are converted to USD at the latest FX rate."}


def flags(s: dict, positions: list[dict], sectors: list[dict], risk: dict) -> list[dict[str, Any]]:
    """Descriptive observations, worded as facts to review rather than instructions."""
    out = []
    for p in positions:
        if p["weight"] >= 0.2:
            out.append({"level": "warn", "kind": "concentration", "symbol": p["symbol"],
                        "text": f"{p['symbol']} is {p['weight'] * 100:.0f}% of the portfolio; a 30% fall in it would cost about {p['weight'] * 30:.0f}% of the total."})
    for sec in sectors:
        if sec["weight"] >= 0.4 and sec["sector"] != "Fund / ETF":
            out.append({"level": "warn", "kind": "sector", "text": f"{sec['sector']} is {sec['weight'] * 100:.0f}% of the portfolio."})
    if s.get("effective_holdings") and s["positions"] >= 5 and s["effective_holdings"] < 5:
        out.append({"level": "info", "kind": "concentration", "text": f"Weights behave like about {s['effective_holdings']:.1f} equal positions (effective number of holdings)."})
    if (risk.get("avg_correlation") or 0) > 0.6:
        out.append({"level": "warn", "kind": "correlation", "text": f"Holdings move closely together (average correlation {risk['avg_correlation']:.2f}), so diversification is limited."})
    if risk.get("volatility") and risk.get("bench_volatility") and risk["volatility"] > 1.5 * risk["bench_volatility"]:
        out.append({"level": "info", "kind": "risk", "text": f"Volatility of {risk['volatility'] * 100:.0f}% is {risk['volatility'] / risk['bench_volatility']:.1f}x the benchmark's."})
    if risk.get("max_drawdown") is not None and risk["max_drawdown"] < -0.25:
        out.append({"level": "info", "kind": "risk", "text": f"At today's weights the portfolio would have fallen {abs(risk['max_drawdown']) * 100:.0f}% peak to trough over the past year."})
    for p in positions:
        if p["unrealized_pct"] is not None and p["unrealized_pct"] <= -0.25:
            out.append({"level": "info", "kind": "loss", "symbol": p["symbol"], "text": f"{p['symbol']} is {abs(p['unrealized_pct']) * 100:.0f}% below your cost basis."})
        g = (p.get("grade") or {}).get("overall")
        if g in ("D+", "D", "D-", "F"):
            out.append({"level": "info", "kind": "quality", "symbol": p["symbol"], "text": f"{p['symbol']} has a weak quant rating ({g}); see its factor grades."})
    if s.get("cash") and s.get("total_value") and s["cash"] / s["total_value"] > 0.25:
        out.append({"level": "info", "kind": "cash", "text": f"Cash is {s['cash'] / s['total_value'] * 100:.0f}% of the portfolio."})
    if not out:
        out.append({"level": "ok", "kind": "ok", "text": "No concentration, correlation or drawdown flags at the current thresholds."})
    return out


# ── AI review ────────────────────────────────────────────────────────────────────────────────────
REVIEW_SYSTEM = (
    "You are a senior portfolio analyst writing an objective review of a self-directed investor's portfolio for that "
    "investor. Use ONLY the JSON provided; never invent figures, and cite the metric behind each statement. Structure in "
    "Markdown: **Overview** (2-3 sentences), **What stands out** (concentration, sectors, factor/valuation tilt, income), "
    "**Risk profile** (volatility, drawdown, beta, correlation vs the benchmark), **Holdings to look at more closely** "
    "(why, using grades, P&L, momentum; no instructions to trade), **Questions to consider** (3-5 questions the investor "
    "can research), **Data notes** (missing, DEMO or STALE data). This is research and education, not personalized "
    "advice: never tell the reader to buy, sell, hold, trim, add, rebalance or reallocate, and never suggest target "
    "weights or price targets. Describe what the data shows and what to investigate.")


def review(a: dict[str, Any]) -> dict[str, Any]:
    from valuebot.config import settings as vb

    slim = {"summary": a["summary"], "risk": {k: v for k, v in a["risk"].items()}, "sectors": a["sectors"], "flags": a["flags"],
            "benchmark": a["benchmark"], "data_labels": a["data_labels"], "missing": a["missing"],
            "positions": [{k: p.get(k) for k in ("symbol", "name", "weight", "unrealized_pct", "ret_1m", "ret_12m", "volatility", "sector",
                                                 "forward_pe", "dividend_yield", "beta", "grade", "source")} for p in a["positions"]]}
    if vb.llm_enabled:
        try:
            import json

            import anthropic

            resp = anthropic.Anthropic(api_key=vb.anthropic_api_key).messages.create(
                model=vb.fast_model, max_tokens=1800, system=REVIEW_SYSTEM,
                messages=[{"role": "user", "content": "Portfolio data (JSON):\n" + json.dumps(slim, default=str)[:80_000]}])
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return {"engine": "claude", "model": vb.fast_model, "markdown": text}
        except Exception as e:  # noqa: BLE001
            note = f"AI writer unavailable ({type(e).__name__}); rules-based summary shown."
    else:
        note = "Set ANTHROPIC_API_KEY on the server to have Claude write this review."
    s, r = a["summary"], a["risk"]

    def pc(x, d=0):
        return "n/a" if x is None else f"{x * 100:.{d}f}%"

    lines = ["**Overview**",
             f"{s['positions']} positions worth ${s['total_value']:,.0f}. The largest is {pc(s['top_weight'])} of the total and the top five {pc(s['top5_weight'])}. "
             f"Estimated income is ${s['est_annual_income']:,.0f} a year ({pc(s['yield'], 2)}).", "", "**Risk profile**",
             f"Volatility {pc(r.get('volatility'))} vs {pc(r.get('bench_volatility'))} for {a['benchmark']}; beta {r.get('beta') and round(r['beta'], 2) or 'n/a'}; "
             f"one-year max drawdown at today's weights {pc(r.get('max_drawdown'))}.", "", "**What stands out**"]
    lines += [f"- {f['text']}" for f in a["flags"]]
    return {"engine": "rules", "markdown": "\n".join(lines), "note": note}
