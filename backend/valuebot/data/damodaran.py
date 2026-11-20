"""Damodaran's public datasets (pages.stern.nyu.edu/~adamodar/), fetched and cached.

* Industry unlevered betas (betas.xls)    -> bottom-up beta when the user names no segments
* Country risk premiums (ctryprem.xlsx)   -> ERP weighted by where revenues come from

Both are optional: any failure returns None and the pipeline falls back to the regression
beta / mature ERP, recording the fallback in the sources list. Parsing is header-driven so a
column move between annual updates doesn't break it.
"""
from __future__ import annotations

import difflib
import io
import json
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import settings

BASE = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/"
BETAS_URL = BASE + "betas.xls"
CTRY_URL = BASE + "ctryprem.xlsx"
CACHE_DAYS = 30


def _cache_path(name: str) -> Path:
    d = settings.data_dir / "_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def _download(url: str, name: str) -> bytes | None:
    f = _cache_path(name)
    if f.exists() and time.time() - f.stat().st_mtime < CACHE_DAYS * 86400:
        return f.read_bytes()
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True)
        r.raise_for_status()
    except Exception:  # noqa: BLE001
        return f.read_bytes() if f.exists() else None
    f.write_bytes(r.content)
    return r.content


def _find_table(frames: dict, must: list[str]):
    """Locate the header row containing all `must` substrings in any sheet; return a clean DataFrame."""
    import pandas as pd

    for _, raw in frames.items():
        for i in range(min(len(raw), 30)):
            row = [str(x).strip().lower() for x in raw.iloc[i].tolist()]
            if all(any(m in c for c in row) for m in must):
                df = raw.iloc[i + 1:].copy()
                df.columns = [str(x).strip() for x in raw.iloc[i].tolist()]
                return df.dropna(how="all")
    return None


def parse_industry_betas(frames: dict) -> dict[str, float]:
    df = _find_table(frames, ["industry name", "unlevered beta"])
    if df is None:
        return {}
    name_col = next(c for c in df.columns if "industry name" in c.lower())
    beta_cols = [c for c in df.columns if "unlevered beta" in c.lower()]
    # prefer "unlevered beta corrected for cash"
    beta_col = next((c for c in beta_cols if "cash" in c.lower()), beta_cols[0])
    out = {}
    for _, r in df.iterrows():
        try:
            out[str(r[name_col]).strip()] = float(r[beta_col])
        except (TypeError, ValueError):
            continue
    return out


def parse_country_premiums(frames: dict) -> dict[str, float]:
    df = _find_table(frames, ["country", "country risk premium"])
    if df is None:
        return {}
    name_col = next(c for c in df.columns if c.lower().startswith("country"))
    crp_col = next(c for c in df.columns if "country risk premium" in c.lower())
    out = {}
    for _, r in df.iterrows():
        try:
            out[str(r[name_col]).strip()] = float(r[crp_col])
        except (TypeError, ValueError):
            continue
    return out


def _frames(content: bytes) -> dict | None:
    try:
        import pandas as pd

        return pd.read_excel(io.BytesIO(content), sheet_name=None, header=None)
    except Exception:  # noqa: BLE001  (missing xlrd/openpyxl or a format change)
        return None


def _load(url: str, name: str, parser) -> dict[str, float] | None:
    cache = _cache_path(name + ".json")
    if cache.exists() and time.time() - cache.stat().st_mtime < CACHE_DAYS * 86400:
        return json.loads(cache.read_text())
    if settings.offline:
        return None
    content = _download(url, name)
    frames = _frames(content) if content else None
    data = parser(frames) if frames else {}
    if data:
        cache.write_text(json.dumps(data))
    return data or None


def industry_betas() -> dict[str, float] | None:
    return _load(BETAS_URL, "betas.xls", parse_industry_betas)


def country_premiums() -> dict[str, float] | None:
    return _load(CTRY_URL, "ctryprem.xlsx", parse_country_premiums)


# Yahoo Finance industry names → Damodaran industry names. Fuzzy matching alone mis-files common
# industries (e.g. "Software - Infrastructure" landed on "Software (Internet)", beta 1.59, for Microsoft).
YAHOO_TO_DAMODARAN = {
    "software - infrastructure": "Software (System & Application)",
    "software - application": "Software (System & Application)",
    "internet content & information": "Software (Internet)",
    "electronic gaming & multimedia": "Software (Entertainment)",
    "semiconductors": "Semiconductor",
    "semiconductor equipment & materials": "Semiconductor Equip",
    "consumer electronics": "Electronics (Consumer & Office)",
    "computer hardware": "Computers/Peripherals",
    "communication equipment": "Telecom. Equipment",
    "information technology services": "Computer Services",
    "internet retail": "Retail (Online)",
    "specialty retail": "Retail (Special Lines)",
    "discount stores": "Retail (General)",
    "home improvement retail": "Retail (Building Supply)",
    "grocery stores": "Retail (Grocery and Food)",
    "auto manufacturers": "Auto & Truck",
    "auto parts": "Auto Parts",
    "banks - diversified": "Bank (Money Center)",
    "banks - regional": "Banks (Regional)",
    "capital markets": "Brokerage & Investment Banking",
    "asset management": "Investments & Asset Management",
    "insurance - life": "Insurance (Life)",
    "insurance - property & casualty": "Insurance (Prop/Cas.)",
    "insurance - diversified": "Insurance (General)",
    "credit services": "Financial Svcs. (Non-bank & Insurance)",
    "drug manufacturers - general": "Drugs (Pharmaceutical)",
    "drug manufacturers - specialty & generic": "Drugs (Pharmaceutical)",
    "biotechnology": "Drugs (Biotechnology)",
    "medical devices": "Healthcare Products",
    "medical instruments & supplies": "Healthcare Products",
    "diagnostics & research": "Healthcare Products",
    "healthcare plans": "Healthcare Support Services",
    "oil & gas integrated": "Oil/Gas (Integrated)",
    "oil & gas e&p": "Oil/Gas (Production and Exploration)",
    "oil & gas midstream": "Oil/Gas Distribution",
    "utilities - regulated electric": "Utility (General)",
    "utilities - diversified": "Utility (General)",
    "utilities - renewable": "Power",
    "telecom services": "Telecom. Services",
    "entertainment": "Entertainment",
    "beverages - non-alcoholic": "Beverage (Soft)",
    "beverages - brewers": "Beverage (Alcoholic)",
    "beverages - wineries & distilleries": "Beverage (Alcoholic)",
    "household & personal products": "Household Products",
    "packaged foods": "Food Processing",
    "tobacco": "Tobacco",
    "restaurants": "Restaurant/Dining",
    "aerospace & defense": "Aerospace/Defense",
    "railroads": "Transportation (Railroads)",
    "airlines": "Air Transport",
    "integrated freight & logistics": "Transportation",
    "specialty industrial machinery": "Machinery",
    "farm & heavy construction machinery": "Machinery",
    "conglomerates": "Diversified",
    "steel": "Steel",
    "other industrial metals & mining": "Metals & Mining",
    "gold": "Precious Metals",
    "chemicals": "Chemical (Basic)",
    "specialty chemicals": "Chemical (Specialty)",
    "reit - specialty": "R.E.I.T.",
    "reit - industrial": "R.E.I.T.",
    "reit - retail": "R.E.I.T.",
    "residential construction": "Homebuilding",
    "travel services": "Hotel/Gaming",
    "lodging": "Hotel/Gaming",
    "resorts & casinos": "Hotel/Gaming",
    "advertising agencies": "Advertising",
    "apparel retail": "Retail (Distributors)",
    "footwear & accessories": "Shoe",
}


def best_match(name: str | None, table: dict[str, Any] | None, cutoff: float = 0.55) -> str | None:
    if not name or not table:
        return None
    mapped = YAHOO_TO_DAMODARAN.get(name.strip().lower())
    if mapped and mapped in table:
        return mapped
    keys = list(table)
    simple = name.replace("—", " ").replace("-", " ")
    hit = difflib.get_close_matches(simple, keys, n=1, cutoff=cutoff)
    if hit:
        return hit[0]
    low = simple.lower()
    for k in keys:
        if k.lower() in low or low in k.lower():
            return k
    return None
