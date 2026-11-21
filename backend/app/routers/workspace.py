"""Research workspace: unified search, themes (curated + custom) with drivers and PESTEL radar, pins,
and multi-stock comparison with an AI-written read-through."""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import statistics
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import fundamentals, research
from ..config import settings
from ..db import get_db
from ..market import service
from ..models import Article, BuzzSnapshot, Pin, ResearchTheme, Thread, User, Watchlist
from ..security import current_user, limits, optional_user

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

# ── search ───────────────────────────────────────────────────────────────────────────────────────
@router.get("/search")
def search(q: str = Query(min_length=1, max_length=60), user: User | None = Depends(optional_user),
           db: Session = Depends(get_db)):
    """One box for everything: tickers, research articles, themes and community analysis."""
    like = f"%{q.strip().lower()}%"
    tickers = service.search(q)[:8]
    articles = [{"slug": a.slug, "title": a.title, "category": a.category} for a in db.scalars(
        select(Article).where(or_(func.lower(Article.title).like(like), func.lower(Article.summary).like(like))).limit(6))]
    tq = select(ResearchTheme).where(or_(func.lower(ResearchTheme.name).like(like), func.lower(ResearchTheme.description).like(like)))
    tq = tq.where(or_(ResearchTheme.public.is_(True), ResearchTheme.owner_id == (user.id if user else -1)))
    themes = [{"slug": t.slug, "name": t.name, "custom": t.owner_id is not None} for t in db.scalars(tq.limit(6))]
    threads = [{"id": t.id, "title": t.title, "kind": t.kind, "ticker": t.primary_ticker} for t in db.scalars(
        select(Thread).where(Thread.hidden.is_(False), or_(func.lower(Thread.title).like(like),
                                                            func.lower(func.coalesce(Thread.primary_ticker, "")) == q.strip().lower()))
        .order_by(Thread.last_activity_at.desc()).limit(6))]
    return {"q": q, "tickers": tickers, "articles": articles, "themes": themes, "analysis": threads}


# ── themes ───────────────────────────────────────────────────────────────────────────────────────
PESTEL: dict[str, tuple[str, str]] = {
    "political": ("Political", "(tariff OR sanctions OR election OR \"export controls\" OR government OR geopolitical)"),
    "economic": ("Economic", "(inflation OR \"interest rates\" OR recession OR demand OR earnings OR pricing)"),
    "social": ("Social", "(consumers OR workforce OR labor OR demographic OR adoption OR boycott)"),
    "technological": ("Technological", "(AI OR innovation OR patent OR breakthrough OR launch OR disruption)"),
    "environmental": ("Environmental", "(climate OR emissions OR ESG OR drought OR carbon OR sustainability)"),
    "legal": ("Legal", "(lawsuit OR antitrust OR regulation OR regulator OR SEC OR fine OR settlement)"),
}


def _theme_out(t: ResearchTheme, user: User | None = None, pinned: set[str] | None = None) -> dict[str, Any]:
    return {"slug": t.slug, "name": t.name, "description": t.description, "tickers": t.tickers, "keywords": t.keywords,
            "drivers": t.drivers, "custom": t.owner_id is not None, "mine": bool(user and t.owner_id == user.id),
            "notes_md": t.notes_md if user and t.owner_id == user.id else None, "public": t.public,
            "pinned": bool(pinned and t.slug in pinned)}


def _pinned(db: Session, user: User | None, kind: str) -> set[str]:
    if not user:
        return set()
    return set(db.scalars(select(Pin.ref).where(Pin.user_id == user.id, Pin.kind == kind)))


def _get_theme(db: Session, slug: str, user: User | None) -> ResearchTheme:
    t = db.scalar(select(ResearchTheme).where(ResearchTheme.slug == slug))
    if not t or (not t.public and (not user or t.owner_id != user.id)):
        raise HTTPException(404, "Theme not found")
    return t


@router.get("/themes")
def themes(user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    pins = _pinned(db, user, "theme")
    q = select(ResearchTheme).where(or_(ResearchTheme.owner_id.is_(None), ResearchTheme.owner_id == (user.id if user else -1)))
    rows = [_theme_out(t, user, pins) for t in db.scalars(q.order_by(ResearchTheme.owner_id.is_(None), ResearchTheme.name))]
    rows.sort(key=lambda r: (not r["pinned"], not r["mine"], r["name"]))
    return rows


@router.get("/themes/{slug}")
def theme(slug: str, bench: str = Query("SPY", pattern="^(SPY|QQQ|IWM|DIA|ACWI|VT)$"),
          user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    """Theme dashboard: constituents with returns/risk/valuation, an equal-weight theme index vs SPY,
    breadth, dispersion, correlation, leaders/laggards, driver readings and buzz."""
    t = _get_theme(db, slug, user)
    out = _theme_out(t, user, _pinned(db, user, "theme"))
    syms = t.tickers[:25]
    out.update(theme_analytics(syms, bench))
    buzz = {b.symbol: b for b in db.scalars(select(BuzzSnapshot).where(BuzzSnapshot.symbol.in_(syms))).all()} if syms else {}
    for r in out["constituents"]:
        b = buzz.get(r["symbol"])
        r["buzz"] = {"score": b.score, "level": b.level} if b else None
    drivers = []
    for d in t.drivers:
        reading = None
        if d.get("symbol"):
            try:
                c = service.chart(d["symbol"], "1y")
                q = c["quote"]
                rr = research._returns(c["history"])
                reading = {"symbol": d["symbol"], "price": q.get("price"), "change_pct": q.get("change_pct"), "source": q.get("source"),
                           "ret_1m": rr.get("1m"), "ret_3m": rr.get("3m"),
                           "spark": [h["close"] for h in c["history"][-63:]]}
            except Exception:  # noqa: BLE001
                pass
        drivers.append({**d, "reading": reading})
    out["drivers"] = drivers
    return out


def _corr(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 30:
        return None
    a, b = a[-n:], b[-n:]
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if not va or not vb:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def _rets_by_date(hist: list[dict]) -> dict[str, float]:
    out, prev = {}, None
    for h in hist:
        c = h.get("close")
        if c and prev:
            out[h["date"]] = c / prev - 1
        prev = c or prev
    return out


def theme_analytics(syms: list[str], bench: str = "SPY") -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor

    def load(sym: str):
        try:
            c = service.chart(sym, "1y")
        except Exception:  # noqa: BLE001
            return None
        try:
            info = service.info(sym)
        except Exception:  # noqa: BLE001
            info = {}
        return sym, c, info

    with ThreadPoolExecutor(max_workers=4) as ex:
        loaded = [x for x in ex.map(load, [*syms, bench]) if x]
    bench_row = next((x for x in loaded if x[0] == bench), None)
    loaded = [x for x in loaded if x[0] in syms]
    rows, daily = [], {}
    for sym, c, info in loaded:
        closes = [h["close"] for h in c["history"] if h.get("close")]
        q = c["quote"]
        rr = research._returns(c["history"])
        sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
        sma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else None
        hi = max(closes[-252:]) if closes else None
        daily[sym] = _rets_by_date(c["history"])
        rows.append({"symbol": sym, "name": info.get("name") or q.get("name"), "price": q.get("price"), "change_pct": q.get("change_pct"),
                     "ret_1m": rr["1m"], "ret_3m": rr["3m"], "ret_ytd": _ytd(c["history"]), "ret_1y": rr["12m"],
                     "volatility": rr["volatility"], "max_drawdown": rr["max_drawdown"],
                     "from_high": (closes[-1] / hi - 1) if hi else None,
                     "above_50d": bool(sma50 and closes and closes[-1] > sma50), "above_200d": bool(sma200 and closes and closes[-1] > sma200),
                     "market_cap": info.get("market_cap"), "forward_pe": info.get("forward_pe"), "ev_ebitda": info.get("ev_ebitda"),
                     "revenue_growth": info.get("revenue_growth"), "operating_margin": info.get("operating_margin"),
                     "dividend_yield": info.get("dividend_yield"), "beta": info.get("beta"), "sector": info.get("sector"),
                     "source": q.get("source")})
    # equal-weight index (daily rebalanced) on common dates, rebased to 100
    dates = sorted(set().union(*[set(d) for d in daily.values()])) if daily else []
    idx, level = [], 100.0
    for d in dates:
        rs = [daily[s][d] for s in daily if d in daily[s]]
        if len(rs) >= max(1, len(daily) // 2):
            level *= 1 + statistics.fmean(rs)
            idx.append({"date": d, "theme": round(level, 3)})
    bench_out = None
    if bench_row and idx:
        bh = {h["date"]: h["close"] for h in bench_row[1]["history"] if h.get("close")}
        base = next((bh[p["date"]] for p in idx if p["date"] in bh), None)
        for p in idx:
            if base and p["date"] in bh:
                p["bench"] = round(bh[p["date"]] / base * 100, 3)
        bclose = [h["close"] for h in bench_row[1]["history"] if h.get("close")]
        br = research._returns(bench_row[1]["history"])
        bench_out = {"symbol": bench, "ret_1m": br["1m"], "ret_3m": br["3m"], "ret_ytd": _ytd(bench_row[1]["history"]), "ret_1y": br["12m"],
                     "volatility": br["volatility"], "max_drawdown": br["max_drawdown"], "source": bench_row[1]["quote"].get("source"), "last": bclose[-1] if bclose else None}

    def idx_ret(n: int | None = None, ytd: bool = False):
        if not idx:
            return None
        if ytd:
            y = str(dt.date.today().year)
            prior = [p for p in idx if p["date"] < y]
            return idx[-1]["theme"] / prior[-1]["theme"] - 1 if prior else None
        return idx[-1]["theme"] / idx[-1 - n]["theme"] - 1 if len(idx) > n else None

    ir = [b / a - 1 for a, b in zip([p["theme"] for p in idx], [p["theme"] for p in idx][1:])]
    peak, mdd = 0.0, 0.0
    for p in idx:
        peak = max(peak, p["theme"])
        mdd = min(mdd, p["theme"] / peak - 1)
    theme_stats = {"ret_1m": idx_ret(21), "ret_3m": idx_ret(63), "ret_ytd": idx_ret(ytd=True), "ret_1y": idx_ret(250),
                   "volatility": statistics.pstdev(ir) * math.sqrt(252) if len(ir) > 20 else None, "max_drawdown": mdd if idx else None}
    if bench_row and len(ir) > 30:
        bd = _rets_by_date(bench_row[1]["history"])
        pairs = [(r, bd[p["date"]]) for r, p in zip(ir, idx[1:]) if p["date"] in bd]
        if len(pairs) > 30:
            xs, ys = [b for _, b in pairs], [a for a, _ in pairs]
            vb = statistics.pvariance(xs)
            theme_stats["beta_vs_bench"] = (sum((x - statistics.fmean(xs)) * (y - statistics.fmean(ys)) for x, y in pairs) / len(pairs) / vb) if vb else None
            theme_stats["corr_vs_bench"] = _corr(ys, xs)
    # average pairwise correlation over the last 6 months (diversification inside the theme)
    keys = list(daily)
    recent = dates[-126:]
    cors = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a = [daily[keys[i]][d] for d in recent if d in daily[keys[i]] and d in daily[keys[j]]]
            b = [daily[keys[j]][d] for d in recent if d in daily[keys[i]] and d in daily[keys[j]]]
            c = _corr(a, b)
            if c is not None:
                cors.append(c)

    def med(k: str):
        v = [r[k] for r in rows if r.get(k) is not None and not (k in ("forward_pe", "ev_ebitda") and r[k] <= 0)]
        return statistics.median(v) if v else None

    m1 = [r["ret_1m"] for r in rows if r["ret_1m"] is not None]
    ranked = sorted([r for r in rows if r["ret_1m"] is not None], key=lambda r: r["ret_1m"], reverse=True)
    caps = sum(r["market_cap"] or 0 for r in rows)
    return {
        "constituents": rows,
        "breadth": {"above_50d_pct": (sum(r["above_50d"] for r in rows) / len(rows)) if rows else None,
                    "above_200d_pct": (sum(r["above_200d"] for r in rows) / len(rows)) if rows else None,
                    "advancing_pct": (sum(1 for r in rows if (r["change_pct"] or 0) > 0) / len(rows)) if rows else None,
                    "median_1m": statistics.median(m1) if m1 else None,
                    "dispersion_1m": (statistics.pstdev(m1) if len(m1) > 2 else None), "count": len(rows)},
        "index": {"series": idx, "stats": theme_stats, "bench": bench_out,
                  "method": "Equal-weight, rebalanced daily, rebased to 100 one year ago. Benchmark rebased on the same date."},
        "correlation": {"avg_pairwise_6m": statistics.fmean(cors) if cors else None, "pairs": len(cors)},
        "valuation": {"median_forward_pe": med("forward_pe"), "median_ev_ebitda": med("ev_ebitda"), "median_revenue_growth": med("revenue_growth"),
                      "median_operating_margin": med("operating_margin"), "median_dividend_yield": med("dividend_yield"),
                      "total_market_cap": caps or None},
        "leaders": [{"symbol": r["symbol"], "ret_1m": r["ret_1m"]} for r in ranked[:3]],
        "laggards": [{"symbol": r["symbol"], "ret_1m": r["ret_1m"]} for r in ranked[-3:][::-1]] if len(ranked) > 3 else [],
        "sectors": _sector_mix(rows),
    }


def _when(v: Any) -> str | None:
    """RSS pubDate (RFC 822) or GDELT seendate (20261120T153000Z) → ISO 8601."""
    from email.utils import parsedate_to_datetime

    if not v:
        return None
    try:
        return parsedate_to_datetime(str(v)).astimezone(dt.timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
    try:
        return dt.datetime.strptime(str(v), "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc).isoformat()
    except ValueError:
        return None


def _sector_mix(rows: list[dict]) -> list[dict]:
    mix: dict[str, int] = {}
    for r in rows:
        mix[r.get("sector") or "ETF / other"] = mix.get(r.get("sector") or "ETF / other", 0) + 1
    return [{"sector": k, "count": v} for k, v in sorted(mix.items(), key=lambda kv: -kv[1])]


@router.get("/themes/{slug}/news")
def theme_news(slug: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    """Merged headline feed for the theme's largest constituents plus upcoming earnings dates (catalysts)."""
    from concurrent.futures import ThreadPoolExecutor

    t = _get_theme(db, slug, user)
    syms = t.tickers[:10]

    def one(sym: str):
        try:
            hs = research.headlines(sym, limit=6)
        except Exception:  # noqa: BLE001
            hs = []
        nxt = None
        try:
            e = fundamentals.earnings(sym)
            nxt = next((x for x in reversed(e.get("quarterly") or []) if x.get("upcoming")), None)
        except Exception:  # noqa: BLE001
            pass
        return sym, hs, nxt

    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(one, syms))
    seen, items = set(), []
    for sym, hs, _ in res:
        for h in hs:
            key = (h.get("title") or "").strip().lower()[:90]
            if key and key not in seen:
                seen.add(key)
                items.append({**h, "symbol": sym})
    for h in items:
        h["published_iso"] = _when(h.get("published"))
    items.sort(key=lambda h: h["published_iso"] or "", reverse=True)
    cats = sorted([{"symbol": s, "date": n.get("date"), "eps_estimate": n.get("eps_estimate")} for s, _, n in res if n and n.get("date")],
                  key=lambda c: str(c["date"]))
    return {"slug": slug, "headlines": items[:30], "catalysts": cats, "source": "LIVE" if settings.live else "DEMO",
            "provider": {"label": "Yahoo Finance RSS and GDELT (headlines); Yahoo Finance (earnings calendar)", "url": None},
            "as_of": dt.datetime.now(dt.timezone.utc).isoformat()}


def _ytd(hist: list[dict]) -> float | None:
    y = str(dt.date.today().year)
    prior = [h for h in hist if h["date"] < y]
    return hist[-1]["close"] / prior[-1]["close"] - 1 if prior and hist else None


PESTEL_TTL_H = 6


def compute_pestel(t: ResearchTheme) -> dict[str, Any]:
    """Query GDELT for each PESTEL factor (volume + headlines) plus one theme-level tone series.
    GDELT is slow and throttles bursts, so calls run 3 at a time and results are cached on the theme."""
    from concurrent.futures import ThreadPoolExecutor

    base = " OR ".join(f'"{k}"' if " " in k else k for k in (t.keywords or [t.name]))
    base = f"({base})" if " OR " in base else base

    def one(key: str) -> dict[str, Any]:
        label, terms = PESTEL[key]
        q = f"{base} {terms} sourcelang:english"
        try:
            vol = research._gdelt({"query": q, "mode": "timelinevolraw", "timespan": "30d"})
            arts = research._gdelt({"query": q, "mode": "artlist", "maxrecords": "5", "sort": "hybridrel", "timespan": "7d"})
        except Exception as e:  # noqa: BLE001
            return {"key": key, "label": label, "attention": None, "tone": None, "error": type(e).__name__, "headlines": []}
        series = research.parse_gdelt_timeline(vol)
        recent, norm = (sum(series[-7:]) / 7, statistics.mean(series[:-7])) if len(series) > 14 else (None, None)
        return {"key": key, "label": label, "articles_7d_avg": recent, "articles_30d_avg": norm,
                "attention": (recent / norm) if recent is not None and norm else None, "tone": None,
                "headlines": [{"title": a.get("title"), "url": a.get("url"), "domain": a.get("domain"), "seen": a.get("seendate")}
                              for a in (arts.get("articles") or [])[:5]]}

    with ThreadPoolExecutor(max_workers=3) as ex:
        factors = list(ex.map(one, PESTEL))
    try:
        tones = research.parse_gdelt_timeline(research._gdelt({"query": f"{base} sourcelang:english", "mode": "timelinetone", "timespan": "7d"}))
        theme_tone = statistics.mean(tones) if tones else None
    except Exception:  # noqa: BLE001
        theme_tone = None
    return {"slug": t.slug, "factors": factors, "theme_tone": theme_tone, "source": "LIVE",
            "provider": {"label": "GDELT Project (open news data)", "url": "https://www.gdeltproject.org/"},
            "note": "Attention 1.0 = normal news flow for this theme and factor; above 1.5 is unusually active. Tone is GDELT's "
                    "average article tone for the theme over 7 days, roughly −10 (negative) to +10 (positive).",
            "computed_at": dt.datetime.now(dt.timezone.utc).isoformat()}


def pestel_fresh(t: ResearchTheme) -> bool:
    at = t.pestel_at
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=dt.timezone.utc)
    return bool(t.pestel and at and dt.datetime.now(dt.timezone.utc) - at < dt.timedelta(hours=PESTEL_TTL_H))


@router.get("/themes/{slug}/pestel")
def theme_pestel(slug: str, refresh: bool = False, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    """PESTEL radar from GDELT, cached on the theme for 6 hours (the worker refreshes curated themes)."""
    t = _get_theme(db, slug, user)
    if not settings.live:
        return {"slug": slug, "source": "DEMO", "theme_tone": None, "provider": {"label": "GDELT Project (open news data)", "url": "https://www.gdeltproject.org/"},
                "factors": [{"key": k, "label": lab, "attention": None, "tone": None, "headlines": []} for k, (lab, _) in PESTEL.items()]}
    if t.pestel and (pestel_fresh(t) or not (refresh and user and t.owner_id == user.id)):
        return {**t.pestel, "cached_at": t.pestel_at.isoformat() if t.pestel_at else None, "stale": not pestel_fresh(t)}
    out = compute_pestel(t)
    t.pestel, t.pestel_at = out, dt.datetime.now(dt.timezone.utc)
    db.commit()
    return out


class ThemeIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field("", max_length=2000)
    tickers: list[str] = Field(default_factory=list, max_length=40)
    keywords: list[str] = Field(default_factory=list, max_length=8)
    drivers: list[dict[str, str]] = Field(default_factory=list, max_length=15)
    notes_md: str | None = Field(None, max_length=50_000)
    public: bool = False


def _clean_theme(body: ThemeIn) -> dict:
    tick = [t.strip().upper() for t in body.tickers if re.match(r"^[A-Za-z0-9.\-=^]{1,20}$", t.strip())]
    drivers = [{"name": d.get("name", "")[:80], "why": d.get("why", "")[:300], **({"symbol": d["symbol"].upper()[:20]} if d.get("symbol") else {})}
               for d in body.drivers if d.get("name")]
    return {"name": body.name.strip(), "description": body.description.strip(), "tickers": list(dict.fromkeys(tick)),
            "keywords": [k.strip()[:60] for k in body.keywords if k.strip()], "drivers": drivers,
            "notes_md": body.notes_md, "public": body.public}


@router.post("/themes")
def create_theme(body: ThemeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    mine = db.scalar(select(func.count()).select_from(ResearchTheme).where(ResearchTheme.owner_id == user.id)) or 0
    cap = 3 if limits(user).get("monitor_rows") is not None else 50
    if mine >= cap:
        raise HTTPException(402, f"Your plan allows {cap} custom themes")
    base = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:50] or "theme"
    slug = f"u{user.id}-{base}"
    i = 2
    while db.scalar(select(ResearchTheme).where(ResearchTheme.slug == slug)):
        slug, i = f"u{user.id}-{base}-{i}", i + 1
    t = ResearchTheme(slug=slug, owner_id=user.id, **_clean_theme(body))
    db.add(t)
    db.add(Pin(user_id=user.id, kind="theme", ref=slug))
    db.commit()
    return _theme_out(t, user, {slug})


@router.put("/themes/{slug}")
def update_theme(slug: str, body: ThemeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.scalar(select(ResearchTheme).where(ResearchTheme.slug == slug))
    if not t or t.owner_id != user.id:
        raise HTTPException(404, "Theme not found")
    for k, v in _clean_theme(body).items():
        setattr(t, k, v)
    db.commit()
    return _theme_out(t, user, _pinned(db, user, "theme"))


@router.delete("/themes/{slug}")
def delete_theme(slug: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.scalar(select(ResearchTheme).where(ResearchTheme.slug == slug))
    if not t or t.owner_id != user.id:
        raise HTTPException(404, "Theme not found")
    db.delete(t)
    for p in db.scalars(select(Pin).where(Pin.kind == "theme", Pin.ref == slug)):
        db.delete(p)
    db.commit()
    return {"ok": True}


# ── pins ─────────────────────────────────────────────────────────────────────────────────────────
class PinIn(BaseModel):
    kind: str = Field(pattern="^(theme|watchlist|ticker|report|screen)$")
    ref: str = Field(min_length=1, max_length=80)


@router.get("/pins")
def pins(user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = []
    for p in db.scalars(select(Pin).where(Pin.user_id == user.id).order_by(Pin.created_at.desc())):
        label = p.ref
        if p.kind == "theme":
            t = db.scalar(select(ResearchTheme).where(ResearchTheme.slug == p.ref))
            label = t.name if t else p.ref
        elif p.kind == "watchlist":
            w = db.get(Watchlist, int(p.ref)) if p.ref.isdigit() else None
            if not w or w.user_id != user.id:
                continue
            label = w.name
        out.append({"kind": p.kind, "ref": p.ref, "label": label})
    return out


@router.post("/pins")
def add_pin(body: PinIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ref = body.ref.upper() if body.kind == "ticker" else body.ref
    if not db.scalar(select(Pin).where(Pin.user_id == user.id, Pin.kind == body.kind, Pin.ref == ref)):
        if (db.scalar(select(func.count()).select_from(Pin).where(Pin.user_id == user.id)) or 0) >= 100:
            raise HTTPException(400, "You can pin up to 100 items")
        db.add(Pin(user_id=user.id, kind=body.kind, ref=ref))
        db.commit()
    return pins(user, db)


@router.delete("/pins/{kind}/{ref}")
def remove_pin(kind: str, ref: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for p in db.scalars(select(Pin).where(Pin.user_id == user.id, Pin.kind == kind, Pin.ref.in_((ref, ref.upper())))):
        db.delete(p)
    db.commit()
    return pins(user, db)


# ── compare ──────────────────────────────────────────────────────────────────────────────────────
COMPARE_ROWS = fundamentals.RATIO_KEYS + [("rating", "Irradiance quant rating"), ("valuation", "Valuation grade"),
                                          ("quality", "Quality grade"), ("growth", "Growth grade"), ("momentum", "Momentum grade"),
                                          ("risk", "Risk grade"), ("ret_1y", "1-year return"), ("vol_1y", "Volatility (1y)"),
                                          ("target_upside", "Consensus target vs price"), ("buzz", "Buzz (0-100)")]


def compare_table(symbols: list[str]) -> dict[str, Any]:
    from ..market.source import parallel

    def one(sym: str) -> dict[str, Any]:
        q = service.quote(sym)
        try:
            inf = service.info(sym)
        except Exception:  # noqa: BLE001
            inf = {}
        r = research.ratings(sym)
        cons = research.consensus(sym)
        b = research.buzz(sym, with_headlines=False)
        return {"symbol": sym, "name": inf.get("name") or q.get("name"), "price": q.get("price"), "change_pct": q.get("change_pct"),
                **{k: inf.get(k) for k, _ in fundamentals.RATIO_KEYS},
                "rating": r["overall_grade"], "rating_label": r["overall_label"],
                **{f: r["factors"][f]["grade"] for f in ("valuation", "quality", "growth", "momentum", "risk")},
                "ret_1y": r["returns"]["12m"], "vol_1y": r["returns"]["volatility"], "target_upside": cons["implied_move"],
                "buzz": b["score"], "sector": inf.get("sector"), "industry": inf.get("industry"),
                "source": "DEMO" if "DEMO" in (q.get("source"), inf.get("source")) else q.get("source")}

    res = parallel(one, symbols, workers=5)
    rows = [res[s] for s in symbols if isinstance(res.get(s), dict)]
    missing = [s for s in symbols if not isinstance(res.get(s), dict)]
    return {"symbols": [r["symbol"] for r in rows], "rows": rows, "missing": missing,
            "columns": [{"key": k, "label": lab} for k, lab in COMPARE_ROWS],
            "provider": "Yahoo Finance key statistics; Irradiance quant grades and buzz (computed)",
            "as_of": dt.datetime.now(dt.timezone.utc).isoformat()}


def _rule_based_read(table: dict[str, Any]) -> str:
    """Deterministic comparison summary used when Claude is not configured."""
    rows = table["rows"]
    if not rows:
        return "No data to compare."

    def best(key, reverse=True, fmt=lambda v: f"{v:.2f}"):
        vals = [(r[key], r["symbol"]) for r in rows if isinstance(r.get(key), (int, float))]
        if not vals:
            return None
        v, s = sorted(vals, reverse=reverse)[0]
        return f"{s} ({fmt(v)})"

    lines = ["**Snapshot (rule-based summary)**", ""]
    pct = lambda v: f"{v:.1%}"  # noqa: E731
    for label, key, rev, fmt in [("Cheapest on forward P/E", "forward_pe", False, lambda v: f"{v:.1f}x"),
                                 ("Highest operating margin", "operating_margin", True, pct),
                                 ("Fastest revenue growth", "revenue_growth", True, pct),
                                 ("Strongest 1-year return", "ret_1y", True, pct),
                                 ("Lowest volatility", "vol_1y", False, pct),
                                 ("Most media/market attention", "buzz", True, lambda v: f"{v:.0f}/100")]:
        b = best(key, rev, fmt)
        if b:
            lines.append(f"- {label}: {b}")
    graded = sorted((r for r in rows if r.get("rating")), key=lambda r: research.GRADES.index(r["rating"]), reverse=True)
    if graded:
        lines.append(f"- Highest overall quant grade: {graded[0]['symbol']} ({graded[0]['rating']}, {graded[0]['rating_label']})")
    lines += ["", "Trade-offs: cheaper names often carry lower growth or quality; check whether a valuation gap is explained "
              "by the grades before treating it as an opportunity. Research and education only, not investment advice."]
    return "\n".join(lines)


def ai_read(table: dict[str, Any], question: str | None) -> dict[str, Any]:
    from valuebot.config import settings as vb

    if not vb.llm_enabled:
        return {"engine": "rules", "markdown": _rule_based_read(table),
                "note": "Set ANTHROPIC_API_KEY on the server to have Claude write this comparison."}
    import anthropic

    data = json.dumps({"rows": table["rows"], "columns": table["columns"]}, default=str)[:60_000]
    system = ("You are a buy-side equity analyst writing for sophisticated self-directed investors. Compare the companies "
              "using ONLY the data provided; never invent figures. Cite the metric behind every claim. Structure: 1) one-paragraph "
              "bottom line, 2) valuation vs quality/growth trade-offs, 3) risk and momentum, 4) what would change the picture "
              "(key questions to research), 5) data caveats (missing or DEMO values). Use Markdown with short headers and a "
              "compact table where useful. Do not give buy/sell/hold recommendations, price targets or personalized advice.")
    user = f"Question from the member: {question or 'Compare these companies.'}\n\nData (JSON):\n{data}"
    resp = anthropic.Anthropic(api_key=vb.anthropic_api_key).messages.create(
        model=vb.fast_model, max_tokens=1800, system=system, messages=[{"role": "user", "content": user}])
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return {"engine": "claude", "model": vb.fast_model, "markdown": text}


class CompareIn(BaseModel):
    symbols: list[str] = Field(min_length=2, max_length=8)
    question: str | None = Field(None, max_length=500)
    analysis: bool = True


@router.post("/compare")
def compare(body: CompareIn, user: User | None = Depends(optional_user)):
    syms = list(dict.fromkeys(s.strip().upper() for s in body.symbols if re.match(r"^[A-Za-z0-9.\-=^]{1,20}$", s.strip())))
    if len(syms) < 2:
        raise HTTPException(422, "Give at least two valid symbols")
    if user is None and len(syms) > 3:
        raise HTTPException(401, "Sign in to compare more than three companies")
    table = compare_table(syms)
    if body.analysis:
        if user is None:
            table["analysis"] = {"engine": "rules", "markdown": _rule_based_read(table), "note": "Sign in for the AI-written comparison."}
        else:
            try:
                table["analysis"] = ai_read(table, body.question)
            except Exception as e:  # noqa: BLE001
                table["analysis"] = {"engine": "rules", "markdown": _rule_based_read(table), "note": f"AI unavailable ({type(e).__name__})."}
    return table
