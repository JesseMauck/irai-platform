"use client";
import { useEffect, useState } from "react";

/** Plain-language context for each ticker tab: what it shows, how to read it, and key terms. */
const GUIDES: Record<string, { what: string; how: string[]; terms?: [string, string][] }> = {
  Summary: {
    what: "A one-screen snapshot: price, Irradiance grades, quant ratings, media buzz, the Street's view and recent filings.",
    how: ["Start with the quant rating to see which factors (valuation, quality, growth, momentum, risk) lead or lag.",
      "Use buzz to tell whether a move comes with unusual news flow or is happening quietly.",
      "Treat the consensus target as the Street's average expectation, not a forecast we endorse."],
    terms: [["Relative Value (RV) percentile", "Where the stock's valuation ranks against its peers; a higher percentile means cheaper on our blend."],
      ["Data badge", "LIVE is real-time or near real-time, EOD is end of day, STALE is older than expected, DEMO is sample data."]],
  },
  Analyst: {
    what: "The IRAI Analyst Bot gathers today's data for this ticker and writes a same-day research note. Every claim cites a numbered source.",
    how: ["Watch the progress bar: each step pulls one data set (news, filings, fundamentals, technicals, the Street).",
      "Read the bull and bear cases together; both are built from the same facts.",
      "Click a source tag (S1, S2…) to open the underlying article, filing or data set.", "Use Print report for a branded PDF."],
  },
  Chart: {
    what: "An interactive TradingView chart with drawing tools and hundreds of indicators.",
    how: ["Pick a time frame at the top. Daily or weekly bars suit long-term research; intraday bars suit short-term trading.",
      "Add indicators from the toolbar (for example moving averages, RSI or volume profile).", "Use the full-screen button to chart your own analysis."],
    terms: [["Candlestick", "One bar per period: the body spans open to close, the wicks show the high and low."]],
  },
  Financials: {
    what: "The income statement, balance sheet and cash-flow statement, annual or quarterly, from company filings.",
    how: ["Look for consistent revenue growth and stable or rising margins.", "Compare operating cash flow with net income; lasting gaps can flag earnings quality issues.",
      "Check debt against cash and equity on the balance sheet."],
    terms: [["Free cash flow", "Operating cash flow minus capital expenditure: cash left to return to shareholders or reinvest."],
      ["Operating margin", "Operating income divided by revenue."]],
  },
  Earnings: {
    what: "Reported and estimated EPS by quarter, the earnings surprise, and annual EPS history from SEC filings.",
    how: ["A positive surprise means reported EPS beat the consensus estimate.", "Look at the trend in surprises, not a single quarter.", "Note the next report date as a likely volatility event."],
    terms: [["EPS", "Earnings per share: net income divided by diluted shares outstanding."]],
  },
  Dividends: {
    what: "Dividend payment history, trailing yield, payout ratio and growth streak.",
    how: ["A payout ratio well above 100% of earnings may be hard to sustain.", "Steady multi-year increases suggest a dividend policy management protects.",
      "You must own the shares before the ex-dividend date to receive the next payment."],
    terms: [["Yield (TTM)", "Dividends paid over the last 12 months divided by the current price."], ["Ex-dividend date", "The first day the stock trades without the next dividend."]],
  },
  "Peers & ratios": {
    what: "Valuation, profitability and growth ratios next to the closest peers, with the peer median.",
    how: ["A premium multiple can be justified by faster growth or higher margins; compare the columns together.", "Use the peer median as a reference point, not a target."],
    terms: [["EV/EBITDA", "Enterprise value divided by earnings before interest, tax, depreciation and amortization; it is capital-structure neutral."],
      ["Forward P/E", "Price divided by expected earnings over the next 12 months."]],
  },
  Technicals: {
    what: "Trend, momentum and volatility indicators computed from daily closing prices.",
    how: ["Price above both the 50- and 200-day averages is an uptrend; below both is a downtrend.", "RSI above 70 is often read as overbought and below 30 as oversold.",
      "Bollinger Bands widen when volatility rises."],
    terms: [["MACD", "The difference between the 12- and 26-day exponential averages; crossing its signal line marks a momentum shift."]],
  },
  Filings: {
    what: "SEC filings straight from EDGAR. Key filings are shown by default; routine forms (prospectus supplements, insider forms) are behind a filter.",
    how: ["The 10-K (annual) and 10-Q (quarterly) are the primary financial reports.", "An 8-K reports a material event such as earnings, an acquisition or a leadership change.",
      "Form 4 shows insider buying and selling."],
  },
  News: {
    what: "The latest headlines from Yahoo Finance RSS and the GDELT global news database, with today's attention level.",
    how: ["A spike in buzz with little price movement may mean the news is already priced in, or not yet.", "Open the original article; headlines can mislead."],
  },
  Analysis: {
    what: "Community research and Irradiance articles about this ticker.",
    how: ["Check each author's track record on the leaderboard.", "Analysis posts must state a view and show their work; read the attached backtests and valuations."],
  },
  Preferreds: {
    what: "Preferred shares issued by the company: price, coupon and yield.",
    how: ["Preferreds rank above common shares for dividends but usually have no voting rights.", "Check whether a preferred is callable; a call can cap your upside."],
  },
};

export function TabGuide({ tab }: { tab: string }) {
  const g = GUIDES[tab];
  const [open, setOpen] = useState(false);
  useEffect(() => { try { setOpen(localStorage.getItem("irai.guide.hidden") !== "1"); } catch { setOpen(true); } }, []);
  if (!g) return null;
  const toggle = () => { const n = !open; setOpen(n); try { localStorage.setItem("irai.guide.hidden", n ? "0" : "1"); } catch { /* ignore */ } };
  return (
    <div className="mt-4 rounded-lg border border-line bg-card/60 text-sm print:hidden">
      <button onClick={toggle} className="flex w-full items-center justify-between px-4 py-2 text-left">
        <span><span className="mr-2 text-primary">ⓘ</span><b>About this tab:</b> <span className="text-muted">{g.what}</span></span>
        <span className="ml-3 shrink-0 text-xs text-muted">{open ? "Hide guide" : "How to read it"}</span>
      </button>
      {open && (
        <div className="grid gap-4 border-t border-line px-4 py-3 md:grid-cols-2">
          <div><div className="text-xs font-semibold uppercase tracking-wide text-muted">How to read it</div>
            <ul className="mt-1 list-disc space-y-1 pl-5">{g.how.map(h => <li key={h}>{h}</li>)}</ul></div>
          {g.terms && <div><div className="text-xs font-semibold uppercase tracking-wide text-muted">Key terms</div>
            <dl className="mt-1 space-y-1">{g.terms.map(([k, v]) => <div key={k}><dt className="inline font-medium">{k}: </dt><dd className="inline text-muted">{v}</dd></div>)}</dl></div>}
        </div>
      )}
    </div>
  );
}
