"""A request that uses every optional input: stories, market sizing, locked numbers,
earnings adjustments, regional risk, bottom-up beta, options and NOLs. Checks that each input
reaches the numbers, and that Excel still matches Python with early losses and an NOL."""
import json

import pytest

from valuebot import pipeline
from tests.valuebot.test_excel_parity import _excel_value, _recalc, shutil

REQ = {
    "ticker": "DEMO",
    "stories": {"growth": "Takes share in a large analytics market.", "profitability": "Losses near term, then scale.",
                "efficiency": "Light reinvestment.", "risk": "Global customer base.", "moat": "Switching costs."},
    "market": {"tam": 60e9, "tam_growth": 0.08, "target_share": 0.15},
    "overrides": {"operating_margin_y1": -0.08, "target_operating_margin": 0.25, "margin_convergence_year": 6, "sales_to_capital_late": 2.4,
                  "prob_failure": 0.05},
    "adjustments": {"capitalize_rnd": "yes", "rnd_life": 5, "lease_adjust": True, "one_time_addback": 50e6},
    "risk": {"regions": [{"region": "United States", "weight": 70, "crp": 0.0},
                         {"region": "India", "weight": 30, "crp": 0.03}],
             "segments": [{"name": "Software", "weight": 100, "unlevered_beta": 1.20}]},
    "method": "fcff",
    "extras": {"nol": 900e6, "options_count": 10e6, "options_strike": 50, "options_maturity": 4, "volatility": 0.4},
}


@pytest.fixture
def run(offline):
    job = pipeline.create_job(REQ)
    pipeline.run_job(job["id"])
    j = pipeline.load_job(job["id"])
    assert j["status"] == "done", j.get("traceback")
    d = pipeline.job_dir(job["id"])
    return d, json.loads((d / "result.json").read_text())


def test_inputs_reach_the_numbers(run):
    _, r = run
    a = r["assumptions"]
    # locked inputs win
    assert a["operating_margin_y1"]["value"] == -0.08 and a["operating_margin_y1"]["rationale"].startswith("Set by you")
    assert a["target_operating_margin"]["value"] == 0.25
    # TAM × share anchors year-10 revenue
    tam10 = 60e9 * 1.08 ** 10
    assert r["result"]["table"][-1]["revenue"] == pytest.approx(tam10 * 0.15, rel=1e-6)
    # ERP weighted by operations: 4.23% + 30% × 3%
    assert r["risk"]["erp"] == pytest.approx(0.0423 + 0.009)
    # bottom-up beta relevered at market D/E
    de = r["risk"]["debt_to_equity"]
    assert r["cost_of_capital"]["beta"] == pytest.approx(1.20 * (1 + 0.75 * de))
    # earnings adjustments applied
    items = [i["item"] for i in r["earnings"]["items"]]
    assert any("R&D (5-year" in i for i in items) and any("One-time" in i for i in items)
    # NOL and options flow into inputs
    assert r["inputs"]["nol0"] == 900e6 and r["inputs"]["options_value"] > 0
    # NOL shelters early profits: first profitable year pays less tax than the statutory rate
    rows = r["result"]["table"]
    first_profit = next(x for x in rows if x["ebit"] > 0)
    assert first_profit["nopat"] > first_profit["ebit"] * (1 - first_profit["tax_rate"])
    # stories carried through; narrative tests ran with the TAM
    assert r["stories"]["moat"] == "Switching costs."
    assert any(t["test"] == "Not bigger than the total market" for t in r["narrative_tests"])


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")
def test_excel_matches_with_losses_and_nol(run, tmp_path):
    d, r = run
    got = _excel_value(_recalc(d / "model.xlsx", tmp_path))
    assert got == pytest.approx(r["result"]["value_per_share"], rel=1e-9)


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")
def test_all_workbooks_clean_and_market_model_hits_price(run, tmp_path):
    import openpyxl

    d, r = run
    rv = r["probabilistic"]["reverse_dcf"]
    assert rv["converged"] and rv["implied_value"] == pytest.approx(r["result"]["price"], rel=1e-6)
    for name in ("model.xlsx", "model_bear.xlsx", "model_bull.xlsx", "model_market.xlsx"):
        out = _recalc(d / name, tmp_path)
        wb = openpyxl.load_workbook(out, data_only=True)
        errors = [(ws.title, c.coordinate) for ws in wb for row in ws.iter_rows() for c in row
                  if isinstance(c.value, str) and c.value.startswith("#")]
        assert not errors, (name, errors[:5])
        assert "Diagnostics" in wb.sheetnames and "Reverse DCF" in wb.sheetnames
    assert _excel_value(tmp_path / "model_market.xlsx") == pytest.approx(r["result"]["price"], rel=1e-6)


def test_segment_economics_reconcile(offline):
    req = {**REQ, "market": {}, "overrides": {"operating_margin_y1": -0.05},
           "risk": {"segments": [{"name": "Platform", "weight": 70, "unlevered_beta": 1.1, "revenue_y10": 20e9, "target_margin": 0.30},
                                 {"name": "Services", "weight": 30, "unlevered_beta": 0.9, "revenue_y10": 5e9, "target_margin": 0.10}]}}
    job = pipeline.create_job(req)
    pipeline.run_job(job["id"])
    r = json.loads((pipeline.job_dir(job["id"]) / "result.json").read_text())
    assert r["assumptions"]["target_operating_margin"]["value"] == pytest.approx((20 * 0.30 + 5 * 0.10) / 25)
    assert r["result"]["table"][-1]["revenue"] == pytest.approx(25e9, rel=1e-6)
