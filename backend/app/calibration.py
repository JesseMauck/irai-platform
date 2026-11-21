"""Nightly ValueBot calibration.

Runs the full valuation pipeline (deterministic writers, no LLM cost) on a fixed benchmark set and records value
per share against price. A company valued at under 0.4x or over 2.5x its price is not necessarily wrong, but a
cluster of them, a run that errors, or a large swing from the previous night usually means a data or model
regression (a retired XBRL tag, a bad beta, a currency or share-count mix-up). Results show in Admin.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import shutil
import statistics
import threading
from pathlib import Path
from typing import Any

from sqlalchemy import select

from .db import SessionLocal
from .models import CalibrationRun

log = logging.getLogger("irai.calibration")
CONFIG = json.loads((Path(__file__).parent / "seed_data" / "calibration.json").read_text())
_lock = threading.Lock()


def classify(ratio: float | None, prev_value: float | None, value: float | None, band=CONFIG["band"], swing=CONFIG["swing_alert"]) -> list[str]:
    flags = []
    if ratio is None:
        return ["no value"]
    if ratio < band["low"]:
        flags.append("far below price")
    if ratio > band["high"]:
        flags.append("far above price")
    if prev_value and value and abs(value / prev_value - 1) > swing:
        flags.append(f"moved {value / prev_value - 1:+.0%} since last run")
    return flags


def value_one(ticker: str) -> dict[str, Any]:
    from valuebot import pipeline
    from valuebot.config import llm_disabled

    t0 = dt.datetime.now(dt.timezone.utc)
    job = pipeline.create_job({"ticker": ticker, "thesis": "", "questions": [], "stance": "neutral", "method": "auto"})
    try:
        with llm_disabled():
            pipeline.run_job(job["id"])
        job = pipeline.load_job(job["id"])
        s = job.get("summary") or {}
        failed = next((st for st in job["stages"] if st["status"] == "error"), None)
        vps, price = s.get("value_per_share"), s.get("price")
        return {"ticker": ticker, "ok": job["status"] == "done", "value_per_share": vps, "price": price,
                "ratio": (vps / price) if vps and price else None, "method": s.get("method"),
                "prob_undervalued": s.get("prob_undervalued"),
                "error": job.get("error") if job["status"] == "error" else None,
                "failed_stage": failed["label"] if failed else None,
                "seconds": round((dt.datetime.now(dt.timezone.utc) - t0).total_seconds(), 1)}
    except Exception as e:  # noqa: BLE001
        return {"ticker": ticker, "ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
    finally:
        shutil.rmtree(pipeline.job_dir(job["id"]), ignore_errors=True)  # benchmark runs are not kept


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    ratios = [r["ratio"] for r in results if r.get("ratio")]
    return {"tickers": len(results), "ok": sum(1 for r in results if r.get("ok")), "errors": sum(1 for r in results if not r.get("ok")),
            "flagged": sum(1 for r in results if r.get("flags")), "median_ratio": statistics.median(ratios) if ratios else None,
            "in_band": sum(1 for x in ratios if CONFIG["band"]["low"] <= x <= CONFIG["band"]["high"]),
            "band": CONFIG["band"]}


def run(trigger: str = "schedule", tickers: list[str] | None = None) -> int | None:
    """Run the benchmark synchronously (call from a background thread). Returns the run id, or None if busy."""
    if not _lock.acquire(blocking=False):
        return None
    try:
        with SessionLocal() as db:
            prev = db.scalar(select(CalibrationRun).where(CalibrationRun.status == "done").order_by(CalibrationRun.started_at.desc()))
            prev_vals = {r["ticker"]: r.get("value_per_share") for r in (prev.results if prev else [])}
            cr = CalibrationRun(trigger=trigger, results=[])
            db.add(cr)
            db.commit()
            rid = cr.id
        results = []
        for t in tickers or CONFIG["tickers"]:
            r = value_one(t)
            r["prev_value"] = prev_vals.get(t)
            r["flags"] = classify(r.get("ratio"), r["prev_value"], r.get("value_per_share")) if r.get("ok") else ["error"]
            results.append(r)
            with SessionLocal() as db:  # save progress so Admin can watch a run fill in
                c = db.get(CalibrationRun, rid)
                c.results = list(results)
                db.commit()
        with SessionLocal() as db:
            c = db.get(CalibrationRun, rid)
            c.results, c.summary, c.status = results, summarize(results), "done"
            c.finished_at = dt.datetime.now(dt.timezone.utc)
            db.commit()
        log.info("calibration %s done: %s", rid, summarize(results))
        return rid
    except Exception:  # noqa: BLE001
        log.exception("calibration failed")
        return None
    finally:
        _lock.release()


def start_background(trigger: str = "manual") -> bool:
    if _lock.locked():
        return False
    threading.Thread(target=run, kwargs={"trigger": trigger}, daemon=True, name="calibration").start()
    return True


def due(db, now: dt.datetime | None = None) -> bool:
    """Once a day, after 07:00 UTC (US markets closed, SEC overnight filings in), if no run in the last 20 hours."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.hour < 7:
        return False
    last = db.scalar(select(CalibrationRun.started_at).order_by(CalibrationRun.started_at.desc()))
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=dt.timezone.utc)
    return last is None or now - last > dt.timedelta(hours=20)
