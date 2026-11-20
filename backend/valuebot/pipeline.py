"""The valuation pipeline: a fixed sequence of stages with persisted, pollable progress.

Each job lives in runs/<job_id>/ :
  job.json        status + per-stage progress (what the UI polls)
  result.json     everything the report view needs
  report.html     standalone printable report
  model.xlsx      live-formula workbook (+ model_bear.xlsx / model_bull.xlsx)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import smtplib
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable

from . import analysis
from .config import settings
from .data import provider
from .engine import adjustments, fcff, narrative, probabilistic, registry
from .llm import agent
from .output import excel, report, views

STAGES: list[tuple[str, str]] = [
    ("resolve", "Resolve company"),
    ("filings", "Pull filings and market data"),
    ("history", "Analyze historical financials"),
    ("thesis", "Frame the investment thesis"),
    ("research", "Research recent news and context"),
    ("method", "Choose valuation framework"),
    ("risk", "Estimate cost of capital"),
    ("earnings", "Measure earnings right"),
    ("baseline", "Set data-driven starting assumptions"),
    ("story", "Translate the story into numbers"),
    ("valuation", "Run the valuation"),
    ("narrative", "Test the story: possible, plausible, probable"),
    ("sensitivity", "Sensitivity and scenarios"),
    ("probabilistic", "Break-evens, scenarios and simulation"),
    ("excel", "Build the Excel model"),
    ("scenarios", "Build bull and bear scenario models"),
    ("write", "Write the report"),
    ("publish", "Publish report and files"),
]

_lock = threading.Lock()
# Bounded worker pool: a burst of requests queues instead of spawning unbounded threads that all hit
# SEC/Yahoo/Claude at once. Size with VALUEBOT_MAX_WORKERS.
_executor = ThreadPoolExecutor(max_workers=max(1, int(os.environ.get("VALUEBOT_MAX_WORKERS", "4"))),
                               thread_name_prefix="valuebot")
# Callbacks run after each job finishes (status "done" or "error"); the IRAI platform uses this to
# record runs in its database. Each receives the final job dict and must not raise.
on_finish: list[Callable[[dict[str, Any]], None]] = []


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def job_dir(job_id: str) -> Path:
    return settings.data_dir / job_id


def load_job(job_id: str) -> dict[str, Any]:
    return json.loads((job_dir(job_id) / "job.json").read_text())


def _save_job(job: dict[str, Any]) -> None:
    d = job_dir(job["id"])
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "job.json.tmp"
    tmp.write_text(json.dumps(job, indent=1, default=str))
    os.replace(tmp, d / "job.json")


_share_index: dict[str, str] = {}


def find_by_share_token(token: str) -> str | None:
    if not token or len(token) > 64:
        return None
    hit = _share_index.get(token)
    if hit and (job_dir(hit) / "job.json").exists():
        return hit
    if not settings.data_dir.exists():
        return None
    for d in settings.data_dir.iterdir():
        f = d / "job.json"
        if f.exists():
            try:
                t = json.loads(f.read_text()).get("share_token")
                if t:
                    _share_index[t] = d.name
                if t == token:
                    return d.name
            except json.JSONDecodeError:
                continue
    return None


def list_jobs() -> list[dict[str, Any]]:
    if not settings.data_dir.exists():
        return []
    jobs = []
    for d in settings.data_dir.iterdir():
        f = d / "job.json"
        if f.exists():
            try:
                j = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue  # half-written or corrupt job file: skip rather than break the listing
            jobs.append({k: j.get(k) for k in ("id", "ticker", "status", "created_at", "summary")})
    return sorted(jobs, key=lambda j: j["created_at"] or "", reverse=True)


def create_job(request: dict[str, Any]) -> dict[str, Any]:
    job = {
        "id": dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3),
        "ticker": request["ticker"].upper().strip(),
        "request": request,
        "status": "queued",
        "created_at": _now(),
        "share_token": secrets.token_urlsafe(12),
        "stages": [{"key": k, "label": l, "status": "pending", "detail": None} for k, l in STAGES],
        "plan": None,
        "error": None,
        "summary": None,
    }
    _save_job(job)
    _share_index[job["share_token"]] = job["id"]
    return job


def start_job(job: dict[str, Any]):
    """Queue the job on the bounded worker pool. Returns a Future."""
    return _executor.submit(run_job, job["id"])


class _Progress:
    def __init__(self, job: dict[str, Any]):
        self.job = job

    def _stage(self, key):
        return next(s for s in self.job["stages"] if s["key"] == key)

    def start(self, key: str, detail: str | None = None):
        with _lock:
            s = self._stage(key)
            s.update(status="running", started_at=_now(), detail=detail)
            self.job["status"] = "running"
            _save_job(self.job)

    def log(self, key: str) -> Callable[[str], None]:
        def _log(msg: str):
            with _lock:
                self._stage(key)["detail"] = msg
                _save_job(self.job)
        return _log

    def done(self, key: str, detail: str | None = None, status: str = "done"):
        with _lock:
            s = self._stage(key)
            s.update(status=status, finished_at=_now())
            if detail is not None:
                s["detail"] = detail
            _save_job(self.job)


DEFAULT_QUESTIONS = [
    "How big can revenues get (market size × market share), and how quickly?",
    "How profitable will the business be at scale, given its unit economics?",
    "How much must it reinvest to grow, and does that reinvestment earn more than the cost of capital?",
    "How risky is the business, and what is the chance it fails?",
    "When does the company become mature, and what could stop it getting there?",
]


def _segment_economics(segments: list[dict]) -> dict | None:
    """Sum-of-the-segments: consolidated year-10 revenue and revenue-weighted target margin."""
    rows = [s for s in segments if analysis._f(s.get("revenue_y10")) and analysis._f(s.get("target_margin")) is not None]
    if not rows:
        return None
    rev = sum(analysis._f(s["revenue_y10"]) for s in rows)
    ebit = sum(analysis._f(s["revenue_y10"]) * analysis._f(s["target_margin"]) for s in rows)
    parts = " + ".join(f"{s['name']} {analysis._f(s['revenue_y10']) / 1e9:,.1f}bn × {analysis._f(s['target_margin']):.1%}" for s in rows)
    return {"revenue": rev, "margin": ebit / rev, "rows": rows,
            "text": f"({parts}) ÷ {rev / 1e9:,.1f}bn = {ebit / rev:.2%}."}


def _earn_public(earn: dict) -> dict:
    out = {k: v for k, v in earn.items() if k != "rnd"}
    if earn.get("rnd"):
        out["rnd"] = {k: v for k, v in earn["rnd"].items() if k != "rows"}
        out["rnd_rows"] = earn["rnd"].get("rows")
    return out


def _insights(method, inputs, result, snap, metrics, coc, risk) -> dict:
    """Loose ends and cross-checks: value of growth, implied multiples, market-implied cost of equity."""
    last, last_h = metrics[-1], snap["history"][-1]
    out: dict = {}
    if method == "fcff":
        op = dict(result.bridge)["Value of operating assets"]
        out["value_of_growth"] = adjustments.value_of_growth(inputs["ebit0"] or 0, inputs["effective_tax_rate"],
                                                             inputs["wacc_initial"], op)
    out["multiples"] = adjustments.implied_multiples(
        equity_value=result.equity_value, price=snap["price"], shares=snap["shares"],
        debt=last["debt_incl_leases"] or 0, cash=last_h.get("cash") or 0, revenue=last.get("revenue"),
        ebit=last.get("ebit"), net_income=last.get("net_income"), book_equity=last_h.get("equity"))
    m, why = adjustments.conventional_multiple(snap.get("sector"), snap.get("industry"),
                                               last.get("revenue_growth"), (last.get("ebit") or 0) > 0)
    out["conventional_multiple"] = {"multiple": m, "why": why}
    if method == "excess_return" and last_h.get("equity"):
        pbv = snap["price"] * snap["shares"] / last_h["equity"]
        ke = adjustments.implied_cost_of_equity_from_pbv(pbv, last.get("roe") or 0, risk["riskfree"])
        out["implied_cost_of_equity"] = {"pbv": pbv, "roe": last.get("roe"), "growth": risk["riskfree"], "ke": ke,
                                         "model_ke": inputs["cost_of_equity_high"]}
    return out


def _assumption_rows(method: str, values: dict, rationale: dict) -> dict[str, dict]:
    return {d.key: {"label": d.label, "unit": d.unit, "value": values[d.key], "rationale": rationale.get(d.key, ""),
                    "story": d.story} for d in registry.drivers_for(method)}


def run_job(job_id: str) -> None:
    job = load_job(job_id)
    req = job["request"]
    p = _Progress(job)
    out = job_dir(job_id)
    stage = "resolve"
    try:
        # 1-2: data -------------------------------------------------------------------------
        p.start("resolve", f"Looking up {job['ticker']}")
        p.done("resolve")
        stage = "filings"
        p.start("filings")
        snap = provider.snapshot(job["ticker"], log=p.log("filings"))
        p.done("filings", f"{len(snap['history'])} fiscal years · price {snap['price']:,.2f} {snap['currency']}")
        p._stage("resolve")["detail"] = snap["name"]

        stage = "history"
        p.start("history")
        metrics = analysis.history_metrics(snap)
        last = metrics[-1]
        p.done("history", f"FY{last['fiscal_year']}: revenue {(last['revenue'] or 0) / 1e6:,.0f}m, "
                          f"margin {(last['operating_margin'] or 0):.1%}")

        # 3-4: thesis and research --------------------------------------------------------
        stage = "thesis"
        p.start("thesis")
        thesis = (req.get("thesis") or "").strip()
        stories = {k: v.strip() for k, v in (req.get("stories") or {}).items() if v and v.strip()}
        questions = [q for q in (req.get("questions") or []) if q.strip()]
        if not thesis and stories:
            thesis = " ".join(stories.values())
        if not questions:
            questions = list(DEFAULT_QUESTIONS)
        if not thesis:
            drafted = agent.draft_thesis(snap, metrics, req.get("stance", "neutral"))
            thesis = drafted["thesis"]
            stories = stories or drafted.get("stories") or {}
            if drafted.get("questions") and questions == DEFAULT_QUESTIONS:
                questions = drafted["questions"]
            p.done("thesis", f"Drafted a {req.get('stance', 'neutral')} thesis")
        else:
            p.done("thesis", "Using your thesis")

        stage = "research"
        p.start("research")
        res = agent.research(snap, thesis)
        p.done("research", f"{len(res['sources'])} sources" if res["sources"] else "Headlines only")

        # 5-8: framework, risk, baseline ----------------------------------------------------
        stage = "method"
        p.start("method")
        if req.get("method", "auto") in registry.METHODS:
            method, reason = req["method"], "Chosen by the user."
        else:
            pays = bool(snap.get("dividend_rate")) or bool(last.get("payout_ratio"))
            method, reason = registry.choose_method(
                sector=snap.get("sector"), industry=snap.get("industry"),
                payout_ratio=snap.get("payout_ratio") if snap.get("payout_ratio") is not None else last.get("payout_ratio"),
                pays_dividends=pays, has_revenue=bool(last.get("revenue")))
        mod = registry.METHODS[method]
        job["plan"] = {"method": method, "method_title": mod.TITLE, "reason": reason}
        p.done("method", mod.TITLE)

        stage = "risk"
        p.start("risk")
        risk = analysis.risk_inputs(snap, metrics, req.get("risk"))
        coc = analysis.cost_of_capital(snap, metrics, risk)
        p.done("risk", f"Risk-free {risk['riskfree']:.2%} · beta {coc.beta:.2f} ({risk['beta_source'].split(':')[0]}) · "
                       f"ERP {risk['erp']:.2%} · WACC {coc.wacc:.2%} · rating {coc.rating}")

        stage = "earnings"
        p.start("earnings")
        earn = analysis.earnings_adjustments(snap, metrics, coc, req.get("adjustments"))
        last = metrics[-1]
        p.done("earnings", "; ".join(i["item"] for i in earn["items"]) if earn["items"] else "No adjustments needed")

        stage = "baseline"
        p.start("baseline")
        extras = req.get("extras") or {}
        base = analysis.base_inputs(method, snap, metrics, extras, risk["riskfree"])
        _, opt_note = analysis.options_value(snap, extras, risk["riskfree"]) if method == "fcff" else (0, None)
        defaults, why = analysis.default_drivers(method, snap, metrics, coc, earn)
        market = {k: analysis._f(v) for k, v in (req.get("market") or {}).items()}
        tam10 = None
        if market.get("tam") and method == "fcff":
            tam10 = market["tam"] * (1 + (market.get("tam_growth") or 0)) ** 10
        p.done("baseline", f"Options valued: {opt_note}" if opt_note else None)

        stage = "story"
        p.start("story")
        overrides = {k: analysis._f(v) for k, v in (req.get("overrides") or {}).items()
                     if k in {d.key for d in mod.DRIVERS} and analysis._f(v) is not None}
        values, rationale = agent.story_to_numbers(
            snap=snap, metrics=metrics, method=method, drivers=mod.DRIVERS, defaults=defaults, why=why,
            thesis=thesis, briefing=res["briefing"], cost_of_capital=coc.to_dict(), stories=stories,
            locked=overrides, market=market, earnings=earn)
        for k, v in overrides.items():  # the user's numbers always win
            values[k] = next(d for d in mod.DRIVERS if d.key == k).clamp(v)
            rationale[k] = "Set by you." + (f" {rationale[k]}" if rationale.get(k) and not rationale[k].startswith("Set by you") else "")
        segment_econ = _segment_economics((req.get("risk") or {}).get("segments") or [])
        if segment_econ and method == "fcff":
            if "target_operating_margin" not in overrides:
                values["target_operating_margin"] = segment_econ["margin"]
                rationale["target_operating_margin"] = "Revenue-weighted segment margins: " + segment_econ["text"]
        if tam10 and market.get("target_share") and "revenue_growth_y2_5" not in overrides:
            target = tam10 * market["target_share"]
            g = fcff.growth_for_revenue_target({**base, **values}, target)
            if g is not None:
                values["revenue_growth_y2_5"] = next(d for d in mod.DRIVERS if d.key == "revenue_growth_y2_5").clamp(g)
                rationale["revenue_growth_y2_5"] = (
                    f"Solved so year-10 revenue = total market {tam10 / 1e9:,.0f}bn × target share "
                    f"{market['target_share']:.0%} = {target / 1e9:,.1f}bn (market size × market share).")
        elif segment_econ and method == "fcff" and "revenue_growth_y2_5" not in overrides:
            g = fcff.growth_for_revenue_target({**base, **values}, segment_econ["revenue"])
            if g is not None:
                values["revenue_growth_y2_5"] = next(d for d in mod.DRIVERS if d.key == "revenue_growth_y2_5").clamp(g)
                rationale["revenue_growth_y2_5"] = (f"Solved so year-10 revenue equals the sum of segment targets, "
                                                    f"{segment_econ['revenue'] / 1e9:,.1f}bn.")
        inputs = {**base, **values}
        job["plan"]["key_drivers"] = {k: values[k] for k in list(values)[:4]}
        p.done("story", f"Assumptions set ({len(overrides)} locked by you)" if overrides else "Assumptions set")

        # 9-10: numbers -------------------------------------------------------------------
        stage = "valuation"
        p.start("valuation")
        result = registry.run(method, inputs)
        p.done("valuation", f"{result.value_per_share:,.2f} per share vs price {snap['price']:,.2f}")

        stage = "narrative"
        p.start("narrative")
        tests = narrative.narrative_tests(
            method, inputs, result.to_dict(), riskfree=risk["riskfree"], gross_margin=last.get("gross_margin"),
            current_roic=last.get("roic"), current_wacc=coc.wacc, tam_year10=tam10, erp=risk["erp"])
        insights = _insights(method, inputs, result, snap, metrics, coc, risk)
        failed = [t for t in tests if not t["pass"]]
        p.done("narrative", f"{len(tests) - len(failed)}/{len(tests)} tests pass"
                            + (f" · flags: {', '.join(t['test'] for t in failed[:2])}" if failed else ""))

        stage = "sensitivity"
        p.start("sensitivity")
        sens = registry.sensitivity(method, inputs)
        p.done("sensitivity", f"Bear {sens['scenarios']['bear']['value_per_share']:,.2f} · "
                              f"Bull {sens['scenarios']['bull']['value_per_share']:,.2f}")

        stage = "probabilistic"
        p.start("probabilistic")
        keys = probabilistic.KEY_DRIVERS[method]
        bevs = probabilistic.break_even_table(method, inputs, snap["price"], keys)
        top_key = sens["drivers"][0]["key"]
        top_be = probabilistic.break_even(method, inputs, top_key, snap["price"])
        curve = {"key": top_key, "label": next(d.label for d in mod.DRIVERS if d.key == top_key),
                 "unit": next(d.unit for d in mod.DRIVERS if d.key == top_key),
                 "base": inputs[top_key], "price": snap["price"], "break_even": top_be,
                 "points": probabilistic.break_even_curve(method, inputs, top_key, include=top_be)}
        specs = agent.scenarios(snap=snap, method=method, drivers=mod.DRIVERS, key_drivers=keys, base=inputs,
                                thesis=thesis, briefing=res["briefing"])
        prob = {
            "reverse_dcf": probabilistic.reverse_dcf(method, inputs, snap["price"], keys),
            "key_drivers": keys,
            "break_even": bevs,
            "curve": curve,
            "scenarios": probabilistic.plausible_scenarios(method, inputs, specs),
            "simulation": probabilistic.simulate(method, inputs, price=snap["price"], metrics=metrics),
            "checks": probabilistic.consistency_checks(method, inputs, riskfree=risk["riskfree"],
                                                       beta=snap.get("beta"), result_terminal=result.terminal),
        }
        sim = prob["simulation"]
        p.done("probabilistic", f"Median {sim['percentiles'][50]:,.2f} · P(undervalued) "
                                f"{sim.get('prob_undervalued', 0):.0%} · expected {prob['scenarios']['expected_value']:,.2f}")

        company = {k: snap.get(k) for k in ("ticker", "name", "sector", "industry", "country", "currency", "price",
                                            "shares", "market_cap", "beta", "summary", "consensus", "demo")}
        sources = snap.get("sources", []) + res["sources"]
        ctx = {
            "company": company, "thesis": thesis, "questions": questions, "method": method,
            "method_title": mod.TITLE, "method_reason": reason, "metrics": metrics,
            "cost_of_capital": coc.to_dict(), "inputs": inputs,
            "assumptions": _assumption_rows(method, values, rationale),
            "result": result.to_dict(), "sensitivity": sens, "probabilistic": prob, "briefing": res["briefing"], "sources": sources,
            "stories": stories, "market": market, "overrides": overrides, "earnings": _earn_public(earn),
            "risk": {k: v for k, v in risk.items()}, "narrative_tests": tests, "insights": insights,
            "segment_economics": segment_econ,
        }

        # 11-12: Excel ------------------------------------------------------------------------
        stage = "excel"
        p.start("excel")
        cells = excel.build_workbook(out / "model.xlsx", ctx)
        p.done("excel", f"{len(cells['cells'])} editable inputs")

        stage = "scenarios"
        p.start("scenarios")
        for name in ("bear", "bull"):
            excel.build_workbook(out / f"model_{name}.xlsx", ctx, sens["scenarios"][name]["assumptions"])
        rv = prob["reverse_dcf"]
        if rv.get("converged"):
            excel.build_workbook(out / "model_market.xlsx", ctx, {x["key"]: x["market"] for x in rv["rows"]})
        p.done("scenarios")

        # 13-14: narrative and publish -----------------------------------------------------
        stage = "write"
        p.start("write")
        llm_ctx = {k: v for k, v in ctx.items() if k != "inputs"}
        llm_ctx["result"] = {k: v for k, v in ctx["result"].items() if k != "table"}
        llm_ctx["probabilistic"] = {**prob, "curve": {k: v for k, v in prob["curve"].items() if k != "points"},
                                    "simulation": {k: v for k, v in sim.items() if k != "histogram"}}
        sections = agent.write_report(llm_ctx)
        p.done("write")

        stage = "publish"
        p.start("publish")
        date = dt.date.today().isoformat()
        html_doc = report.render_html(ctx, sections, date)
        (out / "report.html").write_text(html_doc)
        has_pdf = report.write_pdf(out / "report.html", out / "report.pdf")
        payload = {**ctx, "sections": sections, "chapters": views.chapters(ctx), "one_page": views.one_page(ctx),
                   "summary": views.summary(ctx), "section_titles": agent.REPORT_SECTIONS, "date": date,
                   "methodology": cells, "files": {"xlsx": "model.xlsx", "bear": "model_bear.xlsx",
                                                   "bull": "model_bull.xlsx", "html": "report.html",
                                                   "market": "model_market.xlsx" if rv.get("converged") else None,
                                                   "pdf": "report.pdf" if has_pdf else None},
                   "llm": settings.llm_enabled}
        (out / "result.json").write_text(json.dumps(payload, default=str))
        job["summary"] = {"name": snap["name"], "value_per_share": result.value_per_share,
                          "price": snap["price"], "upside": result.upside, "method": mod.TITLE,
                          "prob_undervalued": sim.get("prob_undervalued")}
        job["status"] = "done"
        job["finished_at"] = _now()
        p.done("publish")
        _notify(job, req.get("email"))
    except Exception as e:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = f"{type(e).__name__}: {e}"
        job["traceback"] = traceback.format_exc()
        p.done(stage, str(e), status="error")
    finally:
        for cb in list(on_finish):
            try:
                cb(job)
            except Exception:  # noqa: BLE001
                pass


def _notify(job: dict, email: str | None) -> None:
    """Optional email when a run finishes (set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, PUBLIC_URL)."""
    host = os.environ.get("SMTP_HOST")
    if not (email and host):
        return
    msg = EmailMessage()
    msg["Subject"] = f"Your {job['ticker']} valuation is ready"
    msg["From"] = os.environ.get("SMTP_FROM", "valuebot@localhost")
    msg["To"] = email
    base = os.environ.get("PUBLIC_URL", "http://localhost:8000")
    msg.set_content(f"View the report: {base}/#/job/{job['id']}")
    try:
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", 587))) as s:
            s.starttls()
            if os.environ.get("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            s.send_message(msg)
    except Exception:  # noqa: BLE001
        pass
