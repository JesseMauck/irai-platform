"""Prompts, plus template-based fallbacks used when no API key is configured."""
from __future__ import annotations

import datetime as dt
from typing import Any

SYSTEM_ANALYST = """You are a valuation analyst who works in the tradition of Aswath Damodaran's
"narrative and numbers" approach. Principles you follow:
- Every number must connect to a story, and every story must show up in a number.
- The four levers are growth, profitability (target margin), reinvestment efficiency (sales-to-capital) and risk.
- Stable growth can never exceed the risk-free rate; in stable growth, return on capital drifts toward the cost of capital unless the moat is durable.
- Be specific, skeptical and willing to disagree with the thesis you were given. Never pad.
- Percentages are decimals (0.12 means 12%)."""

SYSTEM_WRITER = """You write valuation reports as essays, in the voice of a thoughtful, plain-spoken finance professor
writing on his blog: first person ("I"), short paragraphs, concrete numbers, honest about uncertainty, no hype,
no investment advice. Open with the big picture and the central tension, not with boilerplate. Each section should
say something; if the data does not support a point, say less. You explain *why* each number is what it is. Use markdown (paragraphs, occasional bullet
lists, **bold** sparingly). Cite sources inline as markdown links only when a URL is provided in the context;
never invent URLs, facts or figures that are not in the context. All figures you quote must match the context."""

THESIS = """Draft a {stance} investment thesis for this company that a valuation can test. Keep it simple and
focused. Break the story into its five elements (growth/scaling, profitability, growth efficiency, risk,
competitive advantages), each concrete enough to become a number. Add 3-5 framing questions the valuation
should answer (how big can revenues get, how profitable at scale, how much reinvestment, how risky, when mature).
Ground it in the data below; do not invent facts.

{data}"""

RESEARCH = """Research {name} ({ticker}) for a valuation. Thesis under test:
"{thesis}"

Search for: the latest quarterly results and guidance, major strategic news from the last 6 months,
competitive dynamics, and anything that bears directly on revenue growth, margins, reinvestment or risk.
Known headlines: {headlines}

Write a compact briefing (300-500 words) of facts, each tied to its source. Separate facts from opinion."""

STORY_TO_NUMBERS = """Convert the story into valuation inputs for a {method} valuation.

THESIS UNDER TEST:
{thesis}

RESEARCH BRIEFING:
{briefing}

COMPANY DATA AND HISTORY:
{data}

THE STORY, ELEMENT BY ELEMENT (map each element to its drivers):
{stories}

MARKET SIZING FROM THE USER (total market, its growth, target share; use it to bound revenue):
{market}

EARNINGS ADJUSTMENTS ALREADY APPLIED TO THE BASE YEAR:
{earnings}

INPUTS LOCKED BY THE USER (keep exactly these values; explain them, do not change them):
{locked}

COST OF CAPITAL (computed):
{coc}

DATA-DRIVEN STARTING POINTS (adjust only where the story or evidence justifies it, and say why):
{starting}

Call set_assumptions with every driver. Rules from the class:
- Growth has to be earned: higher growth needs more reinvestment (lower sales-to-capital) unless the firm has excess capacity.
- Target operating margin cannot exceed the gross margin, and only reaches it with large economies of scale.
- Stable-phase return on capital moves toward the cost of capital unless there is a durable competitive advantage.
- Keep stable growth at or below the risk-free rate; keep the cost of capital close to the computed values unless
  there is a specific risk reason. Revenue in year 10 must stay well inside the total market.
- No fairy tales: no growth without reinvestment, profits without competition, or returns without risk."""

SCENARIOS = """Define 3 plausible scenarios for {name} ({method} valuation). Each scenario is a coherent story
about the world (macro environment, competitive response, execution), and the key drivers must move *together*
in a way that story implies; this is not a best-case / worst-case exercise. Give each a probability; probabilities
must sum to 1. Include the thesis outcome as one scenario.

Thesis: {thesis}

Briefing: {briefing}

Key drivers with base-case values:
{drivers}"""

REPORT = """Write the valuation report sections from this context. Each section 1-4 short paragraphs.
- title / subtitle: a headline that names the company and ticker and states the central tension.
- bottom_line: the lede. The big picture first, then value per share vs price, the verdict on the thesis in plain
  words, and the one or two drivers that matter most.
- valuation: walk through the one-page DCF (growth path, margin path, reinvestment, cost of capital, terminal value
  and its share of value, when FCFF turns positive), then the value bridge from operating assets to value per share.
- reverse_dcf: what the market must believe to justify the price (market-implied drivers vs mine); call out any
  implied input that is impossible or implausible.
- peers: the implied multiples at value and at price, and the conventional multiple for this kind of firm; use peer
  multiples only if they appear in the research briefing.
- consensus: analyst consensus (target prices, recommendation) and any external estimates in the research briefing,
  with sources; say plainly if there is none.
- metrics_to_watch: exactly three numbered metrics, each with the threshold where the story strengthens or breaks.
- final_word: two short paragraphs that close the argument; end on the gap between price and value.
- thesis_test: answer each framing question directly.
- story_to_numbers: walk through each major driver and why it was set where it is.
- sensitivity: interpret the tornado (largest swings) and the bull/bear values.
- probabilistic: interpret the break-even table (what the current price implies for each key driver, and how far
  that is from the base case), the plausible scenarios and their probability-weighted value, the simulated value
  distribution (median, 10th-90th percentile, probability the stock is undervalued) and the risk-adjusted margin
  of safety. Note which consistency checks failed, if any. Do not double count risk: a low value in a pessimistic
  scenario is not by itself a reason to reject the stock, because risk is already in the discount rate.
- plausibility: go through the narrative tests (possible / plausible / probable) and say plainly which parts of
  the story are fairy tales or runaway stories, if any. Mention the value of growth versus existing assets and the
  implied multiples as a pricing cross-check (the conventional multiple for the sector is given).
- change_my_mind: name the catalysts that could close the gap between price and value (earnings reports,
  corporate news, management changes, macro/regulatory news), and say what would be a narrative break, shift or change.
- risks and change_my_mind: specific, observable things (e.g. "if gross retention falls below X"); use the
  break-even values as the thresholds where the conclusion flips.
Tables are rendered separately, so do not reproduce tables.

CONTEXT:
{context}"""


# ---------------------------------------------------------------------------- offline fallbacks
def _pct(x):
    return "n/a" if x is None else f"{x:.1%}"


def _offline_stories(snap, metrics, stance) -> dict[str, str]:
    last = metrics[-1]
    up = {"bullish": 1, "bearish": -1}.get(stance, 0)
    return {
        "growth": ["Growth fades toward the market rate as the company gets bigger.",
                   "Revenue growth continues near its recent pace before fading.",
                   "The company keeps taking share in a growing market."][up + 1],
        "profitability": [f"Competition holds margins near today's {_pct(last.get('operating_margin'))}.",
                          f"Margins stay close to today's {_pct(last.get('operating_margin'))}.",
                          "Economies of scale push margins toward the gross-margin ceiling."][up + 1],
        "efficiency": "Reinvestment needs stay in line with history (sales-to-capital near current levels).",
        "risk": "Operating risk in line with its sector; low chance of failure.",
        "moat": ["Excess returns fade as competitors catch up.", "Returns drift toward the cost of capital.",
                 "Competitive advantages sustain returns above the cost of capital for a decade."][up + 1],
    }


def offline_thesis(snap: dict, metrics: list[dict], stance: str) -> dict[str, Any]:
    last = metrics[-1]
    g, m = last.get("revenue_growth"), last.get("operating_margin")
    name = snap["name"]
    if stance == "bearish":
        t = (f"{name}'s recent growth ({_pct(g)}) will slow faster than the market expects as its market matures, "
             f"and competition will cap operating margins near today's {_pct(m)}. At the current price, investors are "
             "paying for a growth and profitability path the business is unlikely to deliver.")
    elif stance == "bullish":
        t = (f"{name} can sustain double-digit revenue growth for several more years while scale pushes operating "
             f"margins well above today's {_pct(m)}. Reinvestment needs are modest relative to growth, so the market "
             "is underpricing the value of the next decade of cash flows.")
    else:
        t = (f"{name} is a solid business growing at {_pct(g)} with {_pct(m)} operating margins. The question is "
             "whether the current price already reflects a reasonable path for growth and margins, or demands more.")
    return {"thesis": t, "stories": _offline_stories(snap, metrics, stance), "questions": [
        "How big can revenues get (market size × market share), and how quickly?",
        "How profitable will the business be at scale, given its unit economics?",
        "How much must it reinvest to grow, and does that reinvestment earn more than the cost of capital?",
        "What growth and margin does the current price imply?",
    ]}


def offline_story_adjust(defaults, why, thesis, drivers):
    return dict(defaults), {d.key: why.get(d.key, "") for d in drivers}


def _val(v, unit):
    return _pct(v) if unit == "pct" else f"{v:.2f}"


def _offline_probabilistic(ctx: dict[str, Any]) -> str:
    p = ctx["probabilistic"]
    sim, sc, price = p["simulation"], p["scenarios"], ctx["result"]["price"]
    pc = sim["percentiles"]
    lines = []
    be = [b for b in p["break_even"] if b["break_even"] is not None]
    if be:
        lines.append("At today's price, the market is implicitly assuming:\n\n" + "\n".join(
            f"- **{b['label']}** of {_val(b['break_even'], b['unit'])} (our base case: {_val(b['base'], b['unit'])})"
            for b in be))
    lines.append("Across the scenarios, " + "; ".join(
        f"*{s['name']}* ({s['probability']:.0%}) gives {s['value_per_share']:,.2f}" for s in sc["scenarios"])
        + f", for a probability-weighted value of **{sc['expected_value']:,.2f}** per share.")
    lines.append(f"Simulating the key drivers together ({sim['n']:,} trials, with correlated inputs), the median value is "
                 f"{pc[50]:,.2f}, with 80% of outcomes between {pc[10]:,.2f} and {pc[90]:,.2f}. "
                 + (f"The stock is undervalued in {sim['prob_undervalued']:.0%} of trials. " if price else "")
                 + (f"The spread of outcomes implies a margin of safety of about {sim['margin_of_safety']:.0%}, "
                    f"i.e. a buy-below price near {sim['buy_below']:,.2f}." if sim.get("margin_of_safety") is not None else ""))
    failed = [c for c in p["checks"] if not c["pass"]]
    lines.append("Consistency checks: " + ("all stable-growth tests pass." if not failed else
                 "; ".join(f"{c['test']} fails ({c['detail']})" for c in failed)))
    return "\n\n".join(lines)


def _offline_reverse(ctx: dict[str, Any]) -> str:
    rv = ctx["probabilistic"].get("reverse_dcf") or {}
    if not rv.get("converged"):
        return "The price cannot be reached by moving the key drivers within sensible bounds."
    lines = [f"To justify {rv['price']:,.2f}, the key drivers would have to move together to:"]
    lines += [f"- **{r['label']}**: {_val(r['market'], r['unit'])} (mine: {_val(r['mine'], r['unit'])})" for r in rv["rows"]]
    lines.append(rv["note"])
    return "\n\n".join([lines[0], "\n".join(lines[1:-1]), lines[-1]])


def _offline_peers(ctx: dict[str, Any]) -> str:
    ins = ctx.get("insights") or {}
    m = ins.get("multiples")
    if not m:
        return ""
    f = lambda x: "n/a" if x is None else f"{x:,.1f}x"  # noqa: E731
    return (f"At today's price the stock trades at {f(m['at_price']['ev_sales'])} EV/sales and {f(m['at_price']['pe'])} "
            f"earnings; at our value those would be {f(m['at_value']['ev_sales'])} and {f(m['at_value']['pe'])}. "
            f"For this kind of company the conventional multiple is {ins['conventional_multiple']['multiple']} "
            f"({ins['conventional_multiple']['why'].lower()}).")


def _offline_consensus(ctx: dict[str, Any]) -> str:
    cons = (ctx["company"].get("consensus") or {})
    if not cons.get("target_mean_price"):
        return "There is no analyst consensus available for this company."
    return (f"{cons.get('analyst_count') or 'Several'} analysts have a mean target price of {cons['target_mean_price']:,.2f}"
            + (f" (range {cons['target_low_price']:,.2f}–{cons['target_high_price']:,.2f})" if cons.get("target_low_price") else "")
            + (f", with a consensus '{cons['recommendation']}' rating" if cons.get("recommendation") else "") + ".")


def _offline_plausibility(ctx: dict[str, Any]) -> str:
    tests = ctx.get("narrative_tests") or []
    bad = [t for t in tests if not t["pass"]]
    parts = [f"{len(tests) - len(bad)} of {len(tests)} narrative tests pass."]
    for lvl in ("impossible", "implausible", "improbable"):
        hits = [t for t in bad if t["level"] == lvl]
        if hits:
            parts.append(f"**{lvl.title()}:** " + " ".join(f"{t['test']} — {t['detail']}" for t in hits))
    ins = ctx.get("insights") or {}
    vg = ins.get("value_of_growth")
    if vg and vg.get("growth_share") is not None:
        parts.append(f"Existing assets are worth about {vg['existing_assets'] / 1e6:,.0f}m on their own; growth adds "
                     f"{vg['growth_assets'] / 1e6:,.0f}m ({vg['growth_share']:.0%} of operating-asset value).")
    m = ins.get("multiples")
    if m:
        def f(x):
            return "n/a" if x is None else f"{x:,.1f}x"
        parts.append(f"Pricing cross-check: at our value the stock trades at {f(m['at_value']['ev_sales'])} EV/sales, "
                     f"{f(m['at_value']['ev_ebit'])} EV/EBIT and {f(m['at_value']['pe'])} PE, versus "
                     f"{f(m['at_price']['ev_sales'])}, {f(m['at_price']['ev_ebit'])} and {f(m['at_price']['pe'])} at today's price. "
                     f"The conventional multiple for this kind of firm is {ins['conventional_multiple']['multiple']} "
                     f"({ins['conventional_multiple']['why'].lower()}).")
    ike = ins.get("implied_cost_of_equity")
    if ike and ike.get("ke") is not None:
        parts.append(f"At {ike['pbv']:.2f}x book and a {ike['roe']:.1%} ROE, the market is pricing in a cost of equity of "
                     f"{ike['ke']:.2%}, against {ike['model_ke']:.2%} in our model.")
    return "\n\n".join(parts)


def offline_report(ctx: dict[str, Any]) -> dict[str, str]:
    c, r, s = ctx["company"], ctx["result"], ctx["sensitivity"]
    vps, price = r["value_per_share"], r["price"]
    up = r.get("upside")
    verdict = ("looks undervalued" if up and up > 0.15 else "looks overvalued" if up and up < -0.15
               else "looks roughly fairly valued")
    top = s["drivers"][:3]
    top_txt = ", ".join(d["label"].lower() for d in top)
    sc = s["scenarios"]
    hist = ctx["metrics"]
    first, last = hist[0], hist[-1]
    a = ctx["assumptions"]

    def drv(k):
        x = a.get(k)
        if not x:
            return ""
        val = _pct(x["value"]) if x["unit"] == "pct" else f"{x['value']:.2f}{'x' if x['unit'] == 'x' else ''}"
        return f"- **{x['label']}: {val}.** {x['rationale']}"

    return {
        "bottom_line": (f"We estimate a value of **{vps:,.2f} {c['currency']} per share** against a price of "
                        f"{price:,.2f}, so the stock {verdict} ({_pct(up)} {'upside' if (up or 0) >= 0 else 'downside'}). "
                        f"The value is most sensitive to {top_txt}."),
        "company_story": c.get("summary") or f"{c['name']} operates in {c.get('industry')}.",
        "thesis_test": f"The thesis under test: *{ctx['thesis']}*\n\n" + "\n".join(
            f"- **{q}** See the valuation and sensitivity sections." for q in ctx.get("questions", [])),
        "history": (f"From FY{first['fiscal_year']} to FY{last['fiscal_year']}, revenue went from "
                    f"{(first['revenue'] or 0) / 1e6:,.0f}m to {(last['revenue'] or 0) / 1e6:,.0f}m. The latest operating "
                    f"margin is {_pct(last.get('operating_margin'))}, return on invested capital {_pct(last.get('roic'))} and "
                    f"return on equity {_pct(last.get('roe'))}."),
        "story_to_numbers": ("*Without an AI key the drivers are data-driven starting points from the filings and market "
                             "data; they are not adjusted to the thesis. Lock your own numbers in the Refine step.*\n\n"
                             + "\n".join(filter(None, (drv(k) for k in a)))),
        "risk": (f"Cost of equity is {_pct(ctx['cost_of_capital']['cost_of_equity'])} (beta "
                 f"{ctx['cost_of_capital']['beta']:.2f}); with a synthetic rating of {ctx['cost_of_capital']['rating']}, "
                 f"the cost of capital is {_pct(ctx['cost_of_capital']['wacc'])}, drifting to "
                 f"{_pct(ctx['cost_of_capital']['terminal_wacc'])} as the firm matures."),
        "valuation": f"Using the {ctx['method_title']}: {ctx['method_reason']}",
        "sensitivity": (f"The bear case gives {sc['bear']['value_per_share']:,.2f} and the bull case "
                        f"{sc['bull']['value_per_share']:,.2f} per share. Largest single swing: {top[0]['label'].lower()} "
                        f"({top[0]['low_value']:,.2f} to {top[0]['high_value']:,.2f})."),
        "probabilistic": _offline_probabilistic(ctx),
        "title": f"{c['name']} ({c['ticker']}): " + ("The Price Runs Ahead of the Story" if (up or 0) < -0.15 else
                                                     "The Story Is Worth More Than the Price" if (up or 0) > 0.15 else
                                                     "Priced About Right"),
        "subtitle": f"A {ctx['method_title']} valuation · {dt.date.today():%B %-d, %Y}",
        "reverse_dcf": _offline_reverse(ctx),
        "peers": _offline_peers(ctx),
        "consensus": _offline_consensus(ctx),
        "metrics_to_watch": "\n".join(f"{i}. **{d['label']}.** The base case uses {_val(d['base_input'], d['unit'])}; "
                                       f"moving to {_val(d['low_input'], d['unit'])}–{_val(d['high_input'], d['unit'])} "
                                       f"moves value to {min(d['low_value'], d['high_value']):,.2f}–{max(d['low_value'], d['high_value']):,.2f}."
                                       for i, d in enumerate(s["drivers"][:3], 1)),
        "final_word": (f"The value we estimate, {vps:,.2f} per share, rests on a story that is "
                       f"{'mostly' if not [t for t in ctx.get('narrative_tests', []) if not t['pass']] else 'only partly'} "
                       f"consistent with the company's history and economics. The price, {price:,.2f}, "
                       f"{'asks for more than that story delivers' if (up or 0) < 0 else 'asks for less than that story delivers'}."),
        "plausibility": _offline_plausibility(ctx),
        "risks": "- " + "\n- ".join(f"{d['label']} moves against the story" for d in top),
        "change_my_mind": "- " + "\n- ".join(
            [f"The verdict flips if {b['label'].lower()} reaches {_val(b['break_even'], b['unit'])} "
             f"(base case {_val(b['base'], b['unit'])})." for b in ctx["probabilistic"]["break_even"] if b["break_even"] is not None]
            or [f"If {d['label'].lower()} moves to its low or high case, value moves to "
                f"{d['low_value']:,.2f}–{d['high_value']:,.2f}." for d in top]),
    }
