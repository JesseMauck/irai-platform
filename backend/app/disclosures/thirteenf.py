"""Smart Money Trackers: quarterly 13F-HR holdings of well-known managers, straight from SEC EDGAR.

For each tracked manager the two latest 13F-HR reports are read (submissions JSON → filing index → information table
XML), positions are aggregated by CUSIP and put/call, CUSIPs are mapped to tickers (OpenFIGI, then SEC company names),
and quarter-over-quarter changes are derived: new, added, reduced, sold out.

13F reports are filed up to 45 days after quarter end, cover only long US-listed equity positions and options, and are
a snapshot. Research and education only.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CusipMap, Filing13F

log = logging.getLogger("irai.13f")
UA = {"User-Agent": "Irradiance Research support@irradiance.ai"}
MAX_POSITIONS = 150

FUNDS: dict[str, dict[str, Any]] = {
    "berkshire": {"cik": 1067983, "manager": "Warren Buffett", "fund": "Berkshire Hathaway", "style": "Value, concentrated"},
    "pershing": {"cik": 1336528, "manager": "Bill Ackman", "fund": "Pershing Square Capital", "style": "Activist, concentrated"},
    "bridgewater": {"cik": 1350694, "manager": "Ray Dalio (founder)", "fund": "Bridgewater Associates", "style": "Global macro"},
    "duquesne": {"cik": 1536411, "manager": "Stanley Druckenmiller", "fund": "Duquesne Family Office", "style": "Macro, growth"},
    "appaloosa": {"cik": 1656456, "manager": "David Tepper", "fund": "Appaloosa", "style": "Opportunistic, distressed"},
    "baupost": {"cik": 1061768, "manager": "Seth Klarman", "fund": "Baupost Group", "style": "Deep value"},
    "soros": {"cik": 1029160, "manager": "George Soros (founder)", "fund": "Soros Fund Management", "style": "Macro, multi-strategy"},
    "tiger": {"cik": 1167483, "manager": "Chase Coleman", "fund": "Tiger Global Management", "style": "Growth, technology"},
    "coatue": {"cik": 1135730, "manager": "Philippe Laffont", "fund": "Coatue Management", "style": "Technology growth"},
    "lonepine": {"cik": 1061165, "manager": "Stephen Mandel (founder)", "fund": "Lone Pine Capital", "style": "Long/short growth"},
    "viking": {"cik": 1103804, "manager": "Andreas Halvorsen", "fund": "Viking Global Investors", "style": "Long/short fundamental"},
    "thirdpoint": {"cik": 1040273, "manager": "Dan Loeb", "fund": "Third Point", "style": "Event-driven, activist"},
    "elliott": {"cik": 1791786, "manager": "Paul Singer", "fund": "Elliott Investment Management", "style": "Activist, multi-strategy"},
    "icahn": {"cik": 921669, "manager": "Carl Icahn", "fund": "Icahn Enterprises", "style": "Activist"},
    "trian": {"cik": 1345471, "manager": "Nelson Peltz", "fund": "Trian Fund Management", "style": "Activist"},
    "valueact": {"cik": 1418814, "manager": "Mason Morfit", "fund": "ValueAct Capital", "style": "Activist value"},
    "ark": {"cik": 1697748, "manager": "Cathie Wood", "fund": "ARK Investment Management", "style": "Disruptive innovation"},
    "baron": {"cik": 1017918, "manager": "Ron Baron", "fund": "Baron Capital (BAMCO)", "style": "Long-term growth"},
    "davis": {"cik": 1036325, "manager": "Chris Davis", "fund": "Davis Selected Advisers", "style": "Quality value"},
    "ariel": {"cik": 936753, "manager": "John Rogers", "fund": "Ariel Investments", "style": "Small/mid value"},
    "paulson": {"cik": 1035674, "manager": "John Paulson", "fund": "Paulson & Co.", "style": "Event-driven"},
    "renaissance": {"cik": 1037389, "manager": "Jim Simons (founder)", "fund": "Renaissance Technologies", "style": "Quantitative"},
    "citadel": {"cik": 1423053, "manager": "Ken Griffin", "fund": "Citadel Advisors", "style": "Multi-strategy"},
    "scion": {"cik": 1649339, "manager": "Michael Burry", "fund": "Scion Asset Management", "style": "Contrarian value"},
}
_lock = threading.Lock()


def _get(c: httpx.Client, url: str) -> httpx.Response:
    for i in range(3):
        r = c.get(url)
        if r.status_code != 429:
            r.raise_for_status()
            return r
        time.sleep(1.5 * (i + 1))
    r.raise_for_status()
    return r


def latest_filings(c: httpx.Client, cik: int, n: int = 2) -> list[dict[str, Any]]:
    j = _get(c, f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()
    f = j["filings"]["recent"]
    rows = [{"form": f["form"][i], "period": f["reportDate"][i], "filed": f["filingDate"][i], "accession": f["accessionNumber"][i]}
            for i in range(len(f["form"])) if f["form"][i] in ("13F-HR", "13F-HR/A")]
    out, seen = [], set()
    for r in rows:  # newest first; prefer the original over an amendment for the same period unless only the amendment exists
        if r["period"] in seen:
            continue
        seen.add(r["period"])
        out.append(r)
        if len(out) >= n:
            break
    return out


def parse_info_table(xml: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml)
    ns = {"n": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {"n": ""}
    pre = "n:" if ns["n"] else ""
    agg: dict[tuple[str, str], dict[str, Any]] = {}
    for it in root.findall(f"{pre}infoTable", ns):
        g = lambda p: (it.findtext(p, namespaces=ns) or "").strip()  # noqa: E731
        cusip, pc = g(f"{pre}cusip").upper(), g(f"{pre}putCall").lower()
        k = (cusip, pc)
        row = agg.setdefault(k, {"cusip": cusip, "name": g(f"{pre}nameOfIssuer"), "class": g(f"{pre}titleOfClass"), "put_call": pc or None, "value": 0.0, "shares": 0.0})
        row["value"] += float(g(f"{pre}value") or 0)
        row["shares"] += float(g(f"{pre}shrsOrPrnAmt/{pre}sshPrnamt") or 0)
    return sorted(agg.values(), key=lambda r: -r["value"])


def info_table(c: httpx.Client, cik: int, accession: str) -> list[dict[str, Any]]:
    acc = accession.replace("-", "")
    ix = _get(c, f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json").json()
    names = [x["name"] for x in ix["directory"]["item"] if x["name"].lower().endswith(".xml") and x["name"] != "primary_doc.xml"]
    if not names:
        raise LookupError("no information table")
    rows = parse_info_table(_get(c, f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{names[0]}").text)
    reported = None
    try:
        m = re.search(r"<(?:\w+:)?tableValueTotal>\s*([\d.]+)", _get(c, f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/primary_doc.xml").text)
        reported = float(m.group(1)) if m else None
    except Exception:  # noqa: BLE001
        pass
    return scale_values(rows, reported)


def scale_values(rows: list[dict[str, Any]], reported_total: float | None) -> list[dict[str, Any]]:
    """Some filers still report values in thousands. Detect it from the cover-page total, else from implied share prices."""
    s = sum(r["value"] for r in rows)
    thousands = False
    if reported_total and s:
        thousands = abs(s * 1000 / reported_total - 1) < 0.02 and abs(s / reported_total - 1) > 0.02
    if not thousands:
        px = sorted(r["value"] / r["shares"] for r in rows if r["shares"] and not r.get("put_call"))
        thousands = bool(px) and px[len(px) // 2] < 0.5  # a median "price" under 50 cents means the values are in $000s
    if thousands:
        for r in rows:
            r["value"] *= 1000
    return rows


def _norm(n: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", " ", n.lower())
    n = re.sub(r"\b(inc|corp|corporation|co|company|ltd|limited|plc|com|new|del|the|holdings?|group|cl [a-z]|class [a-z]|sa|nv|ag|lp|llc)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _safe_commit(db: Session) -> bool:
    """Commit, tolerating a concurrent writer that already stored the same row (unique constraints)."""
    from sqlalchemy.exc import IntegrityError

    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def map_cusips(db: Session, c: httpx.Client, rows: list[dict[str, Any]]) -> dict[str, str | None]:
    need = sorted({r["cusip"] for r in rows if r["cusip"]})
    known = {m.cusip: m.ticker for m in db.scalars(select(CusipMap).where(CusipMap.cusip.in_(need)))}
    todo = [x for x in need if x not in known]
    names = {r["cusip"]: r["name"] for r in rows}
    for i in range(0, len(todo), 10):
        batch = todo[i:i + 10]
        try:
            r = c.post("https://api.openfigi.com/v3/mapping", json=[{"idType": "ID_CUSIP", "idValue": x} for x in batch], timeout=30)
            if r.status_code == 429:
                time.sleep(6)
                r = c.post("https://api.openfigi.com/v3/mapping", json=[{"idType": "ID_CUSIP", "idValue": x} for x in batch], timeout=30)
            res = r.json() if r.status_code == 200 else [{} for _ in batch]
        except Exception:  # noqa: BLE001
            res = [{} for _ in batch]
        for cu, d in zip(batch, res):
            data = d.get("data") or []
            pick = next((x for x in data if x.get("exchCode") == "US"), data[0] if data else None)
            t = (pick or {}).get("ticker")
            known[cu] = t.replace("/", "-").replace(" ", "-")[:16] if t else None
            db.merge(CusipMap(cusip=cu, ticker=known[cu], name=(names.get(cu) or "")[:200], source="openfigi" if t else "none"))
        _safe_commit(db)
        time.sleep(2.6)  # OpenFIGI's keyless limit is 25 requests a minute
    missing = [cu for cu, t in known.items() if not t]
    if missing:
        try:
            ct = _get(c, "https://www.sec.gov/files/company_tickers.json").json()
            by = {}
            for v in ct.values():
                by.setdefault(_norm(v["title"]), v["ticker"])
            for cu in missing:
                t = by.get(_norm(names.get(cu) or ""))
                if t:
                    known[cu] = t[:16]
                    db.merge(CusipMap(cusip=cu, ticker=t[:16], name=(names.get(cu) or "")[:200], source="sec-name"))
            _safe_commit(db)
        except Exception:  # noqa: BLE001
            pass
    return known


def refresh(db: Session, keys: list[str] | None = None) -> dict[str, Any]:
    stats = {"funds": 0, "new_filings": 0, "errors": []}
    with httpx.Client(headers=UA, timeout=40, follow_redirects=True) as c:
        for key in keys or list(FUNDS):
            f = FUNDS[key]
            try:
                for fl in latest_filings(c, f["cik"]):
                    if db.scalar(select(Filing13F.id).where(Filing13F.accession == fl["accession"])):
                        continue
                    rows = info_table(c, f["cik"], fl["accession"])
                    total = sum(r["value"] for r in rows)
                    top = rows[:MAX_POSITIONS]
                    tick = map_cusips(db, c, top)
                    for r in top:
                        r["ticker"] = tick.get(r["cusip"])
                        r["weight"] = r["value"] / total if total else None
                    db.add(Filing13F(fund_key=key, cik=f["cik"], period=dt.date.fromisoformat(fl["period"]), filed=dt.date.fromisoformat(fl["filed"]),
                                     accession=fl["accession"], total_value=total, positions=len(rows), holdings=top))
                    if _safe_commit(db):
                        stats["new_filings"] += 1
                    time.sleep(0.25)
                stats["funds"] += 1
            except Exception as e:  # noqa: BLE001
                db.rollback()
                stats["errors"].append(f"{key}: {type(e).__name__}")
                log.warning("13f %s: %s", key, e)
            time.sleep(0.2)
    log.info("13f refresh %s", json.dumps(stats))
    return stats


# ── derived views ────────────────────────────────────────────────────────────────────────────────
def _hkey(h: dict[str, Any]) -> str:
    return f"{h['cusip']}:{h.get('put_call') or ''}"


def compare(cur: Filing13F, prev: Filing13F | None) -> list[dict[str, Any]]:
    pm = {_hkey(h): h for h in (prev.holdings if prev else [])}
    out = []
    for h in cur.holdings:
        p = pm.pop(_hkey(h), None)
        if p is None:
            status, chg = ("new" if prev else None), None
        else:
            chg = h["shares"] / p["shares"] - 1 if p["shares"] else None
            status = "added" if chg and chg > 0.02 else "reduced" if chg and chg < -0.02 else "unchanged"
        out.append({**h, "status": status, "shares_change": chg, "prev_shares": p["shares"] if p else None, "prev_weight": p.get("weight") if p else None})
    if prev and prev.total_value:  # positions that were in last quarter's top list but are gone now
        cur_all = {_hkey(h) for h in cur.holdings}
        for k, p in pm.items():
            if k not in cur_all and cur.positions < MAX_POSITIONS:  # only certain when we saw the full current list
                out.append({**p, "value": 0.0, "shares": 0.0, "weight": 0.0, "status": "sold_out", "shares_change": -1.0, "prev_shares": p["shares"], "prev_weight": p.get("weight")})
    return out


def latest_pair(db: Session, key: str) -> tuple[Filing13F | None, Filing13F | None]:
    rows = db.scalars(select(Filing13F).where(Filing13F.fund_key == key).order_by(Filing13F.period.desc(), Filing13F.filed.desc())).all()
    uniq = []
    for r in rows:
        if not uniq or r.period != uniq[-1].period:
            uniq.append(r)
    return (uniq[0] if uniq else None), (uniq[1] if len(uniq) > 1 else None)


_last: dict[str, float] = {"at": 0.0}


def due() -> bool:
    return time.time() - _last["at"] > 12 * 3600


def start_background() -> bool:
    if _lock.locked():
        return False
    _last["at"] = time.time()

    def go():
        from ..db import SessionLocal

        with _lock, SessionLocal() as db:
            try:
                refresh(db)
            except Exception:  # noqa: BLE001
                log.exception("13f refresh failed")

    threading.Thread(target=go, daemon=True, name="13f").start()
    return True
