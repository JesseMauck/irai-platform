"""Ask IRAI navigation: turn a member's question into deep links that open the right feature, pre-filled.

Deterministic so links are always valid: tickers and company names are extracted, the intent is matched against an
app map, and each action is a whitelisted in-app path with query parameters (never an external URL). When the
question is an explicit request to go somewhere ("compare ORCL to 3 other stocks", "open the heatmap", "run a DCF on
NVDA"), the primary action is marked `auto` and the chat opens it immediately.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

SEED = Path(__file__).parent / "seed_data"
NAMES = {
    "apple": "AAPL", "microsoft": "MSFT", "nvidia": "NVDA", "alphabet": "GOOGL", "google": "GOOGL", "amazon": "AMZN", "meta": "META",
    "facebook": "META", "tesla": "TSLA", "netflix": "NFLX", "oracle": "ORCL", "salesforce": "CRM", "adobe": "ADBE", "intel": "INTC",
    "amd": "AMD", "broadcom": "AVGO", "qualcomm": "QCOM", "ibm": "IBM", "sap": "SAP", "palantir": "PLTR", "snowflake": "SNOW",
    "servicenow": "NOW", "cisco": "CSCO", "micron": "MU", "jpmorgan": "JPM", "jp morgan": "JPM", "goldman": "GS", "goldman sachs": "GS",
    "bank of america": "BAC", "wells fargo": "WFC", "berkshire": "BRK-B", "visa": "V", "mastercard": "MA", "paypal": "PYPL",
    "exxon": "XOM", "chevron": "CVX", "coca-cola": "KO", "coke": "KO", "pepsi": "PEP", "pepsico": "PEP", "walmart": "WMT", "costco": "COST",
    "home depot": "HD", "nike": "NKE", "disney": "DIS", "mcdonald's": "MCD", "mcdonalds": "MCD", "starbucks": "SBUX",
    "pfizer": "PFE", "eli lilly": "LLY", "lilly": "LLY", "novo nordisk": "NVO", "merck": "MRK", "johnson & johnson": "JNJ", "unitedhealth": "UNH",
    "boeing": "BA", "lockheed": "LMT", "caterpillar": "CAT", "verizon": "VZ", "at&t": "T", "uber": "UBER", "airbnb": "ABNB", "shopify": "SHOP",
    "alibaba": "BABA", "tsmc": "TSM", "taiwan semiconductor": "TSM", "toyota": "TM", "sony": "SONY", "asml": "ASML", 
    "coinbase": "COIN", "robinhood": "HOOD", "bitcoin": "BTC-USD", "ethereum": "ETH-USD", "solana": "SOL-USD", "gold": "GLD",
    "s&p 500": "SPY", "s&p": "SPY", "nasdaq": "QQQ", "nasdaq 100": "QQQ", "russell 2000": "IWM", "small caps": "IWM", "treasuries": "TLT",
    "dow": "DIA", "oil": "USO", "dollar": "UUP", "vix": "^VIX",
}
STOP = {"A", "I", "AI", "ETF", "ETFS", "DCF", "RSI", "MACD", "USD", "CEO", "CFO", "IPO", "EPS", "PE", "P", "E", "ROE", "ROI", "ROIC", "EV",
        "EBITDA", "FCF", "TTM", "YOY", "QOQ", "SMA", "EMA", "ATR", "ADX", "VAR", "CVAR", "OK", "US", "USA", "UK", "EU", "GDP", "CPI", "FED",
        "FOMC", "SEC", "IRS", "ADR", "ADRS", "NAV", "IV", "HMM", "PDF", "CSV", "API", "FAQ", "IRAI", "AND", "OR", "THE", "TO", "VS", "MY",
        "ME", "IS", "IT", "IN", "ON", "OF", "AT", "BY", "AN", "BE", "DO", "IF", "SO", "UP", "NO", "YES", "Q1", "Q2", "Q3", "Q4", "FY", "NYSE",
        "LLM", "ESG", "M&A", "CAGR", "YTD", "ATH", "PM", "AM", "ET", "EST", "PT", "BUY", "SELL", "HOLD", "LONG", "SHORT", "NEW", "TOP", "ALL",
        "VS.", "PEG", "PB", "PS", "KPI", "OTC", "IRA", "401K", "DRIP", "DEMO", "LIVE", "PRO", "FREE", "R", "X", "Y", "N"}
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
SECTOR_LEADERS = {"Technology": ["MSFT", "AAPL", "NVDA", "ORCL", "CRM", "ADBE", "SAP", "IBM"], "Communication Services": ["GOOGL", "META", "NFLX", "DIS"],
                  "Financial Services": ["JPM", "BAC", "GS", "MS", "WFC"], "Energy": ["XOM", "CVX", "COP"], "Healthcare": ["LLY", "UNH", "JNJ", "MRK", "PFE"],
                  "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE"], "Consumer Defensive": ["WMT", "COST", "PG", "KO", "PEP"]}
SOFTWARE_PEERS = {"ORCL": ["MSFT", "SAP", "CRM", "IBM", "ADBE", "NOW"]}


THEME_KEYS = [(r"\bai\b|artificial intelligence|semiconductor|chips?", "ai-semiconductors"), (r"glp|obesity|weight loss", "glp1-obesity"),
              (r"energy transition|power demand|clean energy|renewable|nuclear|utilities", "energy-transition"), (r"china", "china-internet"),
              (r"japan", "japan-reform"), (r"bonds?|rates|income|treasur", "rates-and-bonds"), (r"cyber", "cybersecurity"),
              (r"defen[cs]e|aerospace", "defense-aerospace"), (r"crypto|bitcoin|digital asset", "crypto-digital-assets"), (r"european banks|europe", "european-banks")]


def _themes() -> list[dict[str, Any]]:
    try:
        return json.loads((SEED / "themes.json").read_text())
    except Exception:  # noqa: BLE001
        return []


def tickers(text: str) -> list[str]:
    """Tickers in the order mentioned: $TICKER or ALLCAPS tokens that look like symbols, plus well-known company names."""
    found: list[tuple[int, str]] = []
    low = text.lower()
    for name, sym in sorted(NAMES.items(), key=lambda x: -len(x[0])):
        for m in re.finditer(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", low):
            found.append((m.start(), sym))
    for m in re.finditer(r"\$?\b([A-Z]{1,5}(?:[.\-][A-Z]{1,3})?|\^[A-Z]{2,5}|[A-Z]{3,5}-USD|[A-Z]{6}=X|[A-Z]{1,3}=F)\b", text):
        tok = m.group(1)
        if tok in STOP and not m.group(0).startswith("$"):
            continue
        if len(tok) == 1 and not m.group(0).startswith("$"):
            continue
        found.append((m.start(), tok))
    out: list[str] = []
    for _, s in sorted(found):
        if s not in out:
            out.append(s)
    return out[:8]


def peers_for(sym: str, n: int) -> list[str]:
    try:
        from sqlalchemy import select

        from .db import SessionLocal
        from .models import PeerMember

        with SessionLocal() as s:
            m = s.scalar(select(PeerMember).where(PeerMember.symbol == sym))
            if m:
                return [x.symbol for x in m.group.members if x.symbol != sym][:n]
    except Exception:  # noqa: BLE001
        pass
    if sym in SOFTWARE_PEERS:
        return SOFTWARE_PEERS[sym][:n]
    try:
        from .market import service

        sector = (service.info(sym) or {}).get("sector")
        return [x for x in SECTOR_LEADERS.get(sector or "", []) if x != sym][:n]
    except Exception:  # noqa: BLE001
        return []


def _n_others(text: str) -> int | None:
    m = re.search(r"\b(\d|one|two|three|four|five|six|seven)\s+(?:other|more|similar|peer|competitor|rival|comparable)", text.lower())
    if not m:
        m = re.search(r"\b(?:its|to)\s+(\d|one|two|three|four|five|six|seven)\s+(?:closest|top|biggest|main)?\s*(?:peers|competitors|rivals|stocks|companies)", text.lower())
    if not m:
        return None
    v = m.group(1)
    return int(v) if v.isdigit() else WORDNUM[v]


def act(label: str, path: str, params: dict[str, Any] | None = None, hash_: str | None = None, desc: str | None = None) -> dict[str, Any]:
    q = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
    href = path + ("?" + urlencode(q, safe=",") if q else "") + (f"#{hash_}" if hash_ else "")
    return {"label": label, "href": href, **({"desc": desc} if desc else {})}


GO = re.compile(r"\b(take me|go to|open|show me|pull up|bring up|navigate|launch|start|run|load|compare|build|create|set up|make me|backtest|simulate|monte carlo|value|analy[sz]e|upgrade|turn on|switch to|print)\b", re.I)

# (intent, pattern, needs_ticker)
INTENTS: list[tuple[str, str, bool]] = [
    ("compare", r"\bcompare|\bvs\.?\b|\bversus\b|side[- ]by[- ]side|stack up against|how does .* compare", False),
    ("valuebot", r"\bdcf\b|intrinsic value|fair value|valu(e|ation) (of|for)|\bvalue\b.*\b(stock|company|it)\b|what('s| is) .* worth|valuebot|undervalued|overvalued", False),
    ("report", r"\bpdf\b|\bprint|research report|full report|report (on|for)|(write|generate|make|create) (me )?a report", True),
    ("street", r"price target|analyst ratings?|consensus|street (view|estimates)|upgrades?|downgrades?|what do analysts", True),
    ("analyst", r"analyst bot|research note|\banaly[sz]e\b|\banalysis\b|deep dive|what('s| is) (going on|happening) with|tell me about|overview of|thesis", True),
    ("bot", r"\bbot\b|automat|algo ?trad|paper trad|trading bot|webhook|tradingview alert", False),
    ("montecarlo", r"monte carlo|simulat|probability of (hitting|reaching)|range of outcomes", False),
    ("backtest", r"backtest|back-test|strategy lab|test (a|my|the) strategy|moving average cross|golden cross|rsi strategy", False),
    ("options", r"\boptions?\b|implied vol|put/call|expected move|max pain|options chain", False),
    ("earnings", r"earnings|eps|quarterly results|report date", False),
    ("dividends", r"dividend|yield|payout", True),
    ("financials", r"financials|income statement|balance sheet|cash flow|revenue history|statements", True),
    ("technicals", r"technical|rsi\b|macd|support|resistance|moving averages?|trend", True),
    ("news", r"\bnews\b|headlines|what happened", True),
    ("filings", r"filing|10-k|10-q|8-k|form 4|sec ", True),
    ("chart", r"\bchart\b|price history", True),
    ("peers", r"\bpeers?\b|competitors|ratios|multiples", True),
    ("congress", r"congress|senator|representative|pelosi|politician|house members?|lawmaker", False),
    ("smartmoney", r"smart money|13f|hedge funds?|institutional|berkshire hathaway|buffett|ackman|burry|dalio|druckenmiller|what are funds buying|whales?", False),
    ("patterns", r"pattern|regime|lead[- ]lag|market state|order ?book|microstructure|analog", False),
    ("signals", r"signals?\b|breakouts?|unusual (move|activity)|oversold|overbought|what('s| is) moving", False),
    ("heatmap", r"heat ?map|sector performance|what sectors", False),
    ("macro", r"macro|world markets|global markets|yields|currencies|commodit", False),
    ("screener", r"screen(er)?|filter stocks|find stocks|stocks with", False),
    ("adr", r"\badrs?\b|cross-listed|depositary", False),
    ("etf_monitor", r"etf (premium|discount)|nav discount|premium to nav", False),
    ("relative_value", r"relative value|cheap for (its|their) quality|quality-adjusted", False),
    ("pairs", r"pair (trade|idea)s?|pairs", False),
    ("portfolio", r"my portfolio|portfolio|holdings|positions|diversif", False),
    ("themes", r"theme|ai stocks|semiconductor stocks|glp-?1|obesity drugs|energy transition|cybersecurity|defen[cs]e stocks|crypto stocks|european banks|japan|china internet", False),
    ("marketplace", r"marketplace|community strateg|copy a strategy|sell my bot|publish (my )?bot", False),
    ("trade", r"ready-made strateg|strategy templates?|connect (my )?(broker|brokerage)|brokerage account", False),
    ("watchlist", r"watchlist|terminal", False),
    ("alerts", r"\balerts?\b|notify me|price alert", False),
    ("pricing", r"pricing|price of (the )?plans?|upgrade|subscription|how much (does|is)|trial|cancel", False),
    ("customize", r"dark mode|light mode|theme color|accent|customi[sz]e|settings|density|start page", False),
    ("learn", r"what is an? |explain|how does .* work|glossary|definition|learn", False),
    ("community", r"forum|community|discussion|trade ideas|leaderboard", False),
    ("library", r"my (reports|valuations|library)|saved reports|history of my", False),
]


def plan(text: str, page_symbol: str | None = None) -> dict[str, Any]:
    """Return {intents, tickers, actions[], auto, note} for a question."""
    t = text.strip()
    low = t.lower()
    syms = tickers(t)
    sym = syms[0] if syms else page_symbol
    hits = [name for name, pat, needs in INTENTS if re.search(pat, low) and (not needs or sym)]
    # a bare ticker or "ORCL?" means: open the ticker page
    if not hits and syms and len(t) <= 24:
        hits = ["ticker"]
    acts: list[dict[str, Any]] = []
    note = None

    def add(a: dict[str, Any]):
        if a["href"] not in {x["href"] for x in acts}:
            acts.append(a)

    for h in hits:
        if h == "compare":
            group = list(syms) if syms else ([page_symbol] if page_symbol else [])
            n = _n_others(t)
            if group and (n or len(group) == 1):
                extra = peers_for(group[0], n or 3)
                note = f"I added {', '.join(extra)} as {group[0]}'s closest peers." if extra else None
                group += [x for x in extra if x not in group]
            group = group[:8]
            if len(group) >= 2:
                add(act(f"Compare {', '.join(group)}", "/compare", {"symbols": ",".join(group)}, desc="Side-by-side valuation, margins, growth, quant grades, momentum, risk and an AI read-through"))
            else:
                add(act("Open Compare", "/compare", desc="Pick up to eight tickers to compare"))
        elif h == "valuebot":
            add(act(f"Value {sym} with ValueBot" if sym else "Open ValueBot", "/valuebot", {"ticker": sym}, desc="18-stage DCF from SEC filings with an editable Excel model"))
        elif h == "report" and sym:
            add(act(f"Open the {sym} research report", f"/ticker/{quote(sym)}/report", desc="Printable 11-page report with charts and tables"))
        elif h == "analyst" and sym:
            add(act(f"Run the Analyst Bot on {sym}", f"/ticker/{quote(sym)}", hash_="analyst", desc="Same-day sourced research note"))
            add(act(f"Printable {sym} report", f"/ticker/{quote(sym)}/report"))
        elif h == "montecarlo":
            add(act(f"Monte Carlo {', '.join(syms[:6])}" if syms else "Open Monte Carlo", "/lab/montecarlo",
                    {"symbols": ",".join(syms[:6])} if len(syms) > 1 else {"symbol": sym}, desc="Thousands of simulated paths, VaR and target probabilities"))
        elif h == "backtest":
            strat = "sma_cross" if re.search(r"golden cross|moving average|sma", low) else "rsi" if "rsi" in low else "bollinger" if "bollinger" in low else "macd" if "macd" in low else "breakout" if "breakout" in low else None
            add(act(f"Backtest {sym}" if sym else "Open the Strategy Lab", "/lab", {"symbol": sym, "strategy": strat}, desc="Costs included, with an out-of-sample check"))
        elif h == "bot":
            add(act("Build this bot", "/bots/new", {"prompt": t[:300]}, desc="IRAI drafts the strategy and risk controls for you to review; paper trading first"))
            add(act("Ready-made strategies", "/trade"))
        elif h == "street" and sym:
            add(act(f"{sym} Street consensus", f"/ticker/{quote(sym)}", desc="Consensus rating, target range and analyst count on the Summary tab"))
            add(act(f"{sym} report: sentiment & the Street", f"/ticker/{quote(sym)}/report"))
        elif h == "options":
            add(act(f"{sym} options" if sym else "Options Discover", "/options", {"symbol": sym}, desc="Chain, IV, put/call, expected move and unusual activity"))
        elif h == "earnings":
            if sym:
                add(act(f"{sym} earnings", f"/ticker/{quote(sym)}", hash_="earnings"))
            add(act("Earnings Hub", "/earnings", desc="Upcoming report dates and recent surprises"))
        elif h in ("dividends", "financials", "technicals", "news", "filings", "chart") and sym:
            add(act(f"{sym} {h}", f"/ticker/{quote(sym)}", hash_=h))
        elif h == "peers" and sym:
            add(act(f"{sym} peers & ratios", f"/ticker/{quote(sym)}", hash_="peers-ratios"))
        elif h == "congress":
            add(act(f"Congress trades in {sym}" if sym else "Congress Trading", "/congress", {"symbol": sym}, desc="Disclosed stock trades by members of Congress"))
        elif h == "smartmoney":
            add(act(f"Smart money in {sym}" if sym else "Smart Money Trackers", "/smart-money", {"symbol": sym}, desc="13F holdings and changes for well-known funds"))
        elif h == "patterns":
            tab = "regimes" if "regime" in low else "leadlag" if "lead" in low else "states" if "state" in low or "analog" in low else "micro" if "order" in low or "micro" in low else "tests"
            add(act("Pattern Lab", "/patterns", {"tab": tab, "symbol": sym if tab == "regimes" else None}, desc="Stress-tested patterns, regimes, lead-lag and market states"))
        elif h == "signals":
            add(act("Premium Signals", "/signals", desc="Tonight's scan: breakouts, RSI extremes, unusual moves"))
        elif h == "heatmap":
            add(act("Market heatmap", "/heatmap"))
        elif h == "macro":
            add(act("Macro map", "/macro"))
        elif h == "screener":
            add(act("Screeners", "/screeners"))
        elif h == "adr":
            add(act(f"{sym} ADR premium" if sym else "ADR Monitor", f"/monitor/adr/{quote(sym)}" if sym else "/monitor/adr"))
        elif h == "etf_monitor":
            add(act("ETF Monitor", "/monitor/etf"))
        elif h == "relative_value":
            add(act("Relative-value grades", "/monitor/fundamental"))
        elif h == "pairs":
            add(act("Pair ideas", "/monitor/pairs"))
        elif h == "portfolio":
            add(act("Portfolio analysis", "/portfolio", desc="Import holdings for P&L, concentration, risk and an AI review"))
        elif h == "themes":
            key = next((slug for pat, slug in THEME_KEYS if re.search(pat, low)), None)
            th = next((x for x in _themes() if x["slug"] == key), None)
            add(act(th["name"], f"/research/themes/{th['slug']}") if th else act("Research & themes", "/research"))
        elif h == "marketplace":
            add(act("Strategy marketplace", "/strategies"))
        elif h == "trade":
            add(act("Trade: ready-made strategies", "/trade"))
        elif h == "watchlist":
            add(act("Terminal & watchlist", "/terminal"))
        elif h == "alerts":
            add(act("Alerts settings", "/account", hash_="alerts"))
        elif h == "pricing":
            add(act("Compare plans", "/pricing"))
        elif h == "customize":
            add(act("Customize Irradiance", "/account/customize"))
        elif h == "learn":
            add(act("Learn & glossary", "/learn"))
        elif h == "community":
            add(act("Leaderboards" if "leaderboard" in low else "Community", "/leaderboards" if "leaderboard" in low else "/community"))
        elif h == "library":
            add(act("My library", "/library"))
        elif h == "ticker" and sym:
            add(act(f"Open {sym}", f"/ticker/{quote(sym)}"))
    if syms and not any(x["href"].startswith(f"/ticker/{syms[0]}") for x in acts) and hits and hits[0] not in ("compare", "montecarlo"):
        add(act(f"Open {syms[0]}", f"/ticker/{quote(syms[0])}"))
    acts = acts[:4]
    auto = bool(acts) and (bool(GO.search(t)) or hits == ["ticker"]) and not re.search(r"\b(how (do|can|would) i|can you explain|what is|what does|why)\b", low)
    if acts:
        acts[0]["primary"] = True
    return {"intents": hits, "tickers": syms, "actions": acts, "auto": auto and bool(acts), "note": note}


def describe_for_model(p: dict[str, Any]) -> str:
    if not p["actions"]:
        return ""
    lines = "\n".join(f"- {a['label']} → {a['href']}" for a in p["actions"])
    return ("\n\nAPP ACTIONS (the chat shows these as buttons under your answer"
            + ("; the first one opens automatically" if p["auto"] else "") + "):\n" + lines
            + (f"\nNote: {p['note']}" if p.get("note") else "")
            + "\nRefer to these by name (for example 'I've opened Compare with …'), do not tell the member to navigate manually, and do not paste URLs.")


def rules_reply(p: dict[str, Any]) -> str | None:
    if not p["actions"]:
        return None
    a = p["actions"][0]
    head = f"Opening **{a['label']}**." if p["auto"] else f"**{a['label']}** is the place for this."
    if p.get("note"):
        head += " " + p["note"]
    if a.get("desc"):
        head += f" {a['desc']}."
    more = [x["label"] for x in p["actions"][1:]]
    if more:
        head += " Also useful: " + ", ".join(more) + "."
    return head
