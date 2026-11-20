"""Command line: python -m valuebot.cli DEMO --stance bullish"""
from __future__ import annotations

import argparse
import json

from . import pipeline


def main() -> None:
    ap = argparse.ArgumentParser(description="Run a valuation from the command line.")
    ap.add_argument("ticker")
    ap.add_argument("--thesis", default="")
    ap.add_argument("--question", action="append", default=[])
    ap.add_argument("--stance", choices=["bullish", "bearish", "neutral"], default="neutral")
    ap.add_argument("--method", default="auto", choices=["auto", "fcff", "ddm", "excess_return"])
    args = ap.parse_args()

    job = pipeline.create_job({"ticker": args.ticker, "thesis": args.thesis, "questions": args.question,
                               "stance": args.stance, "method": args.method})
    pipeline.run_job(job["id"])
    job = pipeline.load_job(job["id"])
    for s in job["stages"]:
        print(f"[{s['status']:>7}] {s['label']}: {s.get('detail') or ''}")
    if job["status"] == "error":
        print(job.get("traceback"))
        raise SystemExit(1)
    print(json.dumps(job["summary"], indent=1))
    print(f"Files in {pipeline.job_dir(job['id'])}")


if __name__ == "__main__":
    main()
