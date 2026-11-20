"""Data parsing with a synthetic SEC payload, and LLM output handling with a fake client."""
import dataclasses
from types import SimpleNamespace

import pytest

import valuebot.config as config
from valuebot.data import sec
from valuebot.engine import fcff
from valuebot.llm import agent


def _obs(val, end, start=None, form="10-K", filed="2025-02-01"):
    o = {"val": val, "end": end, "form": form, "fp": "FY", "filed": filed}
    if start:
        o["start"] = start
    return o


FACTS = {"facts": {"us-gaap": {
    "Revenues": {"units": {"USD": [
        _obs(100, "2023-12-31", "2023-01-01"),
        _obs(120, "2024-12-31", "2024-01-01"),
        _obs(125, "2024-12-31", "2024-01-01", filed="2025-06-01", form="10-K/A"),  # restatement wins
        _obs(30, "2024-09-30", "2024-07-01", form="10-Q"),  # quarterly: ignored
    ]}},
    "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [_obs(50, "2024-12-31")]}},
}}}


def test_annual_series_filters_and_restates():
    s = sec._annual_series(FACTS, "Revenues", instant=False)
    assert s == {"2023-12-31": 100.0, "2024-12-31": 125.0}
    assert sec._annual_series(FACTS, "CashAndCashEquivalentsAtCarryingValue", instant=True) == {"2024-12-31": 50.0}
    assert sec._first(FACTS, ["Missing", "Revenues"], instant=False)[1] == "Revenues"


class FakeClient:
    def __init__(self, tool_input):
        self.messages = SimpleNamespace(create=lambda **kw: SimpleNamespace(
            content=[SimpleNamespace(type="tool_use", input=tool_input)], stop_reason="tool_use"))


def test_story_to_numbers_sanitises(monkeypatch):
    s = dataclasses.replace(config.settings, anthropic_api_key="test", offline=False)
    monkeypatch.setattr("valuebot.llm.agent.settings", s)
    defaults = {d.key: 0.1 for d in fcff.DRIVERS}
    reply = {d.key: {"value": 0.1, "rationale": "ok"} for d in fcff.DRIVERS}
    reply["target_operating_margin"] = {"value": 25, "rationale": "25% at scale"}  # percent as whole number
    reply["prob_failure"] = {"value": -3, "rationale": "bad"}  # out of bounds -> clamped
    del reply["sales_to_capital"]  # missing -> default
    monkeypatch.setattr(agent, "_client", lambda: FakeClient(reply))
    vals, why = agent.story_to_numbers(snap={"ticker": "X"}, metrics=[], method="fcff", drivers=fcff.DRIVERS,
                                       defaults=defaults, why={}, thesis="t", briefing="", cost_of_capital={})
    assert vals["target_operating_margin"] == pytest.approx(0.25)
    assert vals["prob_failure"] == 0.0
    assert vals["sales_to_capital"] == 0.1
    assert why["target_operating_margin"] == "25% at scale"


def test_pipeline_offline_end_to_end(offline):
    from valuebot import pipeline

    job = pipeline.create_job({"ticker": "DEMO", "stance": "bearish", "method": "auto"})
    pipeline.run_job(job["id"])
    j = pipeline.load_job(job["id"])
    assert j["status"] == "done", j.get("traceback")
    assert all(s["status"] == "done" for s in j["stages"])
    d = pipeline.job_dir(job["id"])
    for f in ("report.html", "model.xlsx", "model_bear.xlsx", "model_bull.xlsx", "result.json"):
        assert (d / f).exists()
    assert pipeline.find_by_share_token(j["share_token"]) == job["id"]


def test_unknown_ticker_offline_fails_cleanly(offline):
    from valuebot import pipeline

    job = pipeline.create_job({"ticker": "NOPE"})
    pipeline.run_job(job["id"])
    j = pipeline.load_job(job["id"])
    assert j["status"] == "error" and "not available offline" in j["error"]


def test_damodaran_dataset_parsers():
    import pandas as pd

    from valuebot.data import damodaran

    raw = pd.DataFrame([["Date updated: Jan 2026", None, None, None], [None] * 4,
                        ["Industry Name", "Number of firms", "Unlevered beta", "Unlevered beta corrected for cash"],
                        ["Software (System & Application)", 380, 1.21, 1.25], ["Drugs (Pharmaceutical)", 250, 1.02, 1.05]])
    t = damodaran.parse_industry_betas({"Industry Averages": raw})
    assert t["Software (System & Application)"] == 1.25  # prefers the cash-corrected column
    assert damodaran.best_match("Software—Application", t) == "Software (System & Application)"
    raw2 = pd.DataFrame([["Country", "Moody's rating", "Country Risk Premium"], ["India", "Baa3", 0.0277]])
    assert damodaran.parse_country_premiums({"ERPs": raw2}) == {"India": 0.0277}
