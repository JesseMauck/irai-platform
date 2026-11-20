"""Editable Excel model with live formulas from inputs to value per share.

Conventions: blue font = input you can edit, black = formula. Every input cell
has a workbook-level defined name (in_<key>) so formulas read like the math.
Money is stored in full units and displayed in millions.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Callable

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from ..engine.common import YEARS
from ..engine.registry import METHODS

BLUE = Font(color="1F4FD1")
BOLD = Font(bold=True)
TITLE = Font(bold=True, size=14)
HEAD_FILL = PatternFill("solid", fgColor="1F2A44")
HEAD_FONT = Font(bold=True, color="FFFFFF")
KEY_FILL = PatternFill("solid", fgColor="FFF4CC")
THIN = Border(bottom=Side(style="thin", color="BBBBBB"))

FMT = {"pct": "0.00%", "x": "0.00x", "years": "0", "num": "#,##0.00", "money": '#,##0.0,,;(#,##0.0,,)',
       "ps": "#,##0.00", "shares": '#,##0.0,,', "df": "0.0000"}

BASE_LABELS = {
    "revenue0": ("Revenue, last fiscal year", "money"),
    "ebit0": ("Operating income (EBIT), last fiscal year", "money"),
    "invested_capital0": ("Invested capital (equity + debt + leases − cash)", "money"),
    "cash": ("Cash and marketable securities", "money"),
    "debt": ("Debt incl. lease liabilities", "money"),
    "minority_interest": ("Minority interests", "money"),
    "non_operating_assets": ("Non-operating assets (equity investments)", "money"),
    "options_value": ("Value of employee options outstanding", "money"),
    "shares": ("Shares outstanding (millions)", "shares"),
    "price": ("Current share price", "ps"),
    "failure_proceeds_pct": ("Proceeds if the firm fails, % of value", "pct"),
    "nol0": ("Net operating loss carried forward", "money"),
    "eps0": ("Earnings per share, last fiscal year", "ps"),
    "book_equity0": ("Book value of equity", "money"),
}


def _n(key: str) -> str:
    return f"in_{key}"


def _hdr(ws, row: int, values: list, start_col: int = 1):
    for i, v in enumerate(values):
        c = ws.cell(row=row, column=start_col + i, value=v)
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(horizontal="center" if i else "left")


def _name(wb: Workbook, name: str, ref: str):
    dn = DefinedName(name, attr_text=ref)
    try:
        wb.defined_names[name] = dn  # openpyxl >= 3.1
    except TypeError:  # pragma: no cover
        wb.defined_names.append(dn)


# ------------------------------------------------------------------------------ inputs
def _inputs_sheet(wb, method: str, assumptions: dict, rationale: dict, currency: str) -> dict[str, str]:
    ws = wb.create_sheet("Inputs")
    ws["A1"], ws["A1"].font = "Inputs — edit the blue cells", TITLE
    ws["A2"] = f"Money in {currency} millions. Percentages as %. Changing any blue cell reprices the model."
    cellmap: dict[str, str] = {}
    mod = METHODS[method]
    row = 4
    _hdr(ws, row, ["Base data (from filings / market)", "Value", "Unit"])
    row += 1
    for key in mod.BASE_FIELDS:
        label, fmt = BASE_LABELS.get(key, (key, "num"))
        ws.cell(row=row, column=1, value=label)
        c = ws.cell(row=row, column=2, value=assumptions.get(key, 0) or 0)
        c.font, c.number_format = BLUE, FMT[fmt]
        ws.cell(row=row, column=3, value=fmt)
        _name(wb, _n(key), f"Inputs!$B${row}")
        cellmap[key] = f"Inputs!B{row}"
        row += 1
    row += 1
    _hdr(ws, row, ["Value drivers (the story)", "Value", "Unit", "Rationale"])
    row += 1
    for d in mod.DRIVERS:
        ws.cell(row=row, column=1, value=d.label)
        c = ws.cell(row=row, column=2, value=assumptions[d.key])
        c.font, c.number_format, c.fill = BLUE, FMT[d.unit], KEY_FILL
        ws.cell(row=row, column=3, value=d.unit)
        ws.cell(row=row, column=4, value=rationale.get(d.key, "")).alignment = Alignment(wrap_text=True, vertical="top")
        _name(wb, _n(d.key), f"Inputs!$B${row}")
        cellmap[d.key] = f"Inputs!B{row}"
        row += 1
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 8
    ws.column_dimensions["D"].width = 90
    return cellmap


# ------------------------------------------------------------------------------ projection tables
RowSpec = tuple[str, str, str, Callable[[str, str, str], str] | None, Callable[[], str] | None]
# (key, label, fmt, formula(col, prev_col, t_cell) for years 1..10, terminal formula)


def _projection(ws, rows: list[RowSpec], base: dict[str, str], first_row: int = 4) -> dict[str, int]:
    """Columns: A label, B year 0, C..L years 1..10, M terminal."""
    _hdr(ws, first_row, ["", "Base"] + [f"Year {t}" for t in range(1, YEARS + 1)] + ["Terminal"])
    year_row = first_row + 1
    ws.cell(row=year_row, column=1, value="t")
    for t in range(0, YEARS + 1):
        ws.cell(row=year_row, column=2 + t, value=t)
    rowidx: dict[str, int] = {"t": year_row}
    r = year_row + 1
    for key, *_ in rows:
        rowidx[key] = r
        r += 1
    for key, label, fmt, f_year, f_term in rows:
        rr = rowidx[key]
        ws.cell(row=rr, column=1, value=label).border = THIN
        if key in base:
            ws.cell(row=rr, column=2, value=base[key]).number_format = FMT[fmt]
        for t in range(1, YEARS + 1):
            col = get_column_letter(2 + t)
            prev = get_column_letter(1 + t)
            if f_year:
                c = ws.cell(row=rr, column=2 + t, value="=" + f_year(col, prev, f"{col}${year_row}").format(**{k: v for k, v in rowidx.items()}))
                c.number_format = FMT[fmt]
        if f_term:
            c = ws.cell(row=rr, column=13, value="=" + f_term().format(**rowidx))
            c.number_format = FMT[fmt]
    ws.column_dimensions["A"].width = 34
    for i in range(2, 14):
        ws.column_dimensions[get_column_letter(i)].width = 12
    ws.freeze_panes = "B6"
    return rowidx


def _conv(start: str, end: str, t: str) -> str:
    """Excel version of engine.common.converge (flat through year 5, linear to year 10)."""
    return f"IF({t}<=5,{start},{start}+({end}-{start})*({t}-5)/5)"


def _fcff_sheet(wb) -> dict[str, str]:
    ws = wb.create_sheet("Valuation")
    ws["A1"], ws["A1"].font = "FCFF discounted cash flow", TITLE
    ws["A2"] = "Money in millions. All cells are formulas off the Inputs sheet."
    ws["O4"], ws["O4"].font = "Helpers", BOLD
    ws["O5"], ws["P5"] = "Stable growth (capped below mature WACC)", "=IF(in_terminal_growth>=in_wacc_terminal,in_wacc_terminal-0.005,in_terminal_growth)"
    ws["O6"], ws["P6"] = "Margin convergence year (whole years)", "=ROUND(MAX(1,in_margin_convergence_year),0)"
    ws["P5"].number_format = FMT["pct"]
    _name(wb, "calc_g", "Valuation!$P$5")
    _name(wb, "calc_n", "Valuation!$P$6")
    ws.column_dimensions["O"].width = 40
    m, mt = "in_operating_margin_y1", "in_target_operating_margin"
    rows: list[RowSpec] = [
        ("g", "Revenue growth", "pct",
         lambda c, p, t: f"IF({t}=1,in_revenue_growth_y1,{_conv('in_revenue_growth_y2_5', 'calc_g', t)})", lambda: "calc_g"),
        ("rev", "Revenue", "money", lambda c, p, t: f"{p}{{rev}}*(1+{c}{{g}})", lambda: "L{rev}*(1+M{g})"),
        ("margin", "Operating margin", "pct",
         lambda c, p, t: f"IF({t}=1,{m},IF({t}>=calc_n,{mt},{mt}-({mt}-{m})*(calc_n-{t})/(calc_n-1)))", lambda: mt),
        ("ebit", "Operating income (EBIT)", "money", lambda c, p, t: f"{c}{{rev}}*{c}{{margin}}", lambda: "M{rev}*M{margin}"),
        ("tax", "Tax rate", "pct", lambda c, p, t: _conv("in_effective_tax_rate", "in_marginal_tax_rate", t), lambda: "in_marginal_tax_rate"),
        ("nol", "NOL carried forward (beginning)", "money", lambda c, p, t: f"{p}{{nol_end}}", None),
        ("nopat", "EBIT − taxes (after NOL shield)", "money",
         lambda c, p, t: f"IF({c}{{ebit}}>0,{c}{{ebit}}-({c}{{ebit}}-MIN({c}{{nol}},{c}{{ebit}}))*{c}{{tax}},{c}{{ebit}})",
         lambda: "M{ebit}*(1-M{tax})"),
        ("nol_end", "NOL carried forward (ending)", "money",
         lambda c, p, t: f"IF({c}{{ebit}}>0,{c}{{nol}}-MIN({c}{{nol}},{c}{{ebit}}),{c}{{nol}}-{c}{{ebit}})", None),
        ("reinv", "− Reinvestment", "money", lambda c, p, t: f"({c}{{rev}}-{p}{{rev}})/IF({t}<=5,in_sales_to_capital,in_sales_to_capital_late)",
         lambda: "IF(in_terminal_roc<>0,M{g}/in_terminal_roc,0)*M{nopat}"),
        ("fcff", "FCFF", "money", lambda c, p, t: f"{c}{{nopat}}-{c}{{reinv}}", lambda: "M{nopat}-M{reinv}"),
        ("wacc", "Cost of capital", "pct", lambda c, p, t: _conv("in_wacc_initial", "in_wacc_terminal", t), lambda: "in_wacc_terminal"),
        ("df", "Cumulative discount factor", "df", lambda c, p, t: f"{p}{{df}}/(1+{c}{{wacc}})", None),
        ("pv", "PV of FCFF", "money", lambda c, p, t: f"{c}{{fcff}}*{c}{{df}}", None),
    ]
    idx = _projection(ws, rows, {"rev": "=in_revenue0", "ebit": "=in_ebit0", "df": 1, "nol_end": "=in_nol0"})
    ws.cell(row=idx["rev"], column=2).number_format = FMT["money"]
    ws.cell(row=idx["ebit"], column=2).number_format = FMT["money"]
    r = idx["pv"] + 2
    ws.cell(row=r, column=1, value="Terminal value").font = BOLD
    ws.cell(row=r, column=2, value=f"=M{idx['fcff']}/(M{idx['wacc']}-M{idx['g']})").number_format = FMT["money"]
    ws.cell(row=r + 1, column=1, value="PV of terminal value").font = BOLD
    ws.cell(row=r + 1, column=2, value=f"=B{r}*L{idx['df']}").number_format = FMT["money"]
    ws.cell(row=r + 2, column=1, value="Sum of PV of FCFF").font = BOLD
    ws.cell(row=r + 2, column=2, value=f"=SUM(C{idx['pv']}:L{idx['pv']})").number_format = FMT["money"]
    _name(wb, "calc_pv_tv", f"Valuation!$B${r + 1}")
    _name(wb, "calc_pv_cf", f"Valuation!$B${r + 2}")

    out = _output_sheet(wb, [
        ("PV of FCFF, years 1-10", "=calc_pv_cf", "money"),
        ("PV of terminal value", "=calc_pv_tv", "money"),
        ("Value of operating assets", "=B5+B6", "money"),
        ("Probability of failure", "=in_prob_failure", "pct"),
        ("Value adjusted for failure", "=B7*(1-B8)+B7*in_failure_proceeds_pct*B8", "money"),
        ("− Debt", "=-in_debt", "money"),
        ("− Minority interests", "=-in_minority_interest", "money"),
        ("+ Cash", "=in_cash", "money"),
        ("+ Non-operating assets", "=in_non_operating_assets", "money"),
        ("Value of equity", "=SUM(B9:B13)", "money"),
        ("− Value of options", "=-in_options_value", "money"),
        ("Value of common equity", "=B14+B15", "money"),
        ("Shares outstanding", "=in_shares", "shares"),
        ("Estimated value per share", "=B16/B17", "ps"),
    ])
    out["idx"] = idx
    return out


def _ddm_sheet(wb) -> dict[str, str]:
    ws = wb.create_sheet("Valuation")
    ws["A1"], ws["A1"].font = "Dividend discount model", TITLE
    ws["O4"], ws["O4"].font = "Helpers", BOLD
    ws["O5"], ws["P5"] = "Stable growth (capped below stable Ke)", "=IF(in_terminal_growth>=in_cost_of_equity_stable,in_cost_of_equity_stable-0.005,in_terminal_growth)"
    ws["O6"], ws["P6"] = "Expected growth, years 1-5 = ROE × (1 − payout)", "=in_roe_high*(1-in_payout_high)"
    ws["O7"], ws["P7"] = "Stable payout = 1 − g / ROE", "=1-calc_g/in_roe_stable"
    for c in ("P5", "P6", "P7"):
        ws[c].number_format = FMT["pct"]
    _name(wb, "calc_g", "Valuation!$P$5")
    _name(wb, "calc_g_high", "Valuation!$P$6")
    _name(wb, "calc_payout_s", "Valuation!$P$7")
    ws.column_dimensions["O"].width = 44
    rows: list[RowSpec] = [
        ("g", "EPS growth", "pct", lambda c, p, t: _conv("calc_g_high", "calc_g", t), lambda: "calc_g"),
        ("eps", "Earnings per share", "ps", lambda c, p, t: f"{p}{{eps}}*(1+{c}{{g}})", lambda: "L{eps}*(1+M{g})"),
        ("payout", "Payout ratio", "pct", lambda c, p, t: _conv("in_payout_high", "calc_payout_s", t), lambda: "calc_payout_s"),
        ("dps", "Dividends per share", "ps", lambda c, p, t: f"{c}{{eps}}*{c}{{payout}}", lambda: "M{eps}*M{payout}"),
        ("ke", "Cost of equity", "pct", lambda c, p, t: _conv("in_cost_of_equity_high", "in_cost_of_equity_stable", t), lambda: "in_cost_of_equity_stable"),
        ("df", "Cumulative discount factor", "df", lambda c, p, t: f"{p}{{df}}/(1+{c}{{ke}})", None),
        ("pv", "PV of dividends", "ps", lambda c, p, t: f"{c}{{dps}}*{c}{{df}}", None),
    ]
    idx = _projection(ws, rows, {"eps": "=in_eps0", "df": 1})
    ws.cell(row=idx["eps"], column=2).number_format = FMT["ps"]
    r = idx["pv"] + 2
    ws.cell(row=r, column=1, value="Terminal price").font = BOLD
    ws.cell(row=r, column=2, value=f"=M{idx['dps']}/(M{idx['ke']}-M{idx['g']})").number_format = FMT["ps"]
    ws.cell(row=r + 1, column=1, value="PV of terminal price").font = BOLD
    ws.cell(row=r + 1, column=2, value=f"=B{r}*L{idx['df']}").number_format = FMT["ps"]
    _name(wb, "calc_pv_tv", f"Valuation!$B${r + 1}")
    _name(wb, "calc_pv_cf", f"Valuation!$B${r + 2}")
    ws.cell(row=r + 2, column=1, value="Sum of PV of dividends").font = BOLD
    ws.cell(row=r + 2, column=2, value=f"=SUM(C{idx['pv']}:L{idx['pv']})").number_format = FMT["ps"]
    return _output_sheet(wb, [
        ("Expected growth, years 1-5", "=calc_g_high", "pct"),
        ("PV of dividends, years 1-10", "=calc_pv_cf", "ps"),
        ("PV of terminal price", "=calc_pv_tv", "ps"),
        ("Shares outstanding", "=in_shares", "shares"),
        ("Value of equity", "=B10*B8", "money"),
        ("Estimated value per share", "=B6+B7", "ps"),
    ])


def _excess_sheet(wb) -> dict[str, str]:
    ws = wb.create_sheet("Valuation")
    ws["A1"], ws["A1"].font = "Excess return model", TITLE
    ws["O4"], ws["O4"].font = "Helpers", BOLD
    ws["O5"], ws["P5"] = "Stable growth (capped below stable Ke)", "=IF(in_terminal_growth>=in_cost_of_equity_stable,in_cost_of_equity_stable-0.005,in_terminal_growth)"
    ws["O6"], ws["P6"] = "Stable payout = 1 − g / ROE", "=IF(in_roe_stable<>0,1-calc_g/in_roe_stable,1)"
    ws["P5"].number_format = ws["P6"].number_format = FMT["pct"]
    _name(wb, "calc_g", "Valuation!$P$5")
    _name(wb, "calc_payout_s", "Valuation!$P$6")
    ws.column_dimensions["O"].width = 40
    rows: list[RowSpec] = [
        ("roe", "Return on equity", "pct",
         lambda c, p, t: f"IF({t}<=5,in_roe_y1+(in_roe_target-in_roe_y1)*({t}-1)/4,in_roe_target+(in_roe_stable-in_roe_target)*({t}-5)/5)",
         lambda: "in_roe_stable"),
        ("ke", "Cost of equity", "pct", lambda c, p, t: _conv("in_cost_of_equity_high", "in_cost_of_equity_stable", t), lambda: "in_cost_of_equity_stable"),
        ("bv_open", "Beginning book equity", "money", lambda c, p, t: f"{p}{{bv_end}}", lambda: "L{bv_end}"),
        ("ni", "Net income", "money", lambda c, p, t: f"{c}{{roe}}*{c}{{bv_open}}", None),
        ("payout", "Payout ratio", "pct", lambda c, p, t: _conv("in_payout_high", "calc_payout_s", t), None),
        ("excess", "Excess equity return", "money", lambda c, p, t: f"({c}{{roe}}-{c}{{ke}})*{c}{{bv_open}}",
         lambda: "(M{roe}-M{ke})*M{bv_open}"),
        ("df", "Cumulative discount factor", "df", lambda c, p, t: f"{p}{{df}}/(1+{c}{{ke}})", None),
        ("pv", "PV of excess return", "money", lambda c, p, t: f"{c}{{excess}}*{c}{{df}}", None),
        ("bv_end", "Ending book equity", "money", lambda c, p, t: f"{c}{{bv_open}}+{c}{{ni}}*(1-{c}{{payout}})", None),
    ]
    idx = _projection(ws, rows, {"bv_end": "=in_book_equity0", "df": 1})
    ws.cell(row=idx["bv_end"], column=2).number_format = FMT["money"]
    r = idx["bv_end"] + 2
    ws.cell(row=r, column=1, value="Terminal value of excess returns").font = BOLD
    ws.cell(row=r, column=2, value=f"=M{idx['excess']}/(M{idx['ke']}-calc_g)").number_format = FMT["money"]
    ws.cell(row=r + 1, column=1, value="PV of terminal value").font = BOLD
    ws.cell(row=r + 1, column=2, value=f"=B{r}*L{idx['df']}").number_format = FMT["money"]
    ws.cell(row=r + 2, column=1, value="Sum of PV of excess returns").font = BOLD
    ws.cell(row=r + 2, column=2, value=f"=SUM(C{idx['pv']}:L{idx['pv']})").number_format = FMT["money"]
    _name(wb, "calc_pv_tv", f"Valuation!$B${r + 1}")
    _name(wb, "calc_pv_cf", f"Valuation!$B${r + 2}")
    return _output_sheet(wb, [
        ("Current book value of equity", "=in_book_equity0", "money"),
        ("PV of excess returns, years 1-10", "=calc_pv_cf", "money"),
        ("PV of terminal excess returns", "=calc_pv_tv", "money"),
        ("Value of equity", "=B5+B6+B7", "money"),
        ("Shares outstanding", "=in_shares", "shares"),
        ("Estimated value per share", "=B8/B9", "ps"),
    ])


def _output_sheet(wb, lines: list[tuple[str, str, str]]) -> dict[str, str]:
    ws = wb.create_sheet("Valuation output")
    ws["A1"], ws["A1"].font = "Valuation output", TITLE
    _hdr(ws, 4, ["Value bridge", "Value"])
    r = 5
    for label, formula, fmt in lines:
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=formula).number_format = FMT[fmt]
        r += 1
    last = r - 1
    for c in (ws.cell(row=last, column=1), ws.cell(row=last, column=2)):
        c.font, c.fill = BOLD, KEY_FILL
    _name(wb, "out_value_per_share", f"'Valuation output'!$B${last}")
    ws.cell(row=r + 1, column=1, value="Current price")
    ws.cell(row=r + 1, column=2, value="=in_price").number_format = FMT["ps"]
    ws.cell(row=r + 2, column=1, value="Price as % of value")
    ws.cell(row=r + 2, column=2, value="=in_price/out_value_per_share").number_format = FMT["pct"]
    ws.cell(row=r + 3, column=1, value="Upside / (downside)").font = BOLD
    ws.cell(row=r + 3, column=2, value="=out_value_per_share/in_price-1").number_format = FMT["pct"]
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 18
    return {"value_per_share": f"'Valuation output'!B{last}"}


# ------------------------------------------------------------------------------ static sheets
def _cover(wb, ctx):
    ws = wb.active
    ws.title = "Cover"
    c = ctx["company"]
    ws["A1"], ws["A1"].font = f"{c['name']} ({c['ticker']})", Font(bold=True, size=18)
    rows = [
        ("Valuation date", dt.date.today().isoformat()),
        ("Method", ctx["method_title"]),
        ("Estimated value per share", "=out_value_per_share"),
        ("Current price", "=in_price"),
        ("Upside / (downside)", "=out_value_per_share/in_price-1"),
        ("Currency", c.get("currency", "USD")),
        ("Thesis", ctx["thesis"]),
    ]
    for i, (k, v) in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=k).font = BOLD
        cell = ws.cell(row=i, column=2, value=v)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws["B5"].number_format = ws["B6"].number_format = FMT["ps"]
    ws["B7"].number_format = FMT["pct"]
    ws["A12"] = ("AI-generated starting point, not investment advice. Review every source and assumption "
                 "before relying on it. Blue cells on the Inputs sheet are editable.")
    ws["A12"].font = Font(italic=True, color="888888")
    if c.get("demo"):
        ws["A13"] = "DEMO DATA: this company and its numbers are fictional."
        ws["A13"].font = Font(bold=True, color="C00000")
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 100


def _story_sheet(wb, ctx, cellmap):
    ws = wb.create_sheet("Stories to Numbers", 1)
    ws["A1"], ws["A1"].font = "Stories to numbers", TITLE
    ws["A2"] = ctx["thesis"]
    ws["A2"].alignment = Alignment(wrap_text=True)
    ws.merge_cells("A2:E2")
    ws.row_dimensions[2].height = 75
    _hdr(ws, 4, ["Story element", "Driver", "Value", "Cell", "Why"])
    r = 5
    for d in METHODS[ctx["method"]].DRIVERS:
        ws.cell(row=r, column=1, value=d.story)
        ws.cell(row=r, column=2, value=d.label)
        v = ws.cell(row=r, column=3, value=f"=in_{d.key}")
        v.number_format = FMT[d.unit]
        ws.cell(row=r, column=4, value=cellmap[d.key])
        ws.cell(row=r, column=5, value=ctx["assumptions"][d.key]["rationale"]).alignment = Alignment(wrap_text=True, vertical="top")
        r += 1
    for col, w in zip("ABCDE", (40, 36, 12, 14, 90)):
        ws.column_dimensions[col].width = w


def _coc_sheet(wb, coc: dict):
    ws = wb.create_sheet("Cost of capital")
    ws["A1"], ws["A1"].font = "Cost of capital (computed starting point)", TITLE
    ws["A2"] = "The cost of capital used in the valuation is the driver on the Inputs sheet; this sheet shows how the starting point was built."
    rows = [
        ("Risk-free rate", coc["riskfree"], "pct"), ("Equity risk premium", coc["erp"], "pct"),
        ("Levered beta", coc["beta"], "num"), ("Country risk premium", coc["country_risk_premium"], "pct"),
        ("Cost of equity", "=B4+B6*B5+B7", "pct"),
        ("Interest coverage (EBIT / interest)", coc["interest_coverage"] if coc["interest_coverage"] is not None else "n/a", "num"),
        ("Synthetic rating", coc["rating"], None), ("Default spread", coc["default_spread"], "pct"),
        ("Pre-tax cost of debt", "=B4+B11", "pct"), ("Marginal tax rate", coc["marginal_tax_rate"], "pct"),
        ("After-tax cost of debt", "=B12*(1-B13)", "pct"),
        ("Equity weight (market)", coc["equity_weight"], "pct"), ("Debt weight (market)", "=1-B15", "pct"),
        ("Cost of capital", "=B8*B15+B14*B16", "pct"),
        ("Mature cost of capital (beta → 1)", "=(B4+B5+B7)*B15+B14*B16", "pct"),
    ]
    for i, (label, val, fmt) in enumerate(rows, start=4):
        ws.cell(row=i, column=1, value=label)
        c = ws.cell(row=i, column=2, value=val)
        if fmt:
            c.number_format = FMT[fmt]
        if not (isinstance(val, str) and val.startswith("=")):
            c.font = BLUE
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 14


def _historical_sheet(wb, metrics: list[dict]):
    ws = wb.create_sheet("Historical")
    ws["A1"], ws["A1"].font = "Historical financials (money in millions)", TITLE
    cols = [("revenue", "Revenue", "money"), ("revenue_growth", "Revenue growth", "pct"), ("ebit", "EBIT", "money"),
            ("operating_margin", "Operating margin", "pct"), ("effective_tax_rate", "Effective tax rate", "pct"),
            ("net_income", "Net income", "money"), ("invested_capital", "Invested capital", "money"),
            ("sales_to_capital", "Sales / capital", "x"), ("roic", "ROIC", "pct"), ("roe", "ROE", "pct"),
            ("payout_ratio", "Dividend payout", "pct"), ("debt_incl_leases", "Debt incl. leases", "money"),
            ("cash", "Cash", "money"), ("equity", "Book equity", "money")]
    _hdr(ws, 3, ["Fiscal year"] + [m["fiscal_year"] for m in metrics])
    for i, (key, label, fmt) in enumerate(cols, start=4):
        ws.cell(row=i, column=1, value=label)
        for j, m in enumerate(metrics, start=2):
            c = ws.cell(row=i, column=j, value=m.get(key))
            c.number_format = FMT[fmt]
    ws.column_dimensions["A"].width = 24
    for j in range(2, len(metrics) + 2):
        ws.column_dimensions[get_column_letter(j)].width = 13


def _sensitivity_sheet(wb, sens: dict):
    ws = wb.create_sheet("Sensitivity")
    ws["A1"], ws["A1"].font = "Sensitivity — one driver at a time (values per share)", TITLE
    ws["A2"] = f"Base value per share: {sens['base_value']:,.2f}. Static snapshot computed at build time."
    _hdr(ws, 4, ["Driver", "Low input", "High input", "Value at low", "Value at high", "Swing"])
    for i, d in enumerate(sens["drivers"], start=5):
        fmt = FMT[d["unit"]]
        ws.cell(row=i, column=1, value=d["label"])
        ws.cell(row=i, column=2, value=d["low_input"]).number_format = fmt
        ws.cell(row=i, column=3, value=d["high_input"]).number_format = fmt
        ws.cell(row=i, column=4, value=d["low_value"]).number_format = FMT["ps"]
        ws.cell(row=i, column=5, value=d["high_value"]).number_format = FMT["ps"]
        ws.cell(row=i, column=6, value=d["range"]).number_format = FMT["ps"]
    n = len(sens["drivers"])
    chart = BarChart()
    chart.type = "bar"
    chart.title = "Value per share: low vs high input"
    chart.y_axis.title = "Value per share"
    data = Reference(ws, min_col=4, max_col=5, min_row=4, max_row=4 + n)
    cats = Reference(ws, min_col=1, min_row=5, max_row=4 + n)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.height, chart.width = 10, 22
    ws.add_chart(chart, f"H4")
    r = 6 + n
    ws.cell(row=r, column=1, value="Scenarios").font = BOLD
    for j, name in enumerate(("bear", "base", "bull")):
        ws.cell(row=r + 1 + j, column=1, value=name.title())
        ws.cell(row=r + 1 + j, column=2, value=sens["scenarios"][name]["value_per_share"]).number_format = FMT["ps"]
    ws.column_dimensions["A"].width = 40
    for col in "BCDEF":
        ws.column_dimensions[col].width = 14


def _probabilistic_sheet(wb, prob: dict):
    ws = wb.create_sheet("Probabilistic")
    ws["A1"], ws["A1"].font = "Break-evens, plausible scenarios and simulation", TITLE
    ws["A2"] = "Static snapshot from the base case at build time. Use Data > What-If > Goal Seek on the output cell to re-solve break-evens."
    r = 4
    _hdr(ws, r, ["Key driver", "Base case", "Break-even (value = price)"])
    for b in prob["break_even"]:
        r += 1
        ws.cell(row=r, column=1, value=b["label"])
        ws.cell(row=r, column=2, value=b["base"]).number_format = FMT[b["unit"]]
        c = ws.cell(row=r, column=3, value=b["break_even"] if b["break_even"] is not None else "not reachable")
        c.number_format = FMT[b["unit"]]
    r += 2
    _hdr(ws, r, ["Scenario", "Probability", "Value per share", "Story"])
    first = r + 1
    for sc in prob["scenarios"]["scenarios"]:
        r += 1
        ws.cell(row=r, column=1, value=sc["name"])
        ws.cell(row=r, column=2, value=sc["probability"]).number_format = FMT["pct"]
        ws.cell(row=r, column=3, value=sc["value_per_share"]).number_format = FMT["ps"]
        ws.cell(row=r, column=4, value=sc["narrative"]).alignment = Alignment(wrap_text=True)
    r += 1
    ws.cell(row=r, column=1, value="Probability-weighted value").font = BOLD
    ws.cell(row=r, column=3, value=f"=SUMPRODUCT(B{first}:B{r - 1},C{first}:C{r - 1})").number_format = FMT["ps"]
    sim = prob["simulation"]
    r += 2
    _hdr(ws, r, ["Simulation", "Value"])
    pc = sim["percentiles"]
    rows = [(f"P{k}", pc[k] if k in pc else pc[str(k)], "ps") for k in (5, 10, 25, 50, 75, 90, 95)]
    rows += [("Mean", sim["mean"], "ps"), ("Trials", sim["n"], "num")]
    if sim.get("prob_undervalued") is not None:
        rows.append(("Probability undervalued", sim["prob_undervalued"], "pct"))
    if sim.get("margin_of_safety") is not None:
        rows += [("Margin of safety (1 − P25/median)", sim["margin_of_safety"], "pct"), ("Buy below", sim["buy_below"], "ps")]
    for label, v, fmt in rows:
        r += 1
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=v).number_format = FMT[fmt]
    r += 2
    _hdr(ws, r, ["Simulated driver", "Mean", "Std dev"])
    for d in sim["drivers"]:
        r += 1
        ws.cell(row=r, column=1, value=d["label"])
        ws.cell(row=r, column=2, value=d["mean"]).number_format = FMT[d["unit"]]
        ws.cell(row=r, column=3, value=d["sd"]).number_format = FMT[d["unit"]]
    r += 2
    _hdr(ws, r, ["Consistency test", "Result", "Detail"])
    for c in prob["checks"]:
        r += 1
        ws.cell(row=r, column=1, value=c["test"])
        ws.cell(row=r, column=2, value="Pass" if c["pass"] else "Fail").font = Font(bold=True, color="2E7D5B" if c["pass"] else "B4433A")
        ws.cell(row=r, column=3, value=c["detail"])
    # histogram data + chart
    h0 = 4
    ws.cell(row=h0, column=7, value="Bin from").font = BOLD
    ws.cell(row=h0, column=8, value="Trials").font = BOLD
    for i, cnt in enumerate(sim["histogram"]["counts"], start=1):
        ws.cell(row=h0 + i, column=7, value=round(sim["histogram"]["edges"][i - 1], 2))
        ws.cell(row=h0 + i, column=8, value=cnt)
    n = len(sim["histogram"]["counts"])
    ch = BarChart()
    ch.title = "Simulated value per share"
    ch.add_data(Reference(ws, min_col=8, min_row=h0, max_row=h0 + n), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=7, min_row=h0 + 1, max_row=h0 + n))
    ch.gapWidth, ch.height, ch.width, ch.legend = 10, 9, 18, None
    ws.add_chart(ch, "J4")
    ws.column_dimensions["A"].width = 52
    for col in "BC":
        ws.column_dimensions[col].width = 16
    ws.column_dimensions["D"].width = 70


def _diagnostics_sheet(wb, ctx, idx: dict[str, int]):
    """Live sanity checks on the forecast (Damodaran's diagnostics): every cell is a formula."""
    ws = wb.create_sheet("Diagnostics")
    ws["A1"], ws["A1"].font = "Diagnostics — does the forecast make sense?", TITLE
    m = ctx["metrics"]
    last = m[-1]
    V = lambda r, col: f"Valuation!{col}{idx[r]}"  # noqa: E731
    rows: list[tuple] = [
        ("Step 1: Revenue growth", None, None, None, None),
        ("", "Most recent year", "Next year", "Years 2-5", "Years 6-10 (avg)"),
        ("Revenue growth", last.get("revenue_growth"), "=" + V("g", "C"), "=" + V("g", "D"),
         f"=AVERAGE(Valuation!H{idx['g']}:L{idx['g']})", "pct"),
        ("Step 2: Dollar revenues", None, None, None, None),
        ("", "Base year", "Next year", "Year 5", "Year 10"),
        ("Revenues (m)", "=in_revenue0", "=" + V("rev", "C"), "=" + V("rev", "G"), "=" + V("rev", "L"), "money"),
        ("Revenue multiple of today", None, "=C{Revenues (m)}/B{Revenues (m)}", "=D{Revenues (m)}/B{Revenues (m)}",
         "=E{Revenues (m)}/B{Revenues (m)}", "x"),
        ("Step 3: Margins", None, None, None, None),
        ("", "Base year (adjusted)", "Next year", "Year 5", "Year 10"),
        ("Operating margin", "=in_ebit0/in_revenue0", "=" + V("margin", "C"), "=" + V("margin", "G"), "=" + V("margin", "L"), "pct"),
        ("Gross margin (ceiling)", last.get("gross_margin"), None, None, None, "pct"),
        ("Step 4: Reinvestment", None, None, None, None),
        ("", "Most recent year", "Years 1-5", "Years 6-10", ""),
        ("Sales to capital", last.get("sales_to_capital"), "=in_sales_to_capital", "=in_sales_to_capital_late", None, "x"),
        ("PV of after-tax operating income, yrs 1-10", f"=SUMPRODUCT(Valuation!C{idx['nopat']}:L{idx['nopat']},Valuation!C{idx['df']}:L{idx['df']})", None, None, None, "money"),
        ("Value effect of reinvestment, yrs 1-10", "=B{PV of FCFF, yrs 1-10}-B{PV of after-tax operating income, yrs 1-10}", None, None, None, "money"),
        ("PV of FCFF, yrs 1-10", "=calc_pv_cf", None, None, None, "money"),
        ("Step 5: Return on capital", None, None, None, None),
        ("", "Most recent year", "Marginal (yrs 1-10)", "Year 10", "Stable"),
        ("Return on capital", last.get("roic"),
         f"=(Valuation!L{idx['nopat']}-in_ebit0*(1-in_effective_tax_rate))/SUM(Valuation!C{idx['reinv']}:L{idx['reinv']})",
         f"=Valuation!L{idx['nopat']}/(in_invested_capital0+SUM(Valuation!C{idx['reinv']}:K{idx['reinv']}))", "=in_terminal_roc", "pct"),
        ("Step 6: Risk", None, None, None, None),
        ("", "Years 1-5", "Compounded (10 yrs)", "Mature", "Failure"),
        ("Cost of capital", "=in_wacc_initial", f"=(1/Valuation!L{idx['df']})^(1/10)-1", "=in_wacc_terminal", "=in_prob_failure", "pct"),
        ("Step 7: Price versus value", None, None, None, None),
        ("Price as % of value", "=in_price/out_value_per_share", None, None, None, "pct"),
        ("Verdict", '=IF(out_value_per_share<=0,"Value is negative: check margins and reinvestment",'
                    'IF(in_price/out_value_per_share>1.5,"Price well above value: is the growth or margin story too timid?",'
                    'IF(in_price/out_value_per_share<0.67,"Price well below value: is the story too rosy?","Price within ±50% of value")))', None, None, None, None),
    ]
    where = {row[0]: i for i, row in enumerate(rows, start=3) if row[0]}

    def resolve(v):
        if isinstance(v, str) and "{" in v and not v.startswith('=IF('):
            for lab, rr in where.items():
                v = v.replace("{" + lab + "}", str(rr))
        return v

    for i, row in enumerate(rows, start=3):
        label, *vals = row
        fmt = vals[4] if len(vals) > 4 else None
        vals = [resolve(v) for v in vals[:4]]
        c = ws.cell(row=i, column=1, value=label)
        if all(v is None for v in vals):
            c.font = BOLD
        elif label == "":
            for j, v in enumerate(vals, start=2):
                h = ws.cell(row=i, column=j, value=v)
                h.font, h.fill = HEAD_FONT, HEAD_FILL
            continue
        for j, v in enumerate(vals, start=2):
            if v is None:
                continue
            cell = ws.cell(row=i, column=j, value=v)
            if fmt:
                cell.number_format = FMT[fmt]
    ws.column_dimensions["A"].width = 44
    for col in "BCDE":
        ws.column_dimensions[col].width = 20


def _reverse_sheet(wb, prob: dict):
    rv = prob.get("reverse_dcf") or {}
    if not rv.get("rows"):
        return
    ws = wb.create_sheet("Reverse DCF")
    ws["A1"], ws["A1"].font = "What the market believes", TITLE
    ws["A2"] = ("Key drivers moved together until value = price (solved exactly). Open model_market.xlsx for the "
                "full market-implied model.")
    _hdr(ws, 4, ["Driver", "My estimates", "Market-implied"])
    r = 4
    for x in rv["rows"]:
        r += 1
        ws.cell(row=r, column=1, value=x["label"]).font = BOLD if x["diverges"] else Font()
        ws.cell(row=r, column=2, value=x["mine"]).number_format = FMT[x["unit"]]
        ws.cell(row=r, column=3, value=x["market"]).number_format = FMT[x["unit"]]
    r += 1
    ws.cell(row=r, column=1, value="Value per share").font = BOLD
    ws.cell(row=r, column=2, value=rv["base_value"]).number_format = FMT["ps"]
    ws.cell(row=r, column=3, value=rv.get("implied_value")).number_format = FMT["ps"]
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = ws.column_dimensions["C"].width = 16


def _methodology_sheet(wb, ctx, cellmap, outmap):
    ws = wb.create_sheet("Methodology")
    ws["A1"], ws["A1"].font = "Methodology", TITLE
    ws["A2"] = ctx["method_reason"]
    ws["A2"].alignment = Alignment(wrap_text=True)
    ws.merge_cells("A2:D2")
    ws.row_dimensions[2].height = 45
    _hdr(ws, 4, ["Value driver", "Editable cell", "What it represents", "Sensitivity bump (±)"])
    r = 5
    for d in METHODS[ctx["method"]].DRIVERS:
        ws.cell(row=r, column=1, value=d.label)
        ws.cell(row=r, column=2, value=cellmap[d.key])
        ws.cell(row=r, column=3, value=d.story)
        ws.cell(row=r, column=4, value=d.bump).number_format = FMT[d.unit]
        r += 1
    r += 1
    ws.cell(row=r, column=1, value="Output cell").font = BOLD
    ws.cell(row=r, column=2, value=outmap["value_per_share"])
    for col, w in zip("ABCD", (40, 18, 60, 20)):
        ws.column_dimensions[col].width = w


def _sources_sheet(wb, sources: list[dict]):
    ws = wb.create_sheet("Sources")
    ws["A1"], ws["A1"].font = "Sources", TITLE
    for i, s in enumerate(sources, start=3):
        ws.cell(row=i, column=1, value=s.get("label"))
        if s.get("url"):
            c = ws.cell(row=i, column=2, value=s["url"])
            c.hyperlink = s["url"]
            c.font = Font(color="1F4FD1", underline="single")
    ws.column_dimensions["A"].width = 70
    ws.column_dimensions["B"].width = 90


def build_workbook(path: Path, ctx: dict[str, Any], assumptions: dict[str, float] | None = None) -> dict[str, Any]:
    """Write the workbook. `assumptions` overrides the base case (used for scenario workbooks).

    Returns {"cells": driver -> cell, "output": output cell} for the Methodology tab in the UI.
    """
    method = ctx["method"]
    values = dict(ctx["inputs"])
    if assumptions:
        values.update(assumptions)
    rationale = {k: v["rationale"] for k, v in ctx["assumptions"].items()}
    wb = Workbook()
    _cover(wb, ctx)
    cellmap = _inputs_sheet(wb, method, values, rationale, ctx["company"].get("currency", "USD"))
    outmap = {"fcff": _fcff_sheet, "ddm": _ddm_sheet, "excess_return": _excess_sheet}[method](wb)
    _story_sheet(wb, ctx, cellmap)
    _coc_sheet(wb, ctx["cost_of_capital"])
    _historical_sheet(wb, ctx["metrics"])
    _sensitivity_sheet(wb, ctx["sensitivity"])
    if ctx.get("probabilistic"):
        _probabilistic_sheet(wb, ctx["probabilistic"])
        _reverse_sheet(wb, ctx["probabilistic"])
    if method == "fcff":
        _diagnostics_sheet(wb, ctx, outmap["idx"])
    _methodology_sheet(wb, ctx, cellmap, outmap)
    _sources_sheet(wb, ctx["sources"])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return {"cells": cellmap, "output": outmap["value_per_share"]}
