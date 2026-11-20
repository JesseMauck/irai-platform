"""LLM steps. Each function has a deterministic fallback so the pipeline runs without an API key.

Design rule: the LLM never does arithmetic that matters. It reads the data and
the thesis, then *chooses inputs* (with reasons) via a forced tool call; the
Python engine computes value. That keeps every number auditable in Excel.
"""
from __future__ import annotations

import json
from typing import Any

from ..config import settings
from ..engine.common import Driver
from . import prompts


STORY_FIELDS = [
    ("growth", "Growth / scaling story: how big can revenues get (market size × share)?"),
    ("profitability", "Profitability story: unit economics, economies of scale, target margin"),
    ("efficiency", "Growth efficiency story: how much reinvestment growth needs"),
    ("risk", "Risk story: operating risk, leverage, country exposure, chance of failure"),
    ("moat", "Competitive advantages: how long can excess returns last?"),
]


def _client():
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _tool_call(system: str, user: str, tool: dict, model: str | None = None, max_tokens: int = 4000) -> dict:
    resp = _client().messages.create(
        model=model or settings.model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("Model did not return a tool call")


def _fmt(snap: dict, metrics: list[dict]) -> str:
    keep = {k: snap.get(k) for k in ("ticker", "name", "sector", "industry", "country", "currency", "price",
                                     "shares", "market_cap", "beta", "summary", "dividend_rate", "consensus")}
    hist = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()} for m in metrics]
    return json.dumps({"company": keep, "history": hist}, default=str, indent=1)


# --------------------------------------------------------------------------- thesis
def draft_thesis(snap: dict, metrics: list[dict], stance: str) -> dict[str, Any]:
    if not settings.llm_enabled:
        return prompts.offline_thesis(snap, metrics, stance)
    tool = {
        "name": "submit_thesis",
        "description": "Submit the investment thesis and framing questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "thesis": {"type": "string", "description": "3-6 sentences, specific and falsifiable."},
                "stories": {"type": "object", "description": "One or two sentences for each element of the story.",
                            "properties": {k: {"type": "string", "description": d} for k, d in STORY_FIELDS},
                            "required": [k for k, _ in STORY_FIELDS]},
                "questions": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            },
            "required": ["thesis", "stories", "questions"],
        },
    }
    return _tool_call(prompts.SYSTEM_ANALYST, prompts.THESIS.format(stance=stance, data=_fmt(snap, metrics)),
                      tool, model=settings.fast_model, max_tokens=1500)


# --------------------------------------------------------------------------- research
def research(snap: dict, thesis: str) -> dict[str, Any]:
    """Web research with Claude's server-side web search tool. Returns briefing + cited sources."""
    if not settings.llm_enabled:
        news = snap.get("news") or []
        lines = [f"- {n['title']} ({n.get('publisher') or 'news'}, {n.get('date') or 'n.d.'})" for n in news]
        return {"briefing": "Recent headlines:\n" + "\n".join(lines) if lines else "No recent news available offline.",
                "sources": [{"label": n["title"], "url": n.get("url")} for n in news]}
    messages = [{"role": "user", "content": prompts.RESEARCH.format(
        name=snap["name"], ticker=snap["ticker"], thesis=thesis,
        headlines=json.dumps(snap.get("news", [])[:8], default=str))}]
    client = _client()
    text_parts: list[str] = []
    sources: dict[str, str] = {}
    for _ in range(4):  # continue through pause_turn
        resp = client.messages.create(
            model=settings.fast_model, max_tokens=4000, system=prompts.SYSTEM_ANALYST, messages=messages,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
        )
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
                for c in getattr(block, "citations", None) or []:
                    url = getattr(c, "url", None)
                    if url:
                        sources[url] = getattr(c, "title", None) or url
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    return {"briefing": "".join(text_parts).strip(),
            "sources": [{"label": t, "url": u} for u, t in sources.items()]}


# --------------------------------------------------------------------------- story -> numbers
def story_to_numbers(*, snap: dict, metrics: list[dict], method: str, drivers: list[Driver],
                     defaults: dict[str, float], why: dict[str, str], thesis: str, briefing: str,
                     cost_of_capital: dict, stories: dict | None = None, locked: dict | None = None,
                     market: dict | None = None, earnings: dict | None = None) -> tuple[dict[str, float], dict[str, str]]:
    if not settings.llm_enabled:
        return prompts.offline_story_adjust(defaults, why, thesis, drivers)

    props = {}
    for d in drivers:
        props[d.key] = {
            "type": "object",
            "properties": {"value": {"type": "number"}, "rationale": {"type": "string"}},
            "required": ["value", "rationale"],
            "description": f"{d.label} ({d.unit}; decimals for percentages). {d.story}.",
        }
    tool = {
        "name": "set_assumptions",
        "description": "Set every value driver for the valuation, each with a one-sentence rationale tied to the story.",
        "input_schema": {"type": "object", "properties": props, "required": [d.key for d in drivers]},
    }
    starting = {d.key: {"value": defaults[d.key], "basis": why.get(d.key, "")} for d in drivers}
    user = prompts.STORY_TO_NUMBERS.format(
        method=method, thesis=thesis, briefing=briefing[:6000], data=_fmt(snap, metrics),
        coc=json.dumps(cost_of_capital, default=str), starting=json.dumps(starting, indent=1),
        stories=json.dumps(stories or {}, indent=1), locked=json.dumps(locked or {}),
        market=json.dumps({k: v for k, v in (market or {}).items() if v is not None}),
        earnings=json.dumps([i["detail"] for i in (earnings or {}).get("items", [])]))
    out = _tool_call(prompts.SYSTEM_ANALYST, user, tool)

    values, rationale = {}, {}
    for d in drivers:
        item = out.get(d.key) or {}
        try:
            v = float(item.get("value"))
        except (TypeError, ValueError):
            v = defaults[d.key]
        # The model sometimes answers 12 for 12%: normalise obvious percent-as-whole-number slips.
        if d.unit == "pct" and abs(v) > 1.5 and (d.hi is None or d.hi <= 2):
            v = v / 100
        values[d.key] = d.clamp(v)
        rationale[d.key] = item.get("rationale") or why.get(d.key, "")
    return values, rationale


# --------------------------------------------------------------------------- plausible scenarios
def scenarios(*, snap: dict, method: str, drivers: list[Driver], key_drivers: list[str], base: dict[str, float],
              thesis: str, briefing: str) -> list[dict] | None:
    """Ask for 3 coherent scenarios where drivers move together (Damodaran's 'plausible scenarios').

    Returns None offline, so the engine's default interacting scenarios are used.
    """
    if not settings.llm_enabled:
        return None
    dmap = {d.key: d for d in drivers}
    keyed = {k: {"label": dmap[k].label, "unit": dmap[k].unit, "base": base[k]} for k in key_drivers}
    tool = {
        "name": "submit_scenarios",
        "description": "Submit 3 plausible, internally consistent scenarios with probabilities summing to 1.",
        "input_schema": {"type": "object", "properties": {"scenarios": {"type": "array", "minItems": 2, "maxItems": 4, "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"}, "probability": {"type": "number"},
                "narrative": {"type": "string", "description": "1-2 sentences: what happens in the world"},
                "overrides": {"type": "object", "properties": {k: {"type": "number"} for k in key_drivers},
                              "description": "Driver values in this scenario (decimals for percentages)"},
            }, "required": ["name", "probability", "narrative", "overrides"]}}}, "required": ["scenarios"]},
    }
    user = prompts.SCENARIOS.format(name=snap["name"], method=method, thesis=thesis, briefing=briefing[:4000],
                                    drivers=json.dumps(keyed, indent=1))
    try:
        out = _tool_call(prompts.SYSTEM_ANALYST, user, tool, model=settings.fast_model, max_tokens=2000)
    except Exception:  # noqa: BLE001 - scenarios are an enhancement; fall back to defaults
        return None
    specs = []
    for s in out.get("scenarios", []):
        ov = {}
        for k, v in (s.get("overrides") or {}).items():
            if k in dmap:
                v = float(v)
                if dmap[k].unit == "pct" and abs(v) > 1.5:
                    v /= 100
                ov[k] = v
        specs.append({**s, "overrides": ov})
    return specs or None


# --------------------------------------------------------------------------- narrative
REPORT_SECTIONS = [
    ("bottom_line", "The bottom line"),
    ("company_story", "The business and its story"),
    ("history", "What the history tells us"),
    ("story_to_numbers", "The story behind the numbers"),
    ("risk", "Risk and the cost of capital"),
    ("valuation", "The valuation"),
    ("reverse_dcf", "What the market believes"),
    ("plausibility", "Possible, plausible, probable?"),
    ("sensitivity", "What drives the value"),
    ("probabilistic", "Scenarios, simulation and margin of safety"),
    ("peers", "Pricing and peer context"),
    ("consensus", "What others think"),
    ("thesis_test", "Testing the thesis"),
    ("risks", "Risks to the story"),
    ("change_my_mind", "What would change the conclusion"),
    ("metrics_to_watch", "Metrics to watch"),
    ("final_word", "The final word"),
]


def write_report(ctx: dict[str, Any]) -> dict[str, str]:
    if not settings.llm_enabled:
        return prompts.offline_report(ctx)
    tool = {
        "name": "submit_report",
        "description": "Submit the report sections as markdown.",
        "input_schema": {
            "type": "object",
            "properties": {"title": {"type": "string", "description": "Headline: company and ticker, then the central tension, e.g. 'X (TCKR): Great Company, Demanding Price'"},
                           "subtitle": {"type": "string", "description": "One line: the occasion or the question"},
                           **{k: {"type": "string", "description": title} for k, title in REPORT_SECTIONS}},
            "required": ["title", "subtitle"] + [k for k, _ in REPORT_SECTIONS],
        },
    }
    return _tool_call(prompts.SYSTEM_WRITER, prompts.REPORT.format(context=json.dumps(ctx, default=str, indent=1)[:60000]),
                      tool, max_tokens=16000)
