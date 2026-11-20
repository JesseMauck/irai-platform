"""Standalone HTML report (print-ready) + tornado chart image + optional PDF."""
from __future__ import annotations

import base64
import html
import io
from pathlib import Path
from typing import Any

import markdown as md
from jinja2 import Environment, select_autoescape

from ..llm.agent import REPORT_SECTIONS, STORY_FIELDS
from . import views


def tornado_png(sens: dict, title: str = "What drives value per share") -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = sens["drivers"][:10][::-1]
    base = sens["base_value"]
    fig, ax = plt.subplots(figsize=(8, 0.45 * len(rows) + 1.2), dpi=150)
    for i, r in enumerate(rows):
        lo, hi = sorted((r["low_value"], r["high_value"]))
        ax.barh(i, base - lo, left=lo, color="#C0504D", height=0.6)
        ax.barh(i, hi - base, left=base, color="#2E7D5B", height=0.6)
        ax.text(lo, i, f"{lo:,.1f} ", va="center", ha="right", fontsize=7)
        ax.text(hi, i, f" {hi:,.1f}", va="center", ha="left", fontsize=7)
    ax.axvline(base, color="#222", lw=1)
    ax.set_yticks(range(len(rows)), [r["label"] for r in rows], fontsize=8)
    ax.set_title(f"{title} (base {base:,.2f})", fontsize=10, loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="x", labelsize=8)
    lo_all = min(min(r["low_value"], r["high_value"]) for r in rows)
    hi_all = max(max(r["low_value"], r["high_value"]) for r in rows)
    pad = (hi_all - lo_all) * 0.15 or 1
    ax.set_xlim(lo_all - pad, hi_all + pad)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def simulation_png(sim: dict, price: float | None) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    counts, edges = sim["histogram"]["counts"], sim["histogram"]["edges"]
    pc = sim["percentiles"]
    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=150)
    widths = [edges[i + 1] - edges[i] for i in range(len(counts))]
    ax.bar(edges[:-1], counts, width=widths, align="edge", color="#9DB8AD", edgecolor="white")
    p50 = pc.get(50, pc.get("50"))
    ax.axvline(p50, color="#1f5f4a", lw=1.5, label=f"Median {p50:,.2f}")
    if price:
        ax.axvline(price, color="#b4433a", lw=1.5, ls="--", label=f"Price {price:,.2f}")
    ax.set_title(f"Simulated value per share ({sim['n']:,} trials)", fontsize=10, loc="left")
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_yticks([])
    ax.tick_params(labelsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def curve_png(curve: dict) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pct = curve["unit"] == "pct"
    xs = [pt["x"] * (100 if pct else 1) for pt in curve["points"]]
    ys = [pt["value"] for pt in curve["points"]]
    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=150)
    ax.plot(xs, ys, color="#1f5f4a", lw=2)
    ax.axhline(curve["price"], color="#b4433a", ls="--", lw=1.2, label=f"Price {curve['price']:,.2f}")
    if curve.get("break_even") is not None:
        be = curve["break_even"] * (100 if pct else 1)
        ax.axvline(be, color="#888", lw=1, ls=":")
        ax.annotate(f"break-even {be:,.2f}{'%' if pct else ''}", (be, curve["price"]), fontsize=8,
                    xytext=(6, 8), textcoords="offset points")
    ax.set_xlabel(curve["label"] + (" (%)" if pct else ""), fontsize=8)
    ax.set_ylabel("Value per share", fontsize=8)
    ax.set_title(f"Value versus {curve['label'].lower()}", fontsize=10, loc="left")
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def _fmt(v: Any, unit: str) -> str:
    if v is None:
        return "—"
    if abs(v) < 1e-12:
        v = 0.0
    if unit == "pct":
        return f"{v:.1%}"
    if unit == "x":
        return f"{v:.2f}x"
    if unit == "money":
        return f"{v / 1e6:,.0f}"
    if unit == "years":
        return f"{v:.0f}"
    return f"{v:,.2f}"


TABLE_COLUMNS = {
    "fcff": [("revenue_growth", "Revenue growth", "pct"), ("revenue", "Revenue", "money"),
             ("operating_margin", "Operating margin", "pct"), ("ebit", "EBIT", "money"),
             ("nopat", "EBIT(1−t)", "money"), ("reinvestment", "Reinvestment", "money"),
             ("fcff", "FCFF", "money"), ("cost_of_capital", "Cost of capital", "pct"), ("pv_fcff", "PV(FCFF)", "money")],
    "ddm": [("eps_growth", "EPS growth", "pct"), ("eps", "EPS", "num"), ("payout", "Payout", "pct"),
            ("dps", "DPS", "num"), ("cost_of_equity", "Cost of equity", "pct"), ("pv_dps", "PV(DPS)", "num")],
    "excess_return": [("roe", "ROE", "pct"), ("cost_of_equity", "Cost of equity", "pct"),
                      ("beginning_book_equity", "Beginning BV", "money"), ("net_income", "Net income", "money"),
                      ("excess_return", "Excess return", "money"), ("pv_excess_return", "PV(excess)", "money")],
}

def _png(fig) -> bytes:
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def bridge_png(result: dict, price: float, shares: float) -> bytes:
    """Waterfall from PV of cash flows to value per share, with the market's equity value for contrast."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    b = {x["label"]: x["value"] for x in result["bridge"]}
    if "PV of FCFF, years 1-10" in b:
        steps = [("PV of FCFF\n(yrs 1-10)", b["PV of FCFF, years 1-10"]), ("PV of\nterminal value", b["PV of terminal value"]),
                 ("Failure\nadjustment", b["Adjusted for probability of failure"] - b["Value of operating assets"]),
                 ("Net debt &\nother claims", b["Value of common equity"] - b["Adjusted for probability of failure"])]
    else:
        first = next(iter(b.items()))
        steps = [(lab.replace(", ", ",\n"), v) for lab, v in list(b.items())[:4] if "per share" not in lab and "Shares" not in lab]
        steps = steps[:3] if steps else [first]
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
    run = 0.0
    for i, (lab, v) in enumerate(steps):
        ax.bar(i, v / 1e9, bottom=run / 1e9, color="#2e7d5b" if v >= 0 else "#b4433a", width=0.6)
        ax.text(i, (run + v) / 1e9, f"{v / 1e9:,.1f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=8)
        run += v
    eq = result["equity_value"]
    ax.bar(len(steps), eq / 1e9, color="#1d1d1f", width=0.6)
    ax.text(len(steps), eq / 1e9, f"{eq / 1e9:,.1f}\n({result['value_per_share']:,.2f}/sh)", ha="center", va="bottom", fontsize=8)
    mkt = price * shares
    ax.axhline(mkt / 1e9, color="#b4433a", ls="--", lw=1.2)
    ax.text(len(steps) + 0.35, mkt / 1e9, f"market {mkt / 1e9:,.1f}", fontsize=8, color="#b4433a", va="bottom", ha="right")
    ax.set_xticks(range(len(steps) + 1), [l for l, _ in steps] + ["Value of\nequity"], fontsize=8)
    ax.set_ylabel("bn", fontsize=8)
    ax.set_title("Value bridge", fontsize=10, loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    return _png(fig)


def fcff_png(table: list[dict]) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    yrs = [r["year"] for r in table]
    fig, ax = plt.subplots(figsize=(8, 3.0), dpi=150)
    ax.bar(yrs, [r["nopat"] / 1e9 for r in table], color="#9db8ad", width=0.4, label="After-tax operating income", align="edge")
    ax.bar([y - 0.4 for y in yrs], [-r["reinvestment"] / 1e9 for r in table], color="#d7c4c1", width=0.4, label="− Reinvestment", align="edge")
    ax.plot(yrs, [r["fcff"] / 1e9 for r in table], color="#1f5f4a", marker="o", lw=2, label="FCFF")
    ax.axhline(0, color="#888", lw=0.8)
    ax.set_xticks(yrs)
    ax.set_title("Cash flows by year (bn)", fontsize=10, loc="left")
    ax.legend(fontsize=7, frameon=False, ncol=3, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)
    fig.tight_layout()
    return _png(fig)


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{{ title }}</title>
<style>
 @page{size:Letter;margin:18mm 16mm}
 body{font:15px/1.6 Georgia,'Times New Roman',serif;color:#1d1d1f;max-width:820px;margin:40px auto;padding:0 24px}
 h1{font-size:30px;line-height:1.15;margin:0 0 8px} h2{font-size:20px;margin-top:34px;border-bottom:1px solid #ddd;padding-bottom:4px}
 .sub{color:#555;font-style:italic} .meta{color:#777;font:12px system-ui,sans-serif;margin-top:6px}
 .kpis{display:flex;gap:10px;margin:22px 0;font-family:system-ui,sans-serif}
 .kpi{flex:1;border:1px solid #e3e3e3;border-radius:8px;padding:10px 12px}
 .kpi b{display:block;font-size:20px} .kpi span{font-size:11px;color:#666}
 table{border-collapse:collapse;width:100%;font:11.5px system-ui,sans-serif;margin:12px 0}
 th,td{padding:5px 6px;border-bottom:1px solid #eee;text-align:right;vertical-align:top} th:first-child,td:first-child{text-align:left}
 td.l,th.l{text-align:left} th{background:#f3f2ee} tr.tot td{font-weight:600;background:#faf9f6}
 .boxhead{background:#1d1d1f;color:#fff;text-align:center;font-weight:600;letter-spacing:.04em}
 .demo{background:#fff1f0;border:1px solid #f3b4ae;padding:10px;border-radius:6px;font-family:system-ui}
 .note{color:#777;font-size:11px;font-family:system-ui,sans-serif} img{max-width:100%}
 .thesis{background:#f1f6f3;border-left:3px solid #1f5f4a;padding:10px 14px;font-style:italic}
 .pass{color:#2e7d5b} .flag{color:#b4433a;font-weight:600}
 @media print{body{margin:0;max-width:none} h2{break-after:avoid} table,img{break-inside:avoid}}
</style></head><body>
<h1>{{ title }}</h1>
<div class="sub">{{ subtitle }}</div>
<div class="meta">{{ c.name }} ({{ c.ticker }}) · {{ date }} · {{ method_title }}</div>
{% if c.demo %}<p class="demo"><b>Demo data.</b> This company and its numbers are fictional.</p>{% endif %}
<div class="kpis">
 <div class="kpi"><span>Value / share</span><b>{{ "{:,.2f}".format(r.value_per_share) }}</b></div>
 <div class="kpi"><span>Price</span><b>{{ "{:,.2f}".format(r.price) }}</b></div>
 <div class="kpi"><span>Upside / (downside)</span><b>{{ "{:+.1%}".format(r.upside) if r.upside is not none else "—" }}</b></div>
 <div class="kpi"><span>Simulated P(undervalued)</span><b>{{ "{:.0%}".format(sim.prob_undervalued) if sim.prob_undervalued is defined else "—" }}</b></div>
 <div class="kpi"><span>Bear – Bull</span><b>{{ "{:,.0f}".format(bear) }} – {{ "{:,.0f}".format(bull) }}</b></div>
</div>
<p class="thesis">{{ thesis }}</p>
{% for key, stitle, body in sections %}
<h2 id="{{ key }}">{{ stitle }}</h2>
{{ body|safe }}
{% if key == "history" and earnings and earnings["items"] %}
<table><tr><th>Measuring earnings right</th><th>EBIT effect (m)</th><th class="l">Detail</th></tr>
<tr><td>Reported operating income</td><td>{{ fmt(earnings.ebit_reported, "money") }}</td><td></td></tr>
{% for i in earnings["items"] %}<tr><td>{{ i["item"] }}</td><td>{{ fmt(i.ebit, "money") }}</td><td class="l">{{ i.detail }}</td></tr>{% endfor %}
<tr class="tot"><td>Adjusted operating income</td><td>{{ fmt(earnings.ebit_adjusted, "money") }}</td><td></td></tr></table>
{% elif key == "story_to_numbers" %}
<table><tr><th>Chapter</th><th class="l">The storyline</th><th class="l">The numbers</th></tr>
{% for ch in chapters %}<tr><td><b>{{ ch.chapter }}</b></td><td class="l">{{ ch.story }}</td><td class="l">{{ ch.numbers }}</td></tr>{% endfor %}</table>
{% if segs %}<table><tr><th>Business</th><th>Year-10 revenue</th><th>Target margin</th></tr>
{% for s in segs.rows %}<tr><td>{{ s.name }}</td><td>{{ fmt(s.revenue_y10, "money") }}m</td><td>{{ fmt(s.target_margin, "pct") }}</td></tr>{% endfor %}
<tr class="tot"><td>Consolidated</td><td>{{ fmt(segs.revenue, "money") }}m</td><td>{{ fmt(segs.margin, "pct") }}</td></tr></table>
<p class="note">Margin reconciliation: {{ segs.text }}</p>{% endif %}
<table><tr><th>Driver</th><th>Value</th><th class="l">Why</th></tr>
{% for a in assumptions %}<tr><td>{{ a.label }}</td><td>{{ a.fmt }}</td><td class="l">{{ a.rationale }}</td></tr>{% endfor %}</table>
{% elif key == "valuation" %}
{% if onepage %}<table><tr><td class="boxhead" colspan="6">THE ASSUMPTIONS</td></tr>
<tr><th></th><th>Base year</th><th>Years 1-5</th><th>Years 6-10</th><th>After year 10</th><th class="l">Link to story</th></tr>
{% for o in onepage %}<tr><td><b>{{ o.item }}</b></td><td>{{ o.base }}</td><td>{{ o.y1_5 }}</td><td>{{ o.y6_10 }}</td><td>{{ o.after }}</td><td class="l">{{ o.story[:140] }}</td></tr>{% endfor %}</table>{% endif %}
<table><tr><td class="boxhead" colspan="{{ table|length + 2 }}">THE CASH FLOWS ({{ c.currency }} m)</td></tr>
<tr><th>Year</th>{% for row in table %}<th>{{ row.year }}</th>{% endfor %}<th>Terminal</th></tr>
{% for col in columns %}<tr><td>{{ col[1] }}</td>{% for row in table %}<td>{{ fmt(row[col[0]], col[2]) }}</td>{% endfor %}<td>{{ fmt(terminal_row.get(col[0]), col[2]) if terminal_row.get(col[0]) is not none else "" }}</td></tr>{% endfor %}
</table>
<table><tr><td class="boxhead" colspan="2">THE VALUE</td></tr>
{% for b in bridge %}<tr class="{{ 'tot' if b.tot else '' }}"><td>{{ b.label }}</td><td>{{ b.fmt }}</td></tr>{% endfor %}</table>
<img alt="Value bridge" src="data:image/png;base64,{{ bridge_img }}">
{% if fcff_img %}<img alt="Cash flows" src="data:image/png;base64,{{ fcff_img }}">{% endif %}
<p class="note">Money in {{ c.currency }} millions except per-share figures.</p>
{% elif key == "reverse_dcf" and rev and rev.rows %}
<table><tr><th></th><th>My estimates</th><th>Market-implied</th></tr>
{% for x in rev.rows %}<tr><td>{{ "<b>"|safe if x.diverges }}{{ x.label }}{{ "</b>"|safe if x.diverges }}</td><td>{{ fmt(x.mine, x.unit) }}</td><td>{{ fmt(x.market, x.unit) }}</td></tr>{% endfor %}
<tr class="tot"><td>Value per share</td><td>{{ "{:,.2f}".format(rev.base_value) }}</td><td>{{ "{:,.2f}".format(rev.implied_value) }}</td></tr></table>
<p class="note">{{ "Solved exactly: market-implied drivers reproduce the price." if rev.converged else "Did not converge within driver bounds." }} {{ rev.note }}</p>
{% elif key == "plausibility" %}
<table><tr><th>Narrative test</th><th>Question</th><th>Result</th><th class="l">Detail</th></tr>
{% for t in tests %}<tr><td>{{ t.test }}</td><td>{{ {"impossible": "Possible?", "implausible": "Plausible?", "improbable": "Probable?"}[t.level] }}</td><td class="{{ 'pass' if t.pass else 'flag' }}">{{ "Pass" if t.pass else "Flag" }}</td><td class="l">{{ t.detail }}</td></tr>{% endfor %}</table>
{% if vg %}<table><tr><th>Where the value comes from</th><th>m</th></tr><tr><td>Existing assets (no growth)</td><td>{{ fmt(vg.existing_assets, "money") }}</td></tr>
<tr><td>Growth assets</td><td>{{ fmt(vg.growth_assets, "money") }} ({{ "{:.0%}".format(vg.growth_share) if vg.growth_share is not none else "—" }})</td></tr></table>{% endif %}
{% elif key == "sensitivity" %}
<img alt="Tornado chart" src="data:image/png;base64,{{ tornado }}">
<table><tr><th>Driver</th><th>Low case</th><th>Base case</th><th>High case</th><th>Spread</th></tr>
{% for d in sens.drivers[:8] %}<tr><td>{{ d.label }}</td><td>{{ "{:,.2f}".format([d.low_value, d.high_value]|min) }}</td><td>{{ "{:,.2f}".format(sens.base_value) }}</td><td>{{ "{:,.2f}".format([d.low_value, d.high_value]|max) }}</td><td>{{ "{:,.2f}".format(d.range) }}</td></tr>{% endfor %}</table>
{% elif key == "probabilistic" %}
<img alt="Value versus key driver" src="data:image/png;base64,{{ curve_img }}">
<table><tr><th>Key driver</th><th>Base case</th><th>Break-even (value = price)</th></tr>
{% for b in prob.break_even %}<tr><td>{{ b.label }}</td><td>{{ fmt(b.base, b.unit) }}</td><td>{{ fmt(b.break_even, b.unit) if b.break_even is not none else "not reachable" }}</td></tr>{% endfor %}</table>
<table><tr><th>Scenario</th><th>Probability</th><th>Value / share</th><th class="l">Story</th></tr>
{% for s in prob.scenarios.scenarios %}<tr><td>{{ s.name }}</td><td>{{ "{:.0%}".format(s.probability) }}</td><td>{{ "{:,.2f}".format(s.value_per_share) }}</td><td class="l">{{ s.narrative }}</td></tr>{% endfor %}
<tr class="tot"><td>Probability-weighted</td><td>100%</td><td>{{ "{:,.2f}".format(prob.scenarios.expected_value) }}</td><td></td></tr></table>
<img alt="Simulated value distribution" src="data:image/png;base64,{{ sim_img }}">
<table><tr><th>P10</th><th>P25</th><th>Median</th><th>P75</th><th>P90</th><th>P(undervalued)</th><th>Margin of safety</th><th>Buy below</th></tr>
<tr>{% for k in [10,25,50,75,90] %}<td>{{ "{:,.2f}".format(pct_of(k)) }}</td>{% endfor %}
<td>{{ "{:.0%}".format(sim.prob_undervalued) if sim.prob_undervalued is defined else "—" }}</td>
<td>{{ "{:.0%}".format(sim.margin_of_safety) if sim.margin_of_safety is not none else "—" }}</td>
<td>{{ "{:,.2f}".format(sim.buy_below) if sim.buy_below is not none else "—" }}</td></tr></table>
<p class="note">Simulated drivers: {% for d in sim.drivers %}{{ d.label }} (mean {{ fmt(d.mean, d.unit) }}, sd {{ fmt(d.sd, d.unit) }}){% if not loop.last %}; {% endif %}{% endfor %}.
Margin of safety = 1 − P25 / median, so it widens for riskier firms.</p>
<table><tr><th>Consistency test</th><th>Result</th><th class="l">Detail</th></tr>
{% for c2 in prob.checks %}<tr><td>{{ c2.test }}</td><td class="{{ 'pass' if c2.pass else 'flag' }}">{{ "Pass" if c2.pass else "Fail" }}</td><td class="l">{{ c2.detail }}</td></tr>{% endfor %}</table>
{% elif key == "peers" and mult %}
<table><tr><th></th><th>EV / sales</th><th>EV / EBIT</th><th>PE</th><th>P / book</th></tr>
{% for lab, m in [("At my value", mult.at_value), ("At today's price", mult.at_price)] %}<tr><td>{{ lab }}</td>{% for k in ["ev_sales","ev_ebit","pe","pbv"] %}<td>{{ "{:,.1f}x".format(m[k]) if m[k] is not none else "—" }}</td>{% endfor %}</tr>{% endfor %}</table>
{% elif key == "consensus" and cons and cons.target_mean_price %}
<table><tr><th>Source</th><th>Value / target</th><th class="l">Basis</th></tr>
<tr><td>This valuation</td><td>{{ "{:,.2f}".format(r.value_per_share) }}</td><td class="l">{{ method_title }}</td></tr>
<tr><td>Analyst mean target{% if cons.analyst_count %} ({{ cons.analyst_count }} analysts){% endif %}</td><td>{{ "{:,.2f}".format(cons.target_mean_price) }}</td><td class="l">{{ cons.recommendation or "" }}{% if cons.target_low_price %} · range {{ "{:,.2f}".format(cons.target_low_price) }}–{{ "{:,.2f}".format(cons.target_high_price) }}{% endif %}</td></tr>
<tr><td>Current price</td><td>{{ "{:,.2f}".format(r.price) }}</td><td class="l">Market</td></tr></table>
{% elif key == "final_word" %}
<table><tr><td class="boxhead" colspan="2">VALUATION SUMMARY</td></tr>
{% for k, v in summary %}<tr><td>{{ k }}</td><td>{{ v }}</td></tr>{% endfor %}</table>
{% endif %}
{% endfor %}
<h2>Sources</h2><ol class="note">
{% for s in sources %}<li>{% if s.url %}<a href="{{ s.url }}">{{ s.label }}</a>{% else %}{{ s.label }}{% endif %}</li>{% endfor %}
</ol>
<p class="note">This analysis is for informational and educational purposes only. It is not investment advice and nothing in it
is a recommendation to buy, sell or hold any security. It is an AI-generated starting point: the assumptions reflect judgment
and can be wrong. Review the sources and assumptions and do your own research before relying on it.</p>
</body></html>"""


def render_html(ctx: dict[str, Any], sections: dict[str, str], date: str) -> str:
    env = Environment(autoescape=select_autoescape(["html"]))
    r = ctx["result"]
    a_rows = [{"label": a["label"], "fmt": _fmt(a["value"], a["unit"]), "rationale": a["rationale"]}
              for a in ctx["assumptions"].values()]
    bridge = []
    for b in r["bridge"]:
        lab = b["label"]
        if "growth" in lab.lower():
            f = _fmt(b["value"], "pct")
        elif "Shares" in lab:
            f = f"{b['value'] / 1e6:,.1f}m"
        elif "per share" in lab:
            f = f"{b['value']:,.2f}"
        else:
            f = _fmt(b["value"], "money")
        bridge.append({"label": lab, "fmt": f, "tot": lab.startswith(("Value of", "Estimated"))})
    prob = ctx["probabilistic"]
    sim = prob["simulation"]
    pc = sim["percentiles"]
    t = r["terminal"]
    terminal_row = ({"revenue_growth": t["growth"], "revenue": t["revenue"], "operating_margin": ctx["inputs"].get("target_operating_margin"),
                     "ebit": t["ebit"], "nopat": t["nopat"], "reinvestment": t["nopat"] * t["reinvestment_rate"], "fcff": t["fcff"],
                     "cost_of_capital": t["cost_of_capital"]} if ctx["method"] == "fcff" else
                    {"eps_growth": t["growth"], "eps": t.get("eps"), "payout": t.get("payout"), "dps": t.get("dps"),
                     "cost_of_equity": t["cost_of_equity"]} if ctx["method"] == "ddm" else
                    {"roe": t.get("roe"), "cost_of_equity": t["cost_of_equity"], "excess_return": t.get("excess_return")})
    secs = [(k, ttl, md.markdown(sections.get(k, ""), extensions=["extra"])) for k, ttl in REPORT_SECTIONS]
    title = sections.get("title") or f"{ctx['company']['name']} ({ctx['company']['ticker']})"
    return env.from_string(TEMPLATE).render(
        title=title, subtitle=sections.get("subtitle", ""), c=ctx["company"], r=r, date=date,
        method_title=ctx["method_title"], thesis=html.unescape(ctx["thesis"]), sections=secs, assumptions=a_rows,
        table=r["table"], columns=TABLE_COLUMNS[ctx["method"]], terminal_row=terminal_row, fmt=_fmt, bridge=bridge,
        tornado=base64.b64encode(tornado_png(ctx["sensitivity"])).decode(), sens=ctx["sensitivity"],
        bear=ctx["sensitivity"]["scenarios"]["bear"]["value_per_share"],
        bull=ctx["sensitivity"]["scenarios"]["bull"]["value_per_share"], sources=ctx["sources"],
        earnings=ctx.get("earnings"), tests=ctx.get("narrative_tests", []),
        chapters=views.chapters(ctx), onepage=views.one_page(ctx), summary=views.summary(ctx),
        segs=ctx.get("segment_economics"), rev=prob.get("reverse_dcf"),
        vg=(ctx.get("insights") or {}).get("value_of_growth"), mult=(ctx.get("insights") or {}).get("multiples"),
        cons=ctx["company"].get("consensus") or {}, prob=prob, sim=sim, pct_of=lambda k: pc.get(k, pc.get(str(k))),
        sim_img=base64.b64encode(simulation_png(sim, r["price"])).decode(),
        curve_img=base64.b64encode(curve_png(prob["curve"])).decode(),
        bridge_img=base64.b64encode(bridge_png(r, r["price"], ctx["company"]["shares"])).decode(),
        fcff_img=base64.b64encode(fcff_png(r["table"])).decode() if ctx["method"] == "fcff" else None,
    )


def write_pdf(html_path: Path, pdf_path: Path) -> bool:
    """PDF via headless Chromium (Playwright) if available, else WeasyPrint; otherwise the UI
    falls back to the browser's print dialog."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri())
            page.pdf(path=str(pdf_path), format="Letter", print_background=True,
                     margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
                     display_header_footer=True, header_template="<span></span>",
                     footer_template='<div style="font-size:8px;width:100%;text-align:center;color:#888">'
                                     '<span class="pageNumber"></span> / <span class="totalPages"></span></div>')
            browser.close()
        return True
    except Exception:  # noqa: BLE001
        pass
    try:
        from weasyprint import HTML
    except ImportError:
        return False
    HTML(filename=str(html_path)).write_pdf(str(pdf_path))
    return True
