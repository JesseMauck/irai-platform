"""The data Cycle: ingestion → exploration & profiling → cleaning → feature engineering → splitting & versioning →
monitoring & feedback. Runs nightly in the worker; each run writes a DatasetVersion with its quality report, time
splits, feature statistics and drift against the previous version. Pattern engines (regimes, lead-lag, market
states) read the cleaned panel this produces, and the weekly code-improvement agent reads its reports."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..market import service
from ..models import DatasetVersion

log = logging.getLogger("irai.datapipe")
EQUITIES = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "JPM", "BAC", "XOM", "CVX",
            "UNH", "JNJ", "LLY", "PG", "KO", "WMT", "COST", "HD", "CAT", "GE", "V", "MA", "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "SMH"]
MACRO = ["TLT", "IEF", "HYG", "LQD", "GLD", "SLV", "USO", "UUP", "EFA", "EEM", "FXI", "EWJ", "^VIX", "^TNX", "DX-Y.NYB", "CL=F", "GC=F", "HG=F", "BTC-USD", "ETH-USD"]
UNIVERSE = EQUITIES + MACRO
RANGE = "5y"
FEATURES = ["ret_1d", "ret_5d", "ret_21d", "ret_63d", "vol_21d", "vol_63d", "rsi_14", "dist_sma50", "dist_sma200", "drawdown_252", "zret_1d"]
SPLIT = (0.70, 0.15, 0.15)  # train / validation / test, in time order (no shuffling: avoids look-ahead)
_lock = threading.Lock()
_panel_cache: dict[str, Any] = {}


# ── 1. ingestion ─────────────────────────────────────────────────────────────────────────────────
def ingest(universe: list[str]) -> dict[str, dict[str, Any]]:
    def one(sym: str):
        try:
            c = service.chart(sym, RANGE)
            return sym, {"history": c["history"], "source": c["quote"].get("source")}
        except Exception as e:  # noqa: BLE001
            return sym, {"history": [], "source": None, "error": f"{type(e).__name__}: {e}"[:200]}

    with ThreadPoolExecutor(max_workers=4) as ex:
        return dict(ex.map(one, universe))


# ── 2. exploration & profiling ───────────────────────────────────────────────────────────────────
def _bdays(a: str, b: str) -> int:
    return int(np.busday_count(a, b)) if a < b else 0


def profile(sym: str, hist: list[dict]) -> dict[str, Any]:
    dates = [h.get("date") for h in hist]
    closes = [h.get("close") for h in hist]
    n = len(hist)
    p: dict[str, Any] = {"symbol": sym, "rows": n, "first": dates[0] if n else None, "last": dates[-1] if n else None}
    if n < 2:
        return {**p, "quality": 0.0, "issues": ["no data"]}
    dup = n - len(set(dates))
    nonpos = sum(1 for c in closes if c is None or not math.isfinite(c) or c <= 0)
    good = [c for c in closes if c and math.isfinite(c) and c > 0]
    rets = np.diff(np.log(np.array(good))) if len(good) > 2 else np.array([])
    sd = float(np.std(rets)) if rets.size > 5 else 0.0
    outliers = int(np.sum(np.abs(rets) > max(8 * sd, 0.25))) if sd else 0
    jumps = int(np.sum(np.abs(rets) > 0.4))  # possible unadjusted split or bad tick
    flat = max((len(list(g)) for g in _runs(closes)), default=0)
    expected = _bdays(dates[0], dates[-1]) + 1
    missing = max(0, expected - n) if not sym.endswith("-USD") else 0  # crypto trades every day
    stale_days = _bdays(dates[-1], dt.date.today().isoformat())
    issues = []
    if dup:
        issues.append(f"{dup} duplicate dates")
    if nonpos:
        issues.append(f"{nonpos} missing or non-positive closes")
    if missing > expected * 0.03:
        issues.append(f"{missing} missing business days")
    if outliers:
        issues.append(f"{outliers} extreme returns (>8σ)")
    if jumps:
        issues.append(f"{jumps} moves over 40% (check splits)")
    if flat >= 5:
        issues.append(f"price unchanged for {flat} sessions")
    if stale_days > 3:
        issues.append(f"last bar {stale_days} business days old")
    q = 1.0 - min(1, dup / n) * 0.2 - min(1, nonpos / n) * 0.3 - min(1, missing / max(expected, 1)) * 0.2 \
        - min(1, outliers / 5) * 0.1 - min(1, jumps) * 0.1 - (0.1 if flat >= 5 else 0) - min(0.3, stale_days * 0.03)
    return {**p, "duplicates": dup, "non_positive": nonpos, "missing_bdays": missing, "outliers": outliers, "jumps": jumps,
            "longest_flat": flat, "stale_bdays": stale_days, "daily_vol": sd, "quality": round(max(0.0, q), 3), "issues": issues}


def _runs(xs):
    cur = []
    for x in xs:
        if cur and x == cur[-1]:
            cur.append(x)
        else:
            if cur:
                yield cur
            cur = [x]
    if cur:
        yield cur


# ── 3. cleaning ──────────────────────────────────────────────────────────────────────────────────
def clean(hist: list[dict], max_fill: int = 3) -> tuple[list[str], np.ndarray, dict[str, int]]:
    """Dedupe (last value wins), drop non-positive, forward-fill gaps of up to `max_fill` business days, and
    winsorise single-bar spikes that fully reverse the next bar (bad ticks). Returns dates, closes, actions."""
    by: dict[str, float] = {}
    for h in hist:
        c = h.get("close")
        if h.get("date") and c and math.isfinite(c) and c > 0:
            by[h["date"]] = float(c)
    dates = sorted(by)
    acts = {"filled": 0, "spikes_fixed": 0}
    if len(dates) < 3:
        return dates, np.array([by[d] for d in dates]), acts
    out_d, out_c = [dates[0]], [by[dates[0]]]
    for d in dates[1:]:
        gap = _bdays(out_d[-1], d) - 1
        if 0 < gap <= max_fill:
            for fd in np.busday_offset(out_d[-1], np.arange(1, gap + 1), roll="forward").astype(str):
                if fd < d:
                    out_d.append(str(fd))
                    out_c.append(out_c[-1])
                    acts["filled"] += 1
        out_d.append(d)
        out_c.append(by[d])
    c = np.array(out_c)
    r = np.diff(np.log(c))
    for i in range(1, len(r)):
        if abs(r[i - 1]) > 0.25 and abs(r[i - 1] + r[i]) < 0.02:  # up then straight back down (or vice versa)
            c[i] = (c[i - 1] + c[i + 1]) / 2
            acts["spikes_fixed"] += 1
    return out_d, c, acts


# ── 4. refinement & feature engineering ─────────────────────────────────────────────────────────
def _rolling(x: np.ndarray, n: int, fn) -> np.ndarray:
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        out[i] = fn(x[i - n + 1:i + 1])
    return out


def features(closes: np.ndarray) -> dict[str, np.ndarray]:
    c = closes
    lr = np.concatenate([[np.nan], np.diff(np.log(c))])

    def ret(k):
        o = np.full(len(c), np.nan)
        o[k:] = c[k:] / c[:-k] - 1
        return o

    vol21 = _rolling(np.nan_to_num(lr), 21, np.std) * math.sqrt(252)
    vol63 = _rolling(np.nan_to_num(lr), 63, np.std) * math.sqrt(252)
    sma50 = _rolling(c, 50, np.mean)
    sma200 = _rolling(c, 200, np.mean)
    peak = np.maximum.accumulate(c)
    d = np.diff(c, prepend=c[0])
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    rsi = np.full(len(c), np.nan)
    if len(c) > 15:
        ag, al = up[1:15].mean(), dn[1:15].mean()
        for i in range(15, len(c)):
            ag, al = (ag * 13 + up[i]) / 14, (al * 13 + dn[i]) / 14
            rsi[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    sd63 = _rolling(np.nan_to_num(lr), 63, np.std)
    return {"ret_1d": ret(1), "ret_5d": ret(5), "ret_21d": ret(21), "ret_63d": ret(63), "vol_21d": vol21, "vol_63d": vol63, "rsi_14": rsi,
            "dist_sma50": c / sma50 - 1, "dist_sma200": c / sma200 - 1, "drawdown_252": c / peak - 1,
            "zret_1d": np.where(sd63 > 0, lr / np.where(sd63 > 0, sd63, 1), np.nan)}


# ── 5. splitting & versioning ────────────────────────────────────────────────────────────────────
def time_splits(dates: list[str]) -> dict[str, dict[str, str]]:
    n = len(dates)
    a, b = int(n * SPLIT[0]), int(n * (SPLIT[0] + SPLIT[1]))
    return {"train": {"start": dates[0], "end": dates[a - 1]}, "validation": {"start": dates[a], "end": dates[b - 1]},
            "test": {"start": dates[b], "end": dates[-1]}, "embargo_days": 5,
            "note": "Chronological splits; leave a 5-day gap between them when training to avoid overlap from multi-day features."}


def _hist(x: np.ndarray, edges: np.ndarray) -> list[float]:
    x = x[np.isfinite(x)]
    if not x.size:
        return [0.0] * (len(edges) + 1)
    counts = np.bincount(np.searchsorted(edges, x), minlength=len(edges) + 1)
    return (counts / counts.sum()).round(5).tolist()


# ── 6. monitoring: drift between versions ───────────────────────────────────────────────────────
def psi(p: list[float], q: list[float]) -> float:
    """Population stability index between two binned distributions (0.1 = notable shift, 0.25 = major)."""
    s = 0.0
    for a, b in zip(p, q):
        a, b = max(a, 1e-4), max(b, 1e-4)
        s += (a - b) * math.log(a / b)
    return round(s, 4)


def build_panel(universe: list[str] | None = None) -> dict[str, Any]:
    """Run stages 1-4 and return the cleaned panel: {symbol: {dates, closes, features}} plus profiles."""
    raw = ingest(universe or UNIVERSE)
    profiles, panel, actions = [], {}, {}
    for sym, r in raw.items():
        pr = profile(sym, r["history"])
        pr["source"] = r.get("source")
        if r.get("error"):
            pr["issues"] = [r["error"], *pr.get("issues", [])]
        profiles.append(pr)
        if pr["quality"] < 0.5 or pr["rows"] < 260:
            continue
        d, c, a = clean(r["history"])
        actions[sym] = a
        panel[sym] = {"dates": d, "closes": c, "features": features(c), "source": r.get("source")}
    return {"panel": panel, "profiles": profiles, "actions": actions}


def run_cycle(db: Session, trigger: str = "schedule") -> DatasetVersion:
    t0 = dt.datetime.now(dt.timezone.utc)
    b = build_panel()
    panel = b["panel"]
    all_dates = sorted({d for p in panel.values() for d in p["dates"]})
    # global feature statistics on fixed bins, for drift tracking
    edges = {"ret_1d": np.linspace(-0.05, 0.05, 11), "ret_21d": np.linspace(-0.2, 0.2, 11), "vol_21d": np.linspace(0, 0.8, 11),
             "rsi_14": np.linspace(10, 90, 9), "dist_sma200": np.linspace(-0.3, 0.3, 13), "zret_1d": np.linspace(-4, 4, 9)}
    recent = {}
    for f, e in edges.items():
        xs = np.concatenate([p["features"][f][-63:] for p in panel.values()]) if panel else np.array([])
        recent[f] = {"hist": _hist(xs, e), "mean": float(np.nanmean(xs)) if xs.size else None, "std": float(np.nanstd(xs)) if xs.size else None}
    prev = db.scalar(select(DatasetVersion).where(DatasetVersion.status == "done").order_by(DatasetVersion.created_at.desc()))
    drift = {}
    if prev and prev.feature_stats:
        for f, st in recent.items():
            p0 = (prev.feature_stats.get(f) or {}).get("hist")
            if p0 and len(p0) == len(st["hist"]):
                v = psi(st["hist"], p0)
                drift[f] = {"psi": v, "level": "major" if v >= 0.25 else "notable" if v >= 0.1 else "stable"}
    prof = b["profiles"]
    qs = [p["quality"] for p in prof]
    content = json.dumps({s: [p["dates"][-1], round(float(p["closes"][-1]), 6), len(p["dates"])] for s, p in sorted(panel.items())})
    version = f"{t0.date().isoformat()}-{hashlib.sha256(content.encode()).hexdigest()[:10]}"
    alerts = [f"{p['symbol']}: {'; '.join(p['issues'])}" for p in prof if p["quality"] < 0.8 and p["issues"]][:30]
    alerts += [f"Feature drift in {f} (PSI {d['psi']})" for f, d in drift.items() if d["level"] == "major"]
    v = DatasetVersion(version=version, trigger=trigger, status="done", universe=sorted(panel),
                       rows=sum(len(p["dates"]) for p in panel.values()),
                       quality={"mean": round(float(np.mean(qs)), 3) if qs else None, "min": min(qs) if qs else None,
                                "included": len(panel), "excluded": [p["symbol"] for p in prof if p["symbol"] not in panel],
                                "profiles": prof, "cleaning": b["actions"]},
                       splits=time_splits(all_dates) if len(all_dates) > 50 else None,
                       feature_stats=recent, drift=drift, alerts=alerts,
                       seconds=round((dt.datetime.now(dt.timezone.utc) - t0).total_seconds(), 1))
    db.add(v)
    db.commit()
    _panel_cache.update({"version": version, "panel": panel, "at": dt.datetime.now(dt.timezone.utc)})
    log.info("datapipe report %s", json.dumps({"version": version, "included": len(panel), "quality": v.quality["mean"],
                                               "alerts": alerts[:10], "drift": {k: d["psi"] for k, d in drift.items()}}))
    return v


def cached_panel(max_age_hours: float = 12) -> dict[str, Any]:
    """The cleaned panel for pattern engines: from this process's last cycle, else rebuilt on demand."""
    at = _panel_cache.get("at")
    if at and (dt.datetime.now(dt.timezone.utc) - at).total_seconds() < max_age_hours * 3600:
        return _panel_cache["panel"]
    b = build_panel()
    _panel_cache.update({"version": "adhoc", "panel": b["panel"], "at": dt.datetime.now(dt.timezone.utc)})
    return b["panel"]


def due(db: Session, now_utc: dt.datetime | None = None) -> bool:
    """Nightly after 22:30 UTC (after the US close), or on first start."""
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    last = db.scalar(select(DatasetVersion.created_at).order_by(DatasetVersion.created_at.desc()))
    if last is None:
        return True
    last = last.replace(tzinfo=dt.timezone.utc) if last.tzinfo is None else last
    return now.time() >= dt.time(22, 30) and last.date() < now.date()


def start_background(trigger: str = "schedule") -> bool:
    if _lock.locked():
        return False

    def go():
        with _lock, SessionLocal() as db:
            try:
                run_cycle(db, trigger)
            except Exception:  # noqa: BLE001
                log.exception("datapipe failed")

    threading.Thread(target=go, daemon=True, name="datapipe").start()
    return True
