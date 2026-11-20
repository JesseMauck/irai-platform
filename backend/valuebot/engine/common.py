"""Shared types and helpers for the valuation engines.

Every engine follows the same 10-year, three-phase shape Damodaran uses in his
spreadsheets:

  * year 1            – the "next year" assumptions
  * years 2-5         – high-growth phase
  * years 6-10        – linear convergence to stable-growth values
  * terminal (yr 11)  – perpetuity at the stable growth rate

The Excel builder re-implements exactly these formulas so the workbook and the
Python numbers always agree (tests/test_excel_parity.py checks this).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

YEARS = 10
HIGH_GROWTH_END = 5


@dataclass(frozen=True)
class Driver:
    """A value driver the user (or the LLM) sets, and the sensitivity engine flexes."""

    key: str
    label: str
    unit: str  # "pct" | "x" | "years" | "num"
    bump: float  # absolute low/high bump used for the tornado chart
    story: str  # what this driver means in narrative terms
    lo: float | None = None  # hard bounds (clamped during sensitivity / LLM sanitising)
    hi: float | None = None
    higher_is_better: bool = True

    def clamp(self, v: float) -> float:
        if self.lo is not None:
            v = max(self.lo, v)
        if self.hi is not None:
            v = min(self.hi, v)
        return v


def converge(t: int, start: float, end: float, begin_year: int = HIGH_GROWTH_END, end_year: int = YEARS) -> float:
    """Value at year t of a variable that is `start` through `begin_year`
    and moves linearly to `end` by `end_year`."""
    if t <= begin_year:
        return start
    return start + (end - start) * (t - begin_year) / (end_year - begin_year)


@dataclass
class ValuationResult:
    method: str
    value_per_share: float
    price: float | None
    equity_value: float
    table: list[dict[str, Any]]  # per-year rows
    terminal: dict[str, float]
    bridge: list[tuple[str, float]]  # value bridge from operating assets to per-share value
    warnings: list[str] = field(default_factory=list)

    @property
    def upside(self) -> float | None:
        if not self.price:
            return None
        return self.value_per_share / self.price - 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "value_per_share": self.value_per_share,
            "price": self.price,
            "upside": self.upside,
            "equity_value": self.equity_value,
            "table": self.table,
            "terminal": self.terminal,
            "bridge": [{"label": k, "value": v} for k, v in self.bridge],
            "warnings": self.warnings,
        }
