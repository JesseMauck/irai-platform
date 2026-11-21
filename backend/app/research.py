"""Research data for ticker pages and the terminal, built only from public/open sources.

* Quant ratings — our own letter grades (Valuation, Quality, Growth, Momentum, Risk) from fundamentals and
  price history. Not a third-party rating and not a recommendation.
* Consensus — sell-side analyst count, recommendation mean and price-target range as published by the feed.
* SEC filings and financial statements — SEC EDGAR submissions and XBRL company facts (public domain).
* Buzz — media and market attention: GDELT news volume and tone (open data), Yahoo Finance RSS headlines,
  recent 8-K filings, unusual trading volume and price moves, combined into a 0-100 score.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics
import threading
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from .config import settings
from .market import service

SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"
YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline"
UA = "IrradianceResearch/1.0 (support@irradiance.ai)"

_cache: dict[tuple[str, str], tuple[float, Any]] = {}
_lock = threading.Lock()


def _memo(kind: str, key: str, ttl: float, fn):
    now = time.time()
    with _lock:
        hit = _cache.get((kind, key))
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    with _lock:
        _cache[(kind, key)] = (now, val)
    return val


def _http() -> httpx.Client:
    import os

    return httpx.Client(headers={"User-Agent": os.environ.get("SEC_USER_AGENT") or UA}, timeout=12, follow_redirects=True)


# ── quant ratings ────────────────────────────────────────────────────────────────────────────────
GRADES = ["F", "D-", "D", "D+", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+"]


def _grade(score: float | None) -> str | None:
    """0..1 score → letter grade."""
    if score is None or math.isnan(score):
        return None
    return GRADES[max(0, min(len(GRADES) - 1, int(round(score * (len(GRADES) - 1)))))]


def _scale(x: float | None, lo: float, hi: float, invert: bool = False) -> float | None:
    """Map x linearly from [lo, hi] to [0, 1], clipped; invert when lower is better."""
    if x is None:
        return None
    t = (x - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    return 1 - t if invert else t


def _avg(xs: list[float | None]) -> float | None:
    v = [x for x in xs if x is not None]
    return sum(v) / len(v) if v else None


def _returns(history: list[dict]) -> dict[str, float | None]:
    closes = [h["close"] for h in history if h.get("close")]

    def ret(n: int) -> float | None:
        return closes[-1] / closes[-1 - n] - 1 if len(closes) > n else None

    daily = [b / a - 1 for a, b in zip(closes, closes[1:]) if a]
    vol = statistics.pstdev(daily[-252:]) * math.sqrt(252) if len(daily) >= 20 else None
    peak, mdd = 0.0, 0.0
    for c in closes[-252:]:
        peak = max(peak, c)
        mdd = min(mdd, c / peak - 1) if peak else mdd
    return {"1m": ret(21), "3m": ret(63), "6m": ret(126), "12m": ret(250), "volatility": vol, "max_drawdown": mdd if closes else None}


def ratings(symbol: str) -> dict[str, Any]:
    symbol = service.normalise_symbol(symbol)
    data = service.chart(symbol, "1y")
    q, hist = data["quote"], data["history"]
    try:
        info = service.info(symbol)
    except Exception:  # noqa: BLE001
        info = {}
    r = _returns(hist)
    def g(k):  # treat non-meaningful zeros (e.g. banks report no gross margin) as missing
        v = info.get(k)
        return None if k in ("gross_margin", "ev_ebitda") and (v is None or v <= 0) else v

    pe = g("forward_pe") or g("trailing_pe")
    factors = {
        "valuation": {"score": _avg([_scale(pe, 8, 45, invert=True) if pe and pe > 0 else None,
                                     _scale(g("ev_ebitda"), 5, 35, invert=True) if g("ev_ebitda") and g("ev_ebitda") > 0 else None,
                                     _scale(g("price_to_sales"), 0.5, 15, invert=True),
                                     _scale(g("peg_ratio"), 0.5, 3.5, invert=True) if g("peg_ratio") and g("peg_ratio") > 0 else None]),
                      "inputs": {"P/E (fwd or ttm)": pe, "EV/EBITDA": g("ev_ebitda"), "P/S": g("price_to_sales"), "PEG": g("peg_ratio")}},
        "quality": {"score": _avg([_scale(g("roe"), 0, 0.35), _scale(g("operating_margin"), 0, 0.4),
                                   _scale(g("gross_margin"), 0.15, 0.75),
                                   _scale(g("debt_to_equity"), 0, 250, invert=True) if g("debt_to_equity") is not None else None]),
                    "inputs": {"ROE": g("roe"), "Operating margin": g("operating_margin"), "Gross margin": g("gross_margin"),
                               "Debt / equity (%)": g("debt_to_equity")}},
        "growth": {"score": _avg([_scale(g("revenue_growth"), -0.1, 0.35), _scale(g("earnings_growth"), -0.3, 0.5)]),
                   "inputs": {"Revenue growth (yoy)": g("revenue_growth"), "Earnings growth (yoy)": g("earnings_growth")}},
        "momentum": {"score": _avg([_scale(r["3m"], -0.25, 0.3), _scale(r["6m"], -0.35, 0.45), _scale(r["12m"], -0.45, 0.7)]),
                     "inputs": {"3-month return": r["3m"], "6-month return": r["6m"], "12-month return": r["12m"]}},
        "risk": {"score": _avg([_scale(r["volatility"], 0.12, 0.7, invert=True), _scale(g("beta"), 0.5, 2.0, invert=True),
                                _scale(r["max_drawdown"], -0.6, -0.05)]),
                 "inputs": {"Volatility (1y, ann.)": r["volatility"], "Beta": g("beta"), "Max drawdown (1y)": r["max_drawdown"]}},
    }
    for f in factors.values():
        f["grade"] = _grade(f["score"])
    overall = _avg([f["score"] for f in factors.values()])
    label = None if overall is None else ("Very strong" if overall >= 0.75 else "Strong" if overall >= 0.6 else
                                           "Neutral" if overall >= 0.4 else "Weak" if overall >= 0.25 else "Very weak")
    return {"symbol": symbol, "name": q.get("name"), "factors": factors, "overall_score": overall,
            "overall_grade": _grade(overall), "overall_label": label, "returns": r, "source": q.get("source"),
            "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
            "note": "Irradiance quant grades are computed from public fundamentals and price history. They describe "
                    "characteristics, not a recommendation."}


def consensus(symbol: str) -> dict[str, Any]:
    symbol = service.normalise_symbol(symbol)
    try:
        info = service.info(symbol)
    except Exception:  # noqa: BLE001
        info = {}
    price = service.quote(symbol).get("price")
    tgt = info.get("target_mean_price")
    mean = info.get("recommendation_mean")  # 1 = strongest positive … 5 = strongest negative (feed's scale)
    label = None if mean is None else ("Very positive" if mean <= 1.5 else "Positive" if mean <= 2.5 else
                                       "Mixed" if mean <= 3.5 else "Negative" if mean <= 4.5 else "Very negative")
    return {"symbol": symbol, "analyst_count": info.get("analyst_count"), "recommendation_mean": mean,
            "sentiment": label, "target_mean": tgt, "target_median": info.get("target_median_price"),
            "target_high": info.get("target_high_price"), "target_low": info.get("target_low_price"),
            "price": price, "implied_move": (tgt / price - 1) if tgt and price else None,
            "source": info.get("source", "DEMO"),
            "note": "Sell-side consensus as published by the market-data feed; shown for context, not endorsed."}


# ── SEC EDGAR ────────────────────────────────────────────────────────────────────────────────────
FORM_LABELS = {"10-K": "Annual report", "10-Q": "Quarterly report", "8-K": "Current report (material event)",
               "4": "Insider transaction", "3": "Initial insider holdings", "S-1": "IPO registration",
               "DEF 14A": "Proxy statement", "SC 13D": "Activist stake (>5%)", "SC 13G": "Passive stake (>5%)",
               "20-F": "Annual report (foreign issuer)", "6-K": "Current report (foreign issuer)", "13F-HR": "Institutional holdings",
               "424B2": "Prospectus", "N-CSR": "Fund shareholder report", "N-PORT-P": "Fund portfolio holdings"}


# High-volume filings (structured-note prospectuses, free-writing prospectuses, plan registrations) that bury
# the reports investors care about; shown only when "All filings" is selected.
ROUTINE_FORMS = {"424B2", "424B3", "424B4", "424B5", "424B7", "FWP", "S-8", "S-8 POS", "11-K", "CORRESP", "UPLOAD", "SC 13G/A", "13F-HR/A"}


def _cik(symbol: str) -> int | None:
    from valuebot.data import sec

    try:
        return sec.ticker_map().get(symbol.upper(), {}).get("cik")
    except Exception:  # noqa: BLE001
        return None


def filings(symbol: str, limit: int = 60) -> dict[str, Any]:
    symbol = service.normalise_symbol(symbol)
    if not settings.live:
        return {"symbol": symbol, "filings": [], "source": "DEMO", "note": "SEC filings need live mode."}

    def fetch():
        cik = _cik(symbol)
        if not cik:
            return {"symbol": symbol, "filings": [], "source": "LIVE", "note": "Not an SEC registrant (common for non-US listings)."}
        with _http() as c:
            subs = c.get(SEC_SUBMISSIONS.format(cik=cik)).raise_for_status().json()
        rec = subs.get("filings", {}).get("recent", {})
        out, n_key, n_routine = [], 0, 0
        for form, acc, date, doc, desc in zip(rec.get("form", []), rec.get("accessionNumber", []), rec.get("filingDate", []),
                                              rec.get("primaryDocument", []), rec.get("primaryDocDescription", [])):
            routine = form in ROUTINE_FORMS
            if (routine and n_routine >= 15) or (not routine and n_key >= limit):
                if n_key >= limit:
                    break
                continue
            n_routine += routine
            n_key += not routine
            out.append({"form": form, "label": FORM_LABELS.get(form, desc or form), "date": date, "routine": routine,
                        "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"})
        return {"symbol": symbol, "cik": cik, "company": subs.get("name"), "filings": out, "source": "LIVE",
                "edgar_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"}

    try:
        return _memo("filings", symbol, 1800, fetch)
    except Exception as e:  # noqa: BLE001
        return {"symbol": symbol, "filings": [], "source": "ERROR", "note": f"SEC EDGAR unavailable: {type(e).__name__}"}


def financials(symbol: str) -> dict[str, Any]:
    symbol = service.normalise_symbol(symbol)
    if not settings.live:
        return {"symbol": symbol, "years": [], "source": "DEMO", "note": "Financial statements need live mode."}

    def fetch():
        from valuebot.data import sec

        f = sec.fetch_financials(symbol, years=6)
        keys = ["revenue", "gross_profit", "operating_income", "net_income", "rnd", "depreciation", "capex",
                "dividends_paid", "buybacks", "cash", "debt", "equity", "total_assets"]
        years = [{"fiscal_year": h["fiscal_year"], "period_end": h["period_end"], **{k: h.get(k) for k in keys}} for h in f["history"]]
        for y in years:
            rev = y.get("revenue")
            y["operating_margin"] = (y["operating_income"] / rev) if rev and y.get("operating_income") is not None else None
            y["net_margin"] = (y["net_income"] / rev) if rev and y.get("net_income") is not None else None
            y["free_cash_flow_proxy"] = None
        return {"symbol": symbol, "company": f["name"], "years": years, "shares_outstanding": f["shares_outstanding"],
                "source": "LIVE", "provider": f["source"]["label"], "provider_url": f["source"]["url"]}

    try:
        return _memo("financials", symbol, 12 * 3600, fetch)
    except LookupError:
        return {"symbol": symbol, "years": [], "source": "LIVE", "note": "Not an SEC registrant (common for non-US listings)."}
    except Exception as e:  # noqa: BLE001
        return {"symbol": symbol, "years": [], "source": "ERROR", "note": f"SEC EDGAR unavailable: {type(e).__name__}"}


# ── buzz: media + market attention ───────────────────────────────────────────────────────────────
LEVELS = [(85, "Extreme"), (70, "High"), (50, "Elevated"), (25, "Normal"), (0, "Quiet")]


def level(score: float) -> str:
    return next(name for cut, name in LEVELS if score >= cut)


def _news_query(name: str | None, symbol: str) -> str:
    """GDELT full-text query: the company name (trimmed of legal suffixes), quoted."""
    base = (name or symbol).replace(",", " ")
    for suf in (" Inc.", " Inc", " Corporation", " Corp.", " Corp", " plc", " PLC", " Ltd.", " Ltd", " S.A.", " N.V.",
                " AG", " SE", " Holdings", " Group", " Co.", " Company", " ETF", " Trust", " Fund"):
        base = base.replace(suf, "")
    base = " ".join(base.split())[:60]
    return f'"{base}"' if " " in base else base


def parse_gdelt_timeline(payload: dict) -> list[float]:
    try:
        return [float(p.get("value", 0)) for p in payload["timeline"][0]["data"]]
    except (KeyError, IndexError, TypeError, ValueError):
        return []


def parse_rss(xml_text: str, limit: int = 15) -> list[dict[str, Any]]:
    out = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        out.append({"title": title, "url": (item.findtext("link") or "").strip(),
                    "published": (item.findtext("pubDate") or "").strip(), "source": "Yahoo Finance RSS"})
        if len(out) >= limit:
            break
    return out


def score_buzz(news_today: float | None, news_baseline: list[float], tone: float | None, volume_ratio: float | None,
               move_sigma: float | None, filings_7d: int) -> dict[str, Any]:
    """Combine attention signals into 0-100. Each component is 0-100; weights favour news volume."""
    comps: dict[str, float | None] = {}
    if news_today is not None and news_baseline:
        mu = statistics.mean(news_baseline)
        sd = statistics.pstdev(news_baseline) or max(1.0, mu * 0.5)
        z = (news_today - mu) / sd
        comps["news_volume"] = max(0.0, min(100.0, 50 + 18 * z)) if mu > 0 or news_today > 0 else 10.0
    else:
        comps["news_volume"] = None
    comps["trading_volume"] = None if volume_ratio is None else max(0.0, min(100.0, (volume_ratio - 0.5) * 40))
    comps["price_move"] = None if move_sigma is None else max(0.0, min(100.0, abs(move_sigma) * 28))
    comps["filings"] = min(100.0, filings_7d * 30.0)
    weights = {"news_volume": 0.45, "trading_volume": 0.25, "price_move": 0.2, "filings": 0.1}
    have = {k: v for k, v in comps.items() if v is not None}
    total_w = sum(weights[k] for k in have) or 1.0
    score = sum(weights[k] * v for k, v in have.items()) / total_w
    return {"score": round(score, 1), "level": level(score), "components": comps,
            "tone": tone, "tone_label": None if tone is None else ("Positive" if tone > 1.5 else "Negative" if tone < -1.5 else "Mixed")}


def _gdelt(params: dict) -> dict:
    with _http() as c:
        r = c.get(GDELT_DOC, params={**params, "format": "json"})
    r.raise_for_status()
    return r.json() if r.text.strip().startswith("{") else {}


_buzz_cache: dict[tuple[str, bool], tuple[float, dict[str, Any]]] = {}
_buzz_refreshing: set[tuple[str, bool]] = set()
_buzz_gates: dict[tuple[str, bool], threading.Lock] = {}
BUZZ_FRESH, BUZZ_STALE = 900, 6 * 3600
_neg: dict[tuple[str, str], float] = {}  # recent provider failures, so a slow or throttled source isn't retried on every click


def _soft(kind: str, key: str, ttl: float, fn, fail_ttl: float = 600):
    """_memo that also remembers failures briefly (GDELT throttles hard and times out)."""
    t = _neg.get((kind, key))
    if t and time.time() - t < fail_ttl:
        raise RuntimeError(f"{kind} recently unavailable")
    try:
        return _memo(kind, key, ttl, fn)
    except Exception:
        _neg[(kind, key)] = time.time()
        raise


def buzz(symbol: str, with_headlines: bool = True) -> dict[str, Any]:
    """Cached with stale-while-revalidate: a reading under 15 minutes old is served as is; an older one (up to 6 hours) is
    served immediately while a fresh one is computed in the background, so the Buzz tab never waits on news providers."""
    symbol = service.normalise_symbol(symbol)
    key = (symbol, with_headlines)
    hit = _buzz_cache.get(key) or (_buzz_cache.get((symbol, True)) if not with_headlines else None)
    age = time.time() - hit[0] if hit else None
    if hit and age is not None and age < BUZZ_FRESH:
        return hit[1]
    if hit and age is not None and age < BUZZ_STALE:
        with _lock:
            go = key not in _buzz_refreshing
            _buzz_refreshing.add(key)
        if go:
            def refresh():
                try:
                    _buzz_cache[key] = (time.time(), _compute_buzz(symbol, with_headlines))
                except Exception:  # noqa: BLE001
                    pass
                finally:
                    _buzz_refreshing.discard(key)
            threading.Thread(target=refresh, daemon=True, name=f"buzz-{symbol}").start()
        return {**hit[1], "refreshing": True}
    with _lock:
        gate = _buzz_gates.setdefault(key, threading.Lock())
    with gate:  # concurrent first requests (header meter + Buzz card) share one computation
        hit = _buzz_cache.get(key)
        if hit and time.time() - hit[0] < BUZZ_FRESH:
            return hit[1]
        out = _compute_buzz(symbol, with_headlines)
        _buzz_cache[key] = (time.time(), out)
        return out


def _compute_buzz(symbol: str, with_headlines: bool) -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor

    data = service.chart(symbol, "1y")
    q, hist = data["quote"], data["history"]
    ex = ThreadPoolExecutor(max_workers=5)
    try:
        f_info = ex.submit(service.info, symbol)
        f_fil = ex.submit(filings, symbol) if settings.live else None
        try:
            info = f_info.result(timeout=8)
        except Exception:  # noqa: BLE001
            info = {}
        name = info.get("name") or q.get("name")
        f_vol = f_tone = f_head = None
        if settings.live:
            qry = _news_query(name, symbol)
            f_vol = ex.submit(_soft, "gdelt-vol", symbol, 3600, lambda: _gdelt({"query": qry, "mode": "timelinevolraw", "timespan": "30d"}))
            f_tone = ex.submit(_soft, "gdelt-tone", symbol, 3600, lambda: _gdelt({"query": qry, "mode": "timelinetone", "timespan": "7d"}))
        if with_headlines:
            f_head = ex.submit(headlines, symbol, name)
        avg_vol = info.get("average_volume")
        vol_ratio = (q["volume"] / avg_vol) if q.get("volume") and avg_vol else None
        rets = [b["close"] / a["close"] - 1 for a, b in zip(hist, hist[1:]) if a.get("close")]
        sd = statistics.pstdev(rets[-60:]) if len(rets) >= 20 else None
        move_sigma = (q["change_pct"] / sd) if sd and q.get("change_pct") is not None else None
        f7 = 0
        if f_fil:
            try:
                cutoff = (dt.date.today() - dt.timedelta(days=7)).isoformat()
                f7 = sum(1 for f in f_fil.result(timeout=10).get("filings", []) if f["date"] >= cutoff and f["form"] in ("8-K", "6-K", "SC 13D", "4"))
            except Exception:  # noqa: BLE001
                f7 = 0
        news_today, baseline, tone, news_err = None, [], None, None
        if f_vol:
            try:
                series = parse_gdelt_timeline(f_vol.result(timeout=10))
                if series:
                    news_today, baseline = series[-1], series[:-1]
                tones = parse_gdelt_timeline(f_tone.result(timeout=10))
                tone = statistics.mean(tones) if tones else None
            except Exception as e:  # noqa: BLE001
                news_err = type(e).__name__
        heads = None
        if f_head:
            try:
                heads = f_head.result(timeout=10)
            except Exception:  # noqa: BLE001
                heads = []
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    s = score_buzz(news_today, baseline, tone, vol_ratio, move_sigma, f7)
    out = {"symbol": symbol, "name": name, "kind": _kind(info, q), **s,
           "inputs": {"news_articles_today": news_today, "news_daily_avg_30d": statistics.mean(baseline) if baseline else None,
                      "volume_vs_average": vol_ratio, "move_in_sigmas": move_sigma, "filings_7d": f7},
           "price_source": q.get("source"), "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
           "providers": ["GDELT Project (news volume & tone)", "SEC EDGAR", "market feed (volume, price)"],
           "note": "Buzz measures attention, not direction or quality. High buzz often means higher volatility."}
    if news_err:
        out["news_error"] = news_err
    if with_headlines:
        out["headlines"] = heads or []
    return out


def _kind(info: dict, q: dict) -> str:
    t = (info.get("quote_type") or q.get("instrument_type") or "").upper()
    cat = (info.get("category") or "").lower()
    if t == "ETF":
        return "bond_etf" if any(w in cat for w in ("bond", "treasury", "credit", "muni", "income")) else "etf"
    if t == "MUTUALFUND" or "closed" in cat:
        return "fund"
    return {"EQUITY": "equity", "INDEX": "index", "CURRENCY": "fx", "CRYPTOCURRENCY": "crypto", "FUTURE": "future"}.get(t, t.lower() or "other")


def headlines(symbol: str, name: str | None = None, limit: int = 15) -> list[dict[str, Any]]:
    if not settings.live:
        return []

    def fetch():
        items: list[dict[str, Any]] = []
        try:
            with _http() as c:
                r = c.get(YAHOO_RSS, params={"s": symbol, "region": "US", "lang": "en-US"})
            if r.status_code == 200:
                items = parse_rss(r.text, limit)
        except httpx.HTTPError:
            pass
        if len(items) < 5:
            try:
                art = _gdelt({"query": _news_query(name, symbol) + " sourcelang:english", "mode": "artlist",
                              "maxrecords": str(limit), "sort": "datedesc", "timespan": "7d"})
                for a in art.get("articles", [])[:limit]:
                    items.append({"title": a.get("title"), "url": a.get("url"), "published": a.get("seendate"),
                                  "source": a.get("domain") or "GDELT"})
            except Exception:  # noqa: BLE001
                pass
        return items[:limit]

    return _memo("headlines", symbol, 900, fetch)
