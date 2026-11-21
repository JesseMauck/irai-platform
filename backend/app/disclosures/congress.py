"""Congressional stock trades from the official disclosures.

* House: the Clerk's yearly index (financial-pdfs/<year>FD.zip, FilingType "P" = Periodic Transaction Report) and each
  electronic PTR PDF, whose transaction table is parsed from the PDF text. Scanned paper filings can't be parsed; they are
  recorded and linked.
* Senate: the eFD search (after accepting its terms of use, as a browser does) for Periodic Transaction Reports, and each
  electronic report's HTML transaction table.
* Party and state come from the public congress-legislators dataset.

Disclosures arrive up to 45 days after the trade and give an amount range, not an exact size. Research and education only.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html as html_lib
import io
import json
import logging
import re
import threading
import time
import zipfile
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CongressTrade, DisclosureDoc

log = logging.getLogger("irai.congress")
UA = {"User-Agent": "Irradiance Research (support@irradiance.ai)"}
HOUSE_INDEX = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
HOUSE_PTR = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc}.pdf"
SENATE = "https://efdsearch.senate.gov"
LEGISLATORS = "https://unitedstates.github.io/congress-legislators/legislators-current.json"
OWNERS = {"SP": "spouse", "JT": "joint", "DC": "dependent", "Self": "self", "Spouse": "spouse", "Joint": "joint", "Child": "dependent"}
TYPES = {"P": "buy", "Purchase": "buy", "S": "sell", "Sale (Full)": "sell", "Sale (Partial)": "sell_partial", "S (partial)": "sell_partial",
         "E": "exchange", "Exchange": "exchange", "Sale": "sell"}
_lock = threading.Lock()


def amount_bounds(a: str) -> tuple[float | None, float | None]:
    nums = [float(x.replace(",", "")) for x in re.findall(r"\$([\d,]+)", a)]
    if not nums:
        return None, None
    if "over" in a.lower():
        return nums[0], None
    return nums[0], nums[-1] if len(nums) > 1 else nums[0]


def _d(s: str | None) -> dt.date | None:
    if not s:
        return None
    for f in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s.strip(), f).date()
        except ValueError:
            pass
    return None


# ── House ────────────────────────────────────────────────────────────────────────────────────────
CORE = re.compile(r"\b(P|S \(partial\)|S|E)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\$[\d,]+\s*-\s*\$[\d,]+|\$[\d,]+|Over \$[\d,]+|Spouse/DC Over \$[\d,]+)")
TICK = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,9})\)\s*\[([A-Z]{2})\]")
NOISE = [re.compile(p) for p in (r"Filing ID #\d+", r"ID Owner Asset Transaction Type Date Notification Date Amount Cap\. Gains > \$200\?",
                                 r"F\s+S\s+:\s+\w+", r"S\s+O\s*:\s*.*?(?=(?:\b(?:SP|JT|DC)\b|[A-Z][a-z]))", r"\bL\s+:\s+[A-Z]{2}\b",
                                 r"\bD\s+:\s+[^\[]*?(?=\b(?:SP|JT|DC)\b|$)", r"\bC\s+:\s+.*?(?=\b(?:SP|JT|DC)\b|$)")]


def parse_house_text(text: str) -> list[dict[str, Any]]:
    """Transactions from an electronic House PTR's text. Handles records split across page breaks."""
    t = re.sub(r"\s+", " ", text)
    t = re.sub(r"Filing ID #\d+ ID Owner Asset Transaction Type Date Notification Date Amount Cap\. Gains > \$200\?", " ", t)
    head = t.find("Gains > $200?")
    if head >= 0:
        t = t[head + len("Gains > $200?"):]
    end = t.find("* For the complete list of asset type")
    if end >= 0:
        t = t[:end]
    cores = list(CORE.finditer(t))
    out = []
    consumed = 0  # text already claimed by a record split across a page break
    for i, m in enumerate(cores):
        before = t[max(cores[i - 1].end() if i else 0, consumed):m.start()]
        after = t[m.end():cores[i + 1].start() if i + 1 < len(cores) else len(t)]
        tk = list(TICK.finditer(before))
        ticker = atype = None
        asset = before
        if tk:
            ticker, atype = tk[-1].group(1), tk[-1].group(2)
            asset = before[:tk[-1].start()]
        else:  # record split by a page break: the ticker comes after the amount
            ta = TICK.search(after)
            if ta and ta.start() < 200:
                ticker, atype = ta.group(1), ta.group(2)
                asset = before + " " + after[:ta.start()]
                consumed = m.end() + ta.end()
            else:
                ab = re.search(r"\[([A-Z]{2})\]\s*$", before.strip())
                atype = ab.group(1) if ab else None
        for n in NOISE:
            asset = n.sub(" ", asset)
        asset = re.sub(r"\[[A-Z]{2}\]", " ", asset)
        own = re.search(r"(?:^|\s)(SP|JT|DC)\s", " " + asset + " ")
        owner = OWNERS[own.group(1)] if own else "self"
        asset = re.sub(r"(?:^|\s)(SP|JT|DC)\s", " ", " " + asset + " ")
        asset = re.sub(r"\s+", " ", asset).strip(" -:")[-160:]
        lo, hi = amount_bounds(m.group(4))
        out.append({"owner": owner, "asset": asset or (ticker or "Unknown asset"), "ticker": ticker.replace(".", "-") if ticker else None,
                    "asset_type": {"ST": "Stock", "OP": "Option", "OT": "Other", "EF": "ETF", "GS": "Government security", "CS": "Corporate bond",
                                   "MF": "Mutual fund", "CT": "Crypto"}.get(atype or "", atype), "tx_type": TYPES.get(m.group(1), "other"),
                    "traded": _d(m.group(2)), "notified": _d(m.group(3)), "amount": m.group(4).replace("Spouse/DC ", ""), "amount_low": lo, "amount_high": hi})
    return out


def house_index(year: int, client: httpx.Client) -> list[dict[str, Any]]:
    import xml.etree.ElementTree as ET

    r = client.get(HOUSE_INDEX.format(year=year))
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    root = ET.fromstring(z.read(next(n for n in z.namelist() if n.endswith(".xml"))))
    out = []
    for m in root:
        if m.findtext("FilingType") != "P":
            continue
        out.append({"doc": m.findtext("DocID"), "year": m.findtext("Year") or str(year), "first": (m.findtext("First") or "").strip(),
                    "last": (m.findtext("Last") or "").strip(), "statedst": m.findtext("StateDst") or "", "filed": _d(m.findtext("FilingDate"))})
    out.sort(key=lambda x: x["filed"] or dt.date.min, reverse=True)
    return out


def house_pdf_text(url: str, client: httpx.Client) -> str:
    from pypdf import PdfReader

    r = client.get(url)
    r.raise_for_status()
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(r.content)).pages)


# ── Senate ───────────────────────────────────────────────────────────────────────────────────────
def senate_session() -> httpx.Client:
    c = httpx.Client(headers={"User-Agent": "Mozilla/5.0 (Irradiance Research; support@irradiance.ai)"}, timeout=30, follow_redirects=True)
    h = c.get(f"{SENATE}/search/home/")
    tok = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', h.text)
    if not tok:
        raise RuntimeError("Senate eFD: no CSRF token")
    c.post(f"{SENATE}/search/home/", data={"prohibition_agreement": "1", "csrfmiddlewaretoken": tok.group(1)}, headers={"Referer": f"{SENATE}/search/home/"})
    return c


def senate_reports(c: httpx.Client, since: dt.date, limit: int = 200) -> list[dict[str, Any]]:
    csrf = c.cookies.get("csrftoken") or ""
    data = {"start": "0", "length": str(limit), "report_types": "[11]", "filer_types": "[]", "submitted_start_date": since.strftime("%m/%d/%Y 00:00:00"),
            "submitted_end_date": "", "candidate_state": "", "senator_state": "", "office_id": "", "first_name": "", "last_name": "", "csrfmiddlewaretoken": csrf}
    r = c.post(f"{SENATE}/search/report/data/", data=data, headers={"Referer": f"{SENATE}/search/", "X-CSRFToken": csrf})
    r.raise_for_status()
    out = []
    for row in r.json().get("data", []):
        m = re.search(r'href="(/search/view/(ptr|paper)/([^/]+)/)"', row[3])
        if not m:
            continue
        out.append({"first": row[0], "last": row[1], "office": row[2], "path": m.group(1), "kind": m.group(2), "doc": m.group(3), "filed": _d(row[4])})
    return out


def parse_senate_html(html: str) -> list[dict[str, Any]]:
    tbody = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tbody.group(1) if tbody else "", re.S):
        cells = [html_lib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) < 8:
            continue
        _, date, owner, ticker, asset, atype, typ, amount = cells[:8]
        lo, hi = amount_bounds(amount)
        tk = ticker.strip() if ticker.strip() not in ("--", "") else None
        out.append({"owner": OWNERS.get(owner, owner.lower() or "self"), "asset": asset[:300], "ticker": tk.replace(".", "-") if tk else None, "asset_type": atype,
                    "tx_type": TYPES.get(typ, "sell" if typ.startswith("Sale") else typ.lower()), "traded": _d(date), "amount": amount, "amount_low": lo, "amount_high": hi})
    return out


# ── members ──────────────────────────────────────────────────────────────────────────────────────
_leg: dict[str, Any] = {}


def legislators(client: httpx.Client) -> list[dict[str, Any]]:
    if _leg.get("at") and time.time() - _leg["at"] < 86400:
        return _leg["rows"]
    try:
        rows = client.get(LEGISLATORS).json()
    except Exception:  # noqa: BLE001
        rows = _leg.get("rows", [])
    _leg.update(at=time.time(), rows=rows)
    return rows


def match_member(rows: list[dict[str, Any]], last: str, first: str, chamber: str, state: str | None = None) -> dict[str, Any]:
    ln = re.sub(r"[^a-z]", "", last.lower().split(",")[0])
    cands = []
    for r in rows:
        n, term = r.get("name", {}), (r.get("terms") or [{}])[-1]
        if term.get("type") != ("rep" if chamber == "house" else "sen"):
            continue
        lg = re.sub(r"[^a-z]", "", (n.get("last") or "").lower())
        if lg != ln and not (len(ln) >= 4 and (lg.endswith(ln) or ln.endswith(lg))):
            continue
        if state and term.get("state") != state:
            continue
        cands.append((r, term))
    if len(cands) > 1 and first:
        fn = first.lower().split()[0]
        cands = [c for c in cands if fn in (c[0]["name"].get("first", "") + " " + c[0]["name"].get("nickname", "")).lower()] or cands
    if not cands:
        return {}
    r, term = cands[0]
    nm = r["name"]
    return {"member": nm.get("official_full") or f"{nm.get('first')} {nm.get('last')}", "party": {"Democrat": "Democrat", "Republican": "Republican"}.get(term.get("party"), term.get("party")),
            "state": term.get("state")}


# ── refresh ──────────────────────────────────────────────────────────────────────────────────────
def _key(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:40]


def _store(db: Session, chamber: str, doc: str, url: str, filed: dt.date | None, who: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    n = 0
    seen = set()
    for i, t in enumerate(rows):
        k = _key(chamber, doc, i, t["ticker"], t["traded"], t["tx_type"], t["amount"], t["asset"][:40])
        if k in seen:
            continue
        seen.add(k)
        db.add(CongressTrade(row_key=k, chamber=chamber, member=who.get("member") or "Unknown", party=who.get("party"), state=who.get("state"),
                             district=who.get("district"), owner=t.get("owner"), ticker=t.get("ticker"), asset=t["asset"] or "—", asset_type=t.get("asset_type"),
                             tx_type=t["tx_type"], amount=t["amount"], amount_low=t.get("amount_low"), amount_high=t.get("amount_high"),
                             traded=t.get("traded"), filed=filed, doc_id=doc, url=url))
        n += 1
    return n


def refresh(db: Session, max_docs: int = 60, days: int = 120, senate_docs: int = 40) -> dict[str, Any]:
    stats = {"house": 0, "senate": 0, "docs": 0, "scanned": 0, "errors": 0}
    done = set(db.scalars(select(DisclosureDoc.id)).all())
    since = dt.date.today() - dt.timedelta(days=days)
    with httpx.Client(headers=UA, timeout=40, follow_redirects=True) as c:
        leg = legislators(c)
        idx = []
        for y in sorted({dt.date.today().year, since.year}, reverse=True):
            try:
                idx += house_index(y, c)
            except Exception as e:  # noqa: BLE001
                log.warning("house index %s: %s", y, e)
        budget = max_docs
        for f in idx:
            if budget <= 0 or not f["filed"] or f["filed"] < since:
                continue
            did = f"house:{f['doc']}"
            if did in done:
                continue
            budget -= 1
            url = HOUSE_PTR.format(year=f["year"], doc=f["doc"])
            st, n = "parsed", 0
            try:
                text = house_pdf_text(url, c)
                rows = parse_house_text(text)
                if not rows:
                    st = "scanned" if len(text.strip()) < 200 else "empty"
                m = re.match(r"([A-Z]{2})(\d+)?", f["statedst"])
                who = match_member(leg, f["last"], f["first"], "house", m.group(1) if m else None) or {"member": f"{f['first']} {f['last']}".strip(), "state": m.group(1) if m else None}
                who["district"] = m.group(2) if m else None
                n = _store(db, "house", f["doc"], url, f["filed"], who, rows)
                stats["house"] += n
                stats["scanned"] += st == "scanned"
            except Exception as e:  # noqa: BLE001
                st = "error"
                stats["errors"] += 1
                log.warning("house ptr %s: %s", f["doc"], e)
            db.add(DisclosureDoc(id=did, status=st, trades=n))
            db.commit()
            stats["docs"] += 1
            time.sleep(0.3)
    s = None
    try:
        s = senate_session()
        budget = senate_docs
        if True:
            for rep in senate_reports(s, since):
                if budget <= 0:
                    break
                did = f"senate:{rep['doc']}"
                if did in done:
                    continue
                budget -= 1
                url = SENATE + rep["path"]
                st, n = "parsed", 0
                try:
                    if rep["kind"] == "paper":
                        rows, st = [], "scanned"
                    else:
                        rows = parse_senate_html(s.get(url).text)
                        st = "parsed" if rows else "empty"
                    who = match_member(leg, rep["last"], rep["first"], "senate") or {"member": re.sub(r"\s*\(.*\)", "", rep["office"]).strip()}
                    n = _store(db, "senate", rep["doc"], url, rep["filed"], who, rows)
                    stats["senate"] += n
                except Exception as e:  # noqa: BLE001
                    st = "error"
                    stats["errors"] += 1
                    log.warning("senate ptr %s: %s", rep["doc"], e)
                db.add(DisclosureDoc(id=did, status=st, trades=n))
                db.commit()
                stats["docs"] += 1
                time.sleep(0.4)
    except Exception as e:  # noqa: BLE001
        log.warning("senate: %s", e)
        stats["senate_error"] = type(e).__name__
    finally:
        if s is not None:
            s.close()
    log.info("congress refresh %s", json.dumps(stats))
    return stats


_last: dict[str, float] = {"at": 0.0}


def due() -> bool:
    return time.time() - _last["at"] > 4 * 3600


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
                log.exception("congress refresh failed")

    threading.Thread(target=go, daemon=True, name="congress").start()
    return True
