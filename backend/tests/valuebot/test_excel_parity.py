"""Recalculate the generated workbooks with LibreOffice and check they match the Python engine."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import openpyxl
import pytest

from valuebot import pipeline

pytestmark = pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")


def _recalc(src: Path, outdir: Path) -> Path:
    subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(outdir), str(src)],
                   check=True, capture_output=True, timeout=180)
    return outdir / src.name


def _excel_value(path: Path) -> float:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Valuation output"]
    for row in ws.iter_rows(min_row=5, max_col=2):
        if row[0].value == "Estimated value per share":
            return row[1].value
    raise AssertionError("value per share not found")


@pytest.mark.parametrize("ticker", ["DEMO", "DEMOB", "DEMOU"])
def test_workbook_matches_engine(ticker, tmp_path, offline):
    job = pipeline.create_job({"ticker": ticker, "stance": "neutral", "method": "auto"})
    pipeline.run_job(job["id"])
    d = pipeline.job_dir(job["id"])
    result = json.loads((d / "result.json").read_text())
    for name, expected in [
        ("model.xlsx", result["result"]["value_per_share"]),
        ("model_bear.xlsx", result["sensitivity"]["scenarios"]["bear"]["value_per_share"]),
        ("model_bull.xlsx", result["sensitivity"]["scenarios"]["bull"]["value_per_share"]),
    ]:
        got = _excel_value(_recalc(d / name, tmp_path))
        assert got == pytest.approx(expected, rel=1e-9), name
