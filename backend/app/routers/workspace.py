"""Research workspace: unified search, themes (curated + custom) with drivers and PESTEL radar, pins,
and multi-stock comparison with an AI-written read-through."""
from __future__ import annotations

import datetime as dt
import json
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
from ..models import Article, Pin, ResearchTheme, Thread, User, Watchlist
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
def theme(slug: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    """Theme with live constituents, breadth, driver readings and buzz."""
    t = _get_theme(db, slug, user)
    out = _theme_out(t, user, _pinned(db, user, "theme"))
    rows = []
    for sym in t.tickers[:25]:
        try:
            c = service.chart(sym, "1y")
        except Exception:  # noqa: BLE001
            continue
        closes = [h["close"] for h in c["history"]]
        q = c["quote"]
        sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
        rows.append({"symbol": sym, "name": q.get("name"), "price": q.get("price"), "change_pct": q.get("change_pct"),
                     "ret_1m": closes[-1] / closes[-22] - 1 if len(closes) > 22 else None,
                     "ret_ytd": _ytd(c["history"]), "above_50d": bool(sma50 and q.get("price") and q["price"] > sma50),
                     "source": q.get("source")})
    out["constituents"] = rows
    m1 = [r["ret_1m"] for r in rows if r["ret_1m"] is not None]
    out["breadth"] = {"above_50d_pct": (sum(r["above_50d"] for r in rows) / len(rows)) if rows else None,
                      "median_1m": statistics.median(m1) if m1 else None, "count": len(rows)}
    drivers = []
    for d in t.drivers:
        reading = None
        if d.get("symbol"):
            try:
                q = service.quote(d["symbol"])
                reading = {"symbol": d["symbol"], "price": q.get("price"), "change_pct": q.get("change_pct"), "source": q.get("source")}
            except Exception:  # noqa: BLE001
                pass
        drivers.append({**d, "reading": reading})
    out["drivers"] = drivers
    return out


def _ytd(hist: list[dict]) -> float | None:
    y = str(dt.date.today().year)
    prior = [h for h in hist if h["date"] < y]
    return hist[-1]["close"] / prior[-1]["close"] - 1 if prior and hist else None


@router.get("/themes/{slug}/pestel")
def theme_pestel(slug: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    """PESTEL radar: news attention (7 days vs the 30-day norm), tone and headlines per factor, from GDELT."""
    t = _get_theme(db, slug, user)
    base = " OR ".join(f'"{k}"' if " " in k else k for k in (t.keywords or [t.name]))
    base = f"({base})" if " OR " in base else base
    out: dict[str, Any] = {"slug": slug, "factors": [], "provider": {"label": "GDELT Project (open news data)",
                                                                        "url": "https://www.gdeltproject.org/"}}
    if not settings.live:
        out["factors"] = [{"key": k, "label": lab, "attention": None, "tone": None, "headlines": []} for k, (lab, _) in PESTEL.items()]
        out["source"] = "DEMO"
        return out
    for key, (label, terms) in PESTEL.items():
        query = f"{base} {terms} sourcelang:english"

        def fetch(query=query):
            vol = research._gdelt({"query": query, "mode": "timelinevolraw", "timespan": "30d"})
            tone = research._gdelt({"query": query, "mode": "timelinetone", "timespan": "7d"})
            arts = research._gdelt({"query": query, "mode": "artlist", "maxrecords": "5", "sort": "hybridrel", "timespan": "7d"})
            return vol, tone, arts

        try:
            vol, tone, arts = research._memo("pestel", f"{slug}:{key}", 3 * 3600, fetch)
        except Exception as e:  # noqa: BLE001
            out["factors"].append({"key": key, "label": label, "error": type(e).__name__, "headlines": []})
            continue
        series = research.parse_gdelt_timeline(vol)
        recent, norm = (sum(series[-7:]) / 7, statistics.mean(series[:-7])) if len(series) > 14 else (None, None)
        tones = research.parse_gdelt_timeline(tone)
        out["factors"].append({
            "key": key, "label": label, "articles_7d_avg": recent, "articles_30d_avg": norm,
            "attention": (recent / norm) if recent is not None and norm else None,
            "tone": statistics.mean(tones) if tones else None,
            "headlines": [{"title": a.get("title"), "url": a.get("url"), "domain": a.get("domain"), "seen": a.get("seendate")}
                          for a in (arts.get("articles") or [])[:5]]})
    out["source"] = "LIVE"
    out["note"] = "Attention 1.0 = normal news flow for this theme and factor; above 1.5 is unusually active. Tone ranges roughly −10 to +10."
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
              "by the grades before treating it as an opportunity. Research and education only — not investment advice."]
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
